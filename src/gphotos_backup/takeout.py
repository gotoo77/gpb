from __future__ import annotations

import fcntl
import hashlib
import json
import mimetypes
import os
import shlex
import tarfile
import tempfile
import zipfile
import zlib
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from glob import glob, has_magic
from pathlib import Path
from typing import IO, Any

from .db import Database
from .models import (
    ArchiveCheckResult,
    ImportBreakdown,
    LibraryConfig,
    ReconcileSummary,
    Summary,
    TakeoutCheckSummary,
)
from .util import CHUNK, destination, parse_time, safe_archive_name, sanitize, sha256_file

SIDECAR_SUFFIX = ".json"
ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class MetadataRecord:
    metadata: dict[str, Any]
    sidecar_path: str


class CorruptArchiveError(ValueError):
    """An archive directory was readable but one of its members was corrupt."""

    def __init__(self, message: str, context: dict[str, object]) -> None:
        super().__init__(message)
        self.context = context


def _is_sidecar(name: str) -> bool:
    return name.lower().endswith(SIDECAR_SUFFIX)


def _media_key(name: str) -> str:
    path = safe_archive_name(name)
    raw = str(path)
    if _is_sidecar(raw):
        raw = raw[:-5]
    return raw


class Source:
    def names(self) -> list[str]:
        raise NotImplementedError

    @contextmanager
    def open(self, name: str) -> Iterator[IO[bytes]]:
        raise NotImplementedError

    def size(self, name: str) -> int:
        raise NotImplementedError

    def close(self) -> None:
        """Release resources held by an archive source."""


class DirectorySource(Source):
    def __init__(self, root: Path) -> None:
        self.root = root
        self._files = {
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
        }

    def names(self) -> list[str]:
        return list(self._files)

    @contextmanager
    def open(self, name: str) -> Iterator[IO[bytes]]:
        with self._files[name].open("rb") as stream:
            yield stream

    def size(self, name: str) -> int:
        return self._files[name].stat().st_size


class ZipSource(Source):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.archive = zipfile.ZipFile(path)
        self._items = {
            info.filename: info
            for info in self.archive.infolist()
            if not info.is_dir() and not _zip_symlink(info)
        }
        self._positions = {name: position for position, name in enumerate(self._items, start=1)}
        for name in self._items:
            safe_archive_name(name)

    def names(self) -> list[str]:
        return list(self._items)

    @contextmanager
    def open(self, name: str) -> Iterator[IO[bytes]]:
        try:
            with self.archive.open(self._items[name]) as stream:
                yield stream
        except (EOFError, zipfile.BadZipFile, zlib.error) as error:
            raise self._corruption_error(name, error) from error

    def size(self, name: str) -> int:
        return self._items[name].file_size

    def close(self) -> None:
        self.archive.close()

    def _corruption_error(self, name: str, error: BaseException) -> CorruptArchiveError:
        info = self._items[name]
        expected = b"PK\x03\x04"
        try:
            with self.path.open("rb") as raw:
                raw.seek(info.header_offset)
                actual = raw.read(4)
            actual_text = actual.hex(" ") if actual else "<fin de fichier>"
        except OSError as diagnostic_error:
            actual_text = f"<lecture impossible : {diagnostic_error}>"

        stat = self.path.stat()
        allocated = stat.st_blocks * 512
        sparse_gap = max(0, stat.st_size - allocated)
        position = self._positions.get(name, 0)
        command = f"unzip -t {shlex.quote(str(self.path))}"
        context: dict[str, object] = {
            "archive": str(self.path),
            "member": name,
            "member_index": position,
            "member_count": len(self._items),
            "header_offset": info.header_offset,
            "expected_magic": expected.hex(),
            "actual_magic": actual.hex() if "actual" in locals() else None,
            "archive_size": stat.st_size,
            "allocated_bytes": allocated,
            "sparse_gap_bytes": sparse_gap,
            "compressed_size": info.compress_size,
            "original_size": info.file_size,
            "expected_crc32": f"{info.CRC:08x}",
            "cause_type": type(error).__name__,
            "cause": str(error),
            "verification_command": command,
            "action": "redownload_takeout_volume",
        }
        details = [
            "Archive Takeout ZIP corrompue.",
            f"  Archive          : {self.path}",
            f"  Entrée           : {name}",
            f"  Index            : {position}/{len(self._items)}",
            f"  Offset d'en-tête : {info.header_offset} (0x{info.header_offset:x})",
            f"  Magic attendu    : {expected.hex(' ')} (PK\\x03\\x04)",
            f"  Magic lu         : {actual_text}",
            f"  Taille archive   : {stat.st_size} octets",
            f"  Espace alloué    : {allocated} octets",
            f"  Zone non allouée : {sparse_gap} octets",
            f"  Taille compressée: {info.compress_size} octets",
            f"  Taille originale : {info.file_size} octets",
            f"  CRC-32 attendu   : 0x{info.CRC:08x}",
            f"  Cause Python     : {type(error).__name__}: {error}",
            f"  Vérification     : {command}",
            "  Action           : retélécharger ce volume Takeout ; les médias déjà "
            "terminés restent intacts.",
        ]
        return CorruptArchiveError("\n".join(details), context)


class TarSource(Source):
    def __init__(self, path: Path) -> None:
        self.archive = tarfile.open(path, "r:*")  # noqa: SIM115
        self._items = {item.name: item for item in self.archive.getmembers() if item.isfile()}
        for name in self._items:
            safe_archive_name(name)

    def names(self) -> list[str]:
        return list(self._items)

    @contextmanager
    def open(self, name: str) -> Iterator[IO[bytes]]:
        stream = self.archive.extractfile(self._items[name])
        if stream is None:
            raise OSError(f"Cannot read {name}")
        with stream:
            yield stream

    def size(self, name: str) -> int:
        return self._items[name].size

    def close(self) -> None:
        self.archive.close()


def _zip_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def open_source(path: Path) -> Source:
    if path.is_dir():
        return DirectorySource(path)
    if path.suffix.lower() == ".zip":
        try:
            return ZipSource(path)
        except zipfile.BadZipFile as error:
            stat = path.stat()
            context: dict[str, object] = {
                "archive": str(path),
                "archive_size": stat.st_size,
                "cause_type": type(error).__name__,
                "cause": str(error),
                "verification_command": f"unzip -t {shlex.quote(str(path))}",
                "action": "redownload_takeout_volume",
            }
            raise CorruptArchiveError(
                "\n".join(
                    [
                        "Archive Takeout ZIP illisible.",
                        f"  Archive      : {path}",
                        f"  Taille       : {stat.st_size} octets",
                        f"  Cause Python : {type(error).__name__}: {error}",
                        f"  Vérification : unzip -t {shlex.quote(str(path))}",
                        "  Action       : retélécharger ce volume Takeout.",
                    ]
                ),
                context,
            ) from error
    if zipfile.is_zipfile(path):
        return ZipSource(path)
    if tarfile.is_tarfile(path):
        return TarSource(path)
    raise ValueError(f"Unsupported input (expected directory, ZIP, TGZ or TAR): {path}")


def _sidecar_candidates(media_name: str, names: set[str]) -> list[str]:
    candidates = [f"{media_name}.json"]
    path = Path(media_name)
    candidates.append(str(path.with_suffix(".json")))
    # Takeout sometimes truncates the media name before appending .json.
    basename = path.name
    matching = [
        name
        for name in names
        if _is_sidecar(name)
        and Path(name).parent == path.parent
        and (Path(name).name[:-5] == basename or Path(name).name[:-5].startswith(basename))
    ]
    return list(
        dict.fromkeys(candidate for candidate in candidates + matching if candidate in names)
    )


def _metadata(source: Source, name: str) -> tuple[dict[str, Any], str | None, list[str]]:
    matches = _sidecar_candidates(name, set(source.names()))
    if len(matches) != 1:
        warning = [] if not matches else [f"Ambiguous sidecar for {name}: {matches}"]
        return {}, None, warning
    sidecar = matches[0]
    if source.size(sidecar) > 64 * 1024**2:
        return {}, sidecar, [f"Sidecar exceeds 64 MiB safety limit: {sidecar}"]
    try:
        with source.open(sidecar) as stream:
            value = json.load(stream)
        return (value if isinstance(value, dict) else {}), sidecar, []
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        return {}, sidecar, [f"Invalid sidecar {sidecar}: {error}"]


def _capture(metadata: dict[str, Any]) -> datetime | None:
    return (
        parse_time(metadata.get("photoTakenTime"))
        or parse_time(metadata.get("creationTime"))
        or parse_time(metadata.get("creationTimestamp"))
    )


def _sidecar_media_key(name: str, media_names: set[str]) -> str | None:
    raw = str(safe_archive_name(name))
    lowered = raw.lower()
    marker = ".supplemental-metadata"
    marker_index = lowered.rfind(marker)
    if marker_index >= 0 and lowered.endswith(".json"):
        candidate = raw[:marker_index]
        if candidate in media_names:
            return candidate
    if lowered.endswith(".json"):
        candidate = raw[:-5]
        if candidate in media_names:
            return candidate

    sidecar = Path(raw)
    candidates = [
        media
        for media in media_names
        if Path(media).parent == sidecar.parent
        and (Path(media).stem == sidecar.stem or sidecar.name[:-5].startswith(Path(media).name))
    ]
    return candidates[0] if len(candidates) == 1 else None


def _build_metadata_catalog(
    prepared: list[tuple[int, Path, set[str]]],
    config: LibraryConfig,
    *,
    progress: ProgressCallback | None = None,
    inventory_progress: bool = False,
) -> tuple[dict[str, MetadataRecord], int, int, int]:
    media_names = {
        name for _index, _path, names in prepared for name in names if not _is_sidecar(name)
    }
    references: dict[tuple[Path, str], str] = {}
    orphan_count = 0
    for _index, input_path, names in prepared:
        for name in names:
            if not _is_sidecar(name):
                continue
            key = _sidecar_media_key(name, media_names)
            if key is None:
                orphan_count += 1
            else:
                references[(input_path, name)] = key

    sidecar_total_bytes = 0
    for archive_index, input_path, names in prepared:
        source = open_source(input_path)
        try:
            sidecar_total_bytes += sum(source.size(name) for name in names if _is_sidecar(name))
        finally:
            source.close()
        if progress and inventory_progress:
            progress(
                archive_index,
                len(prepared),
                f"Phase 2/3 · Analyse JSON [{archive_index}/{len(prepared)}] "
                f"{input_path.name[-24:]}",
            )
    if progress and sidecar_total_bytes:
        progress(0, sidecar_total_bytes, "Phase 2/3 · Extraction des métadonnées")

    preserved_by_key: dict[str, list[str]] = {}
    sidecar_completed_bytes = 0
    sidecars_processed = 0
    for archive_index, input_path, names in prepared:
        source = open_source(input_path)
        try:
            archive_sidecars = 0
            for name in names:
                if not _is_sidecar(name):
                    continue
                key = references.get((input_path, name))
                label = (
                    f"media-key__{hashlib.sha256(key.encode()).hexdigest()[:16]}"
                    if key is not None
                    else "orphan"
                )
                sidecar_path = _preserve_sidecar(source, name, config, label)
                sidecar_completed_bytes += source.size(name)
                sidecars_processed += 1
                archive_sidecars += 1
                if key is not None:
                    preserved_by_key.setdefault(key, []).append(sidecar_path)
            if progress and sidecar_total_bytes:
                progress(
                    sidecar_completed_bytes,
                    sidecar_total_bytes,
                    f"Phase 2/3 · Métadonnées [{archive_index}/{len(prepared)}] "
                    f"{input_path.name[-24:]} · {archive_sidecars} JSON "
                    f"({sidecars_processed} au total)",
                )
        finally:
            source.close()

    catalog: dict[str, MetadataRecord] = {}
    ambiguous = 0
    malformed = 0
    for key, preserved in preserved_by_key.items():
        unique_by_digest: dict[str, str] = {}
        for sidecar_path in dict.fromkeys(preserved):
            digest, _size = sha256_file(config.library_root / sidecar_path)
            unique_by_digest.setdefault(digest, sidecar_path)
        if len(unique_by_digest) != 1:
            ambiguous += 1
            continue
        sidecar_path = next(iter(unique_by_digest.values()))
        try:
            value = json.loads((config.library_root / sidecar_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            malformed += 1
            continue
        if isinstance(value, dict):
            catalog[key] = MetadataRecord(metadata=value, sidecar_path=sidecar_path)
        else:
            malformed += 1

    return catalog, orphan_count, ambiguous, malformed


def _preserve_sidecar(source: Source, name: str, config: LibraryConfig, label: str) -> str:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=config.library_root / ".gphotos-backup", suffix=".partial", delete=False
        ) as temporary:
            temp_path = Path(temporary.name)
            with source.open(name) as incoming:
                while block := incoming.read(CHUNK):
                    _write_block(temporary, block)
        digest, _ = sha256_file(temp_path)
        target = (
            config.library_root
            / "metadata"
            / f"{label}__{digest[:16]}__{sanitize(Path(name).name)}"
        )
        if target.exists():
            return str(target.relative_to(config.library_root))
        os.replace(temp_path, target)
        return str(target.relative_to(config.library_root))
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _copy_media_to_temp(
    source: Source,
    name: str,
    config: LibraryConfig,
    on_block: Callable[[int], None],
) -> tuple[Path, str, int]:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=config.library_root / ".gphotos-backup",
            suffix=".partial",
            delete=False,
        ) as temporary:
            temp_path = Path(temporary.name)
            digest_builder = hashlib.sha256()
            size = 0
            with source.open(name) as stream:
                while block := stream.read(CHUNK):
                    _write_block(temporary, block)
                    digest_builder.update(block)
                    block_size = len(block)
                    size += block_size
                    on_block(block_size)
        return temp_path, digest_builder.hexdigest(), size
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _write_block(stream: IO[bytes], block: bytes) -> None:
    stream.write(block)


def import_takeout(
    inputs: list[Path],
    config: LibraryConfig,
    db: Database,
    *,
    dry_run: bool = False,
    apply_file_times: bool = False,
    progress: ProgressCallback | None = None,
) -> Summary:
    with _import_lock(config.library_root):
        return _import_takeout_locked(
            inputs,
            config,
            db,
            dry_run=dry_run,
            apply_file_times=apply_file_times,
            progress=progress,
        )


def _import_takeout_locked(
    inputs: list[Path],
    config: LibraryConfig,
    db: Database,
    *,
    dry_run: bool,
    apply_file_times: bool,
    progress: ProgressCallback | None,
) -> Summary:
    summary = Summary()
    summary.abandoned_partials = find_partials(config.library_root)
    if summary.abandoned_partials:
        summary.warnings.append(
            f"{len(summary.abandoned_partials)} fichier(s) .partial abandonné(s) détecté(s). "
            "Ils ne seront pas importés ; lancez `gpb status` pour les localiser."
        )
    run_id = db.begin_run("takeout import")
    try:
        with ExitStack() as stack:
            prepared: list[tuple[int, Path, set[str]]] = []
            total_media_bytes = 0
            expanded_inputs = _expand_inputs(inputs)
            for archive_index, input_path in enumerate(expanded_inputs, start=1):
                source = open_source(input_path)
                try:
                    names = set(source.names())
                    archive_bytes = sum(source.size(name) for name in names)
                    if archive_bytes > config.max_archive_bytes:
                        raise ValueError(f"Archive expands beyond configured limit: {input_path}")
                    total_media_bytes += sum(
                        source.size(name) for name in names if not _is_sidecar(name)
                    )
                    prepared.append((archive_index, input_path, names))
                finally:
                    source.close()

            metadata_catalog: dict[str, MetadataRecord] = {}
            if config.preserve_sidecars and not dry_run:
                (
                    metadata_catalog,
                    orphan_count,
                    ambiguous_count,
                    malformed_count,
                ) = _build_metadata_catalog(prepared, config, progress=progress)
                if orphan_count:
                    summary.warnings.append(
                        f"{orphan_count} sidecar(s) JSON sans média correspondant ont été "
                        "conservés dans metadata/."
                    )
                if ambiguous_count:
                    summary.warnings.append(
                        f"{ambiguous_count} association(s) de sidecar restent ambiguës ; "
                        "les JSON concernés ont été conservés."
                    )
                if malformed_count:
                    summary.warnings.append(
                        f"{malformed_count} sidecar(s) JSON malformé(s) ont été conservés "
                        "mais ignorés."
                    )

            completed_bytes = 0
            if progress:
                progress(0, total_media_bytes, "Analyse terminée")

            for archive_index, input_path, names in prepared:
                source = open_source(input_path)
                stack.callback(source.close)
                for name in sorted(names):
                    if _is_sidecar(name):
                        continue
                    archive_key = str(input_path)
                    media_type = _media_type(name)
                    summary.scanned += 1
                    _record_breakdown(summary, archive_key, media_type, "scanned")
                    member_size = source.size(name)
                    archive_label = input_path.name[-24:]
                    member_label = Path(name).name[-32:]
                    label = (
                        f"[{archive_index}/{len(expanded_inputs)}] {archive_label} · {member_label}"
                    )
                    if member_size > config.max_member_bytes:
                        summary.failed += 1
                        _record_breakdown(summary, archive_key, media_type, "failed")
                        summary.warnings.append(f"Member too large: {name}")
                        completed_bytes += member_size
                        if progress:
                            progress(completed_bytes, total_media_bytes, label)
                        continue

                    record = metadata_catalog.get(str(safe_archive_name(name)))
                    metadata = record.metadata if record else {}
                    sidecar_path = record.sidecar_path if record else None
                    capture = _capture(metadata)

                    def advance(block_size: int, current_label: str = label) -> None:
                        nonlocal completed_bytes
                        completed_bytes += block_size
                        if progress:
                            progress(completed_bytes, total_media_bytes, current_label)

                    temp_path, digest, size = _copy_media_to_temp(source, name, config, advance)
                    try:
                        if db.by_hash(digest):
                            summary.already_local += 1
                            _record_breakdown(summary, archive_key, media_type, "already_local")
                            continue
                        target = destination(config.library_root, Path(name).name, capture, digest)
                        if dry_run:
                            summary.imported += 1
                            summary.bytes_written += size
                            _record_breakdown(
                                summary,
                                archive_key,
                                media_type,
                                "imported",
                                bytes_written=size,
                            )
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(temp_path, target)
                        if (apply_file_times or config.apply_file_times) and capture:
                            stamp = capture.timestamp()
                            os.utime(target, (stamp, stamp))
                        db.add_media(
                            {
                                "source": "takeout",
                                "original_name": Path(name).name,
                                "local_path": str(target.relative_to(config.library_root)),
                                "mime_type": mimetypes.guess_type(name)[0],
                                "size": size,
                                "sha256": digest,
                                "capture_time": capture.isoformat() if capture else None,
                                "download_status": "complete",
                                "metadata_provenance": (
                                    "takeout-sidecar" if record else "filesystem"
                                ),
                                "sidecar_path": sidecar_path,
                            }
                        )
                        summary.imported += 1
                        summary.bytes_written += size
                        _record_breakdown(
                            summary,
                            archive_key,
                            media_type,
                            "imported",
                            bytes_written=size,
                        )
                    finally:
                        temp_path.unlink(missing_ok=True)

                source.close()
        db.finish_run(run_id, summary.model_dump(), "success")
    except BaseException as error:
        result = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        message = (
            "Interruption utilisateur (SIGINT)"
            if isinstance(error, KeyboardInterrupt)
            else str(error)
        )
        db.finish_run(run_id, summary.model_dump(), result, [message])
        raise
    return summary


@contextmanager
def _import_lock(root: Path) -> Iterator[None]:
    path = root / ".gphotos-backup" / "import.lock"
    with path.open("a+", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                f"Un import est déjà en cours pour {root}. "
                "Attendez sa fin ou interrompez-le avant de relancer."
            ) from None
        stream.seek(0)
        stream.truncate()
        stream.write(f"{os.getpid()}\n")
        stream.flush()
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def import_is_running(root: Path) -> bool:
    path = root / ".gphotos-backup" / "import.lock"
    if not path.exists():
        return False
    try:
        with path.open("a+", encoding="utf-8") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(stream, fcntl.LOCK_UN)
    except OSError:
        return False
    return False


def find_partials(root: Path) -> list[str]:
    control = root / ".gphotos-backup"
    if not control.is_dir():
        return []
    return sorted(str(path) for path in control.glob("*.partial") if path.is_file())


def _media_type(name: str) -> str:
    mime_type = mimetypes.guess_type(name)[0]
    if mime_type is None:
        return "other"
    category = mime_type.partition("/")[0]
    return category if category in {"image", "video", "audio"} else "other"


def _record_breakdown(
    summary: Summary,
    archive: str,
    media_type: str,
    field: str,
    *,
    bytes_written: int = 0,
) -> None:
    for collection, key in (
        (summary.archives, archive),
        (summary.media_types, media_type),
    ):
        breakdown = collection.setdefault(key, ImportBreakdown())
        setattr(breakdown, field, getattr(breakdown, field) + 1)
        breakdown.bytes_written += bytes_written


def reconcile_takeout(
    inputs: list[Path],
    config: LibraryConfig,
    db: Database,
    *,
    progress: ProgressCallback | None = None,
) -> ReconcileSummary:
    with _import_lock(config.library_root):
        return _reconcile_takeout_locked(inputs, config, db, progress=progress)


def _reconcile_takeout_locked(
    inputs: list[Path],
    config: LibraryConfig,
    db: Database,
    *,
    progress: ProgressCallback | None,
) -> ReconcileSummary:
    summary = ReconcileSummary()
    run_id = db.begin_run("takeout reconcile")
    try:
        prepared: list[tuple[int, Path, set[str]]] = []
        total_bytes = 0
        expanded = _expand_inputs(inputs)
        for archive_index, input_path in enumerate(expanded, start=1):
            source = open_source(input_path)
            try:
                names = set(source.names())
                prepared.append((archive_index, input_path, names))
                total_bytes += sum(source.size(name) for name in names if not _is_sidecar(name))
            finally:
                source.close()
            if progress:
                progress(
                    archive_index,
                    len(expanded),
                    f"Phase 1/3 · Inventaire [{archive_index}/{len(expanded)}] "
                    f"{input_path.name[-24:]}",
                )

        (
            catalog,
            summary.orphan_sidecars,
            summary.ambiguous_sidecars,
            summary.malformed_sidecars,
        ) = _build_metadata_catalog(
            prepared,
            config,
            progress=progress,
            inventory_progress=True,
        )
        summary.sidecars_catalogued = len(catalog)
        rows_by_hash = {str(row["sha256"]): dict(row) for row in db.rows()}
        completed = 0
        if progress:
            progress(0, total_bytes, "Phase 3/3 · Réconciliation des médias")

        for archive_index, input_path, names in prepared:
            source = open_source(input_path)
            try:
                with db.connect() as connection:
                    try:
                        for name in sorted(names):
                            if _is_sidecar(name):
                                continue
                            summary.media_scanned += 1
                            member_size = source.size(name)
                            record = catalog.get(str(safe_archive_name(name)))
                            label = (
                                f"Phase 3/3 · [{archive_index}/{len(expanded)}] "
                                f"{input_path.name[-24:]} · {Path(name).name[-32:]}"
                            )
                            if record is None:
                                completed += member_size
                                if progress:
                                    progress(completed, total_bytes, label)
                                continue
                            summary.metadata_matched += 1
                            digest_builder = hashlib.sha256()
                            with source.open(name) as stream:
                                while block := stream.read(CHUNK):
                                    digest_builder.update(block)
                                    block_size = len(block)
                                    completed += block_size
                                    summary.bytes_read += block_size
                                    if progress:
                                        progress(completed, total_bytes, label)
                            digest = digest_builder.hexdigest()
                            row = rows_by_hash.get(digest)
                            if row is None:
                                summary.missing_from_library += 1
                                continue
                            summary.database_matched += 1
                            capture = _capture(record.metadata)
                            if capture is None:
                                summary.metadata_without_date += 1
                            existing_capture = parse_time(row.get("capture_time"))
                            effective_capture = capture or existing_capture
                            current = config.library_root / str(row["local_path"])
                            target = current
                            if effective_capture is not None and current.is_file():
                                target = _reconcile_destination(
                                    config.library_root,
                                    Path(name).name,
                                    effective_capture,
                                    digest,
                                    current,
                                )
                                if target != current:
                                    target.parent.mkdir(parents=True, exist_ok=True)
                                    os.replace(current, target)
                                    summary.files_moved += 1
                            elif not current.is_file():
                                summary.warnings.append(f"Fichier local introuvable : {current}")
                            relative_target = str(target.relative_to(config.library_root))
                            effective_capture_text = (
                                effective_capture.isoformat() if effective_capture else None
                            )
                            connection.execute(
                                """UPDATE media
                                   SET capture_time=?,
                                       metadata_provenance='takeout-sidecar',
                                       sidecar_path=?, local_path=?
                                   WHERE id=?""",
                                (
                                    effective_capture_text,
                                    record.sidecar_path,
                                    relative_target,
                                    row["id"],
                                ),
                            )
                            row["capture_time"] = effective_capture_text
                            row["metadata_provenance"] = "takeout-sidecar"
                            row["sidecar_path"] = record.sidecar_path
                            row["local_path"] = relative_target
                            summary.metadata_updated += 1
                    except BaseException:
                        # Files already moved in this archive must remain in sync
                        # with their SQLite rows before propagating SIGINT/errors.
                        connection.commit()
                        raise
            finally:
                source.close()
        try:
            _write_reconcile_report(config.library_root, run_id, summary)
        except OSError as error:
            summary.report_path = None
            summary.warnings.append(
                f"Impossible d'enregistrer le rapport de réconciliation : {error}"
            )
        db.finish_run(run_id, summary.model_dump(), "success")
    except BaseException as error:
        result = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        db.finish_run(run_id, summary.model_dump(), result, [str(error)])
        raise
    return summary


def _write_reconcile_report(root: Path, run_id: str, summary: ReconcileSummary) -> None:
    target = root / "manifests" / f"reconcile-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{run_id[:8]}.json"
    temporary = target.with_suffix(".json.partial")
    summary.report_path = str(target)
    try:
        temporary.write_text(
            json.dumps(
                summary.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _reconcile_destination(
    root: Path,
    original: str,
    capture: datetime,
    digest: str,
    current: Path,
) -> Path:
    directory = root / "media" / f"{capture.year:04d}" / f"{capture.month:02d}"
    prefix = capture.strftime("%Y-%m-%d_%H-%M-%S")
    candidate = directory / f"{prefix}__{sanitize(original)}"
    if candidate.exists() and candidate != current:
        candidate = directory / f"{prefix}__{digest[:10]}__{sanitize(original)}"
    return candidate


def check_takeout(
    inputs: list[Path],
    *,
    progress: ProgressCallback | None = None,
    force: bool = False,
    cache_path: Path | None = None,
) -> TakeoutCheckSummary:
    """Fully read every archive member and report all invalid inputs."""
    summary = TakeoutCheckSummary()
    expanded = _expand_inputs(inputs)
    summary.archives_checked = len(expanded)
    resolved_cache_path = cache_path or _takeout_check_cache_path()
    cache = _load_check_cache(resolved_cache_path)

    with ExitStack() as stack:
        prepared: list[tuple[int, Path, Source, list[str], int]] = []
        for archive_index, input_path in enumerate(expanded, start=1):
            identity = _archive_identity(input_path)
            cached = cache.get(str(input_path))
            if not force and identity is not None and cached is not None:
                cached_identity = cached.get("identity")
                cached_result = cached.get("result")
                if cached_identity == identity and isinstance(cached_result, dict):
                    result = ArchiveCheckResult.model_validate(cached_result)
                    result.cached = True
                    summary.results.append(result)
                    summary.cached += 1
                    summary.bytes_reused += result.bytes_checked
                    if result.status == "valid":
                        summary.valid += 1
                    else:
                        summary.corrupt += 1
                    continue
            try:
                source = open_source(input_path)
                stack.callback(source.close)
                names = sorted(source.names())
                archive_bytes = sum(source.size(name) for name in names)
                prepared.append((archive_index, input_path, source, names, archive_bytes))
            except (OSError, ValueError, tarfile.TarError) as error:
                summary.corrupt += 1
                result = _failed_check(input_path, error)
                summary.results.append(result)
                _cache_check_result(cache, resolved_cache_path, input_path, result)

        total_bytes = sum(item[4] for item in prepared)
        completed_bytes = 0
        if progress:
            progress(
                0,
                total_bytes,
                f"{summary.cached} en cache · {len(prepared)} à contrôler",
            )

        for archive_index, input_path, source, names, archive_bytes in prepared:
            archive_checked = 0
            members_checked = 0
            failure: BaseException | None = None
            for name in names:
                archive_label = input_path.name[-24:]
                member_label = Path(name).name[-32:]
                label = f"[{archive_index}/{len(expanded)}] {archive_label} · {member_label}"
                try:
                    with source.open(name) as stream:
                        while block := stream.read(CHUNK):
                            block_size = len(block)
                            archive_checked += block_size
                            summary.bytes_checked += block_size
                            completed_bytes += block_size
                            if progress:
                                progress(completed_bytes, total_bytes, label)
                    members_checked += 1
                except (OSError, ValueError, tarfile.TarError) as error:
                    failure = error
                    break

            if failure is None:
                summary.valid += 1
                summary.results.append(
                    ArchiveCheckResult(
                        path=str(input_path),
                        status="valid",
                        members_checked=members_checked,
                        bytes_checked=archive_checked,
                    )
                )
            else:
                summary.corrupt += 1
                result = _failed_check(input_path, failure)
                result.members_checked = members_checked
                result.bytes_checked = archive_checked
                summary.results.append(result)

            _cache_check_result(cache, resolved_cache_path, input_path, summary.results[-1])

            # A broken member cannot be decompressed further. Count its unread
            # logical bytes only for progress, not in bytes_checked.
            completed_bytes += max(0, archive_bytes - archive_checked)
            if progress:
                progress(completed_bytes, total_bytes, input_path.name)

    return summary


def _takeout_check_cache_path() -> Path:
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_root / "gphotos-backup" / "takeout-checks.json"


def _archive_identity(path: Path) -> dict[str, int] | None:
    if not path.is_file():
        return None
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "inode": stat.st_ino,
        "device": stat.st_dev,
    }


def _load_check_cache(path: Path) -> dict[str, dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("version") == 1:
            entries = value.get("entries")
            if isinstance(entries, dict):
                return {str(key): item for key, item in entries.items() if isinstance(item, dict)}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _cache_check_result(
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
    input_path: Path,
    result: ArchiveCheckResult,
) -> None:
    identity = _archive_identity(input_path)
    if identity is None:
        return
    cache[str(input_path)] = {
        "identity": identity,
        "result": result.model_copy(update={"cached": False}).model_dump(mode="json"),
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=cache_path.parent,
            prefix=f".{cache_path.name}.",
            delete=False,
        ) as temporary:
            json.dump({"version": 1, "entries": cache}, temporary, ensure_ascii=False)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, cache_path)
    except OSError:
        if "temporary_path" in locals():
            temporary_path.unlink(missing_ok=True)


def _failed_check(path: Path, error: BaseException) -> ArchiveCheckResult:
    context = error.context if isinstance(error, CorruptArchiveError) else None
    return ArchiveCheckResult(
        path=str(path),
        status="corrupt",
        error=str(error),
        context=context,
    )


def _expand_inputs(inputs: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in inputs:
        raw = str(path.expanduser())
        matches = sorted(glob(raw)) if has_magic(raw) else [raw]
        if not matches:
            raise FileNotFoundError(f"No archive or directory matches: {raw}")
        for match in matches:
            resolved = Path(match).resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"Archive or directory not found: {resolved}")
            expanded.append(resolved)
    return list(dict.fromkeys(expanded))

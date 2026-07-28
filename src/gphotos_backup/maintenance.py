from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .db import Database

ItemProgress = Callable[[int, int, str], None]

MEDIA_COLUMNS = {
    "id",
    "provider_id",
    "source",
    "original_name",
    "local_path",
    "mime_type",
    "size",
    "sha256",
    "capture_time",
    "remote_creation_time",
    "imported_at",
    "width",
    "height",
    "duration_seconds",
    "download_status",
    "verification_status",
    "remote_url",
    "metadata_provenance",
    "sidecar_path",
    "error",
    "attempts",
}
REQUIRED_COLUMNS = {"id", "source", "original_name", "local_path", "size", "sha256", "imported_at"}


def _safe_local_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("local_path absent ou invalide")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"local_path non sûr : {value}")
    return value


def rebuild_database(
    root: Path,
    manifest: Path,
    *,
    replace: bool = False,
    progress: ItemProgress | None = None,
) -> dict[str, object]:
    manifest = manifest.expanduser().resolve()
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    target = Database(root).path
    if target.exists() and not replace:
        raise FileExistsError(
            f"La base existe déjà : {target}. "
            "Utilisez --replace pour la sauvegarder et la remplacer."
        )

    with manifest.open(encoding="utf-8") as stream:
        total = sum(1 for line in stream if line.strip())
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.rebuild.partial")
    rebuilt = Database(root, path=temporary)
    rebuilt.initialize()
    seen_paths: set[str] = set()
    inserted = 0
    bytes_catalogued = 0
    try:
        with rebuilt.connect() as connection, manifest.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"JSON invalide à la ligne {line_number}: {error.msg}"
                    ) from error
                if not isinstance(raw, dict):
                    raise ValueError(f"Objet JSON attendu à la ligne {line_number}")
                missing = REQUIRED_COLUMNS - raw.keys()
                if missing:
                    raise ValueError(
                        f"Champs absents à la ligne {line_number}: {', '.join(sorted(missing))}"
                    )
                local_path = _safe_local_path(raw["local_path"])
                if local_path in seen_paths:
                    raise ValueError(f"Chemin dupliqué à la ligne {line_number}: {local_path}")
                seen_paths.add(local_path)
                media_path = root / local_path
                if not media_path.is_file():
                    raise ValueError(f"Média absent à la ligne {line_number}: {local_path}")
                actual_size = media_path.stat().st_size
                expected_size = int(raw["size"])
                if actual_size != expected_size:
                    raise ValueError(
                        f"Taille incorrecte à la ligne {line_number}: {local_path} "
                        f"({actual_size} au lieu de {expected_size})"
                    )
                values = {key: value for key, value in raw.items() if key in MEDIA_COLUMNS}
                values["verification_status"] = "pending"
                values["error"] = None
                columns = ", ".join(values)
                placeholders = ", ".join("?" for _ in values)
                connection.execute(
                    f"INSERT INTO media ({columns}) VALUES ({placeholders})",
                    tuple(values.values()),
                )
                inserted += 1
                bytes_catalogued += actual_size
                if progress:
                    progress(inserted, total, local_path)
            connection.commit()

        backup: Path | None = None
        if target.exists():
            backup = target.with_name(f"{target.name}.backup-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}")
            with sqlite3.connect(target) as source, sqlite3.connect(backup) as destination:
                source.backup(destination)
        for suffix in ("-wal", "-shm"):
            Path(f"{target}{suffix}").unlink(missing_ok=True)
        os.replace(temporary, target)
        os.chmod(target, 0o600)
        return {
            "media_restored": inserted,
            "bytes_catalogued": bytes_catalogued,
            "database": str(target),
            "backup": str(backup) if backup else None,
            "verification_status": "pending",
        }
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def library_report(
    root: Path, rows: list[sqlite3.Row], progress: ItemProgress | None = None
) -> dict[str, object]:
    years: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    bytes_by_year: Counter[str] = Counter()
    bytes_by_format: Counter[str] = Counter()
    hashes: dict[str, list[int]] = defaultdict(list)
    anomalies: Counter[str] = Counter()
    total_bytes = 0

    for index, row in enumerate(rows, start=1):
        size = int(row["size"])
        total_bytes += size
        capture_time = str(row["capture_time"] or "")
        year = (
            capture_time[:4]
            if len(capture_time) >= 4 and capture_time[:4].isdigit()
            else "sans-date"
        )
        suffix = Path(str(row["original_name"])).suffix.lower() or "sans-extension"
        years[year] += 1
        formats[suffix] += 1
        bytes_by_year[year] += size
        bytes_by_format[suffix] += size
        hashes[str(row["sha256"])].append(size)
        path = root / str(row["local_path"])
        if not path.is_file():
            anomalies["missing"] += 1
        elif path.stat().st_size != size:
            anomalies["size_mismatch"] += 1
        status = str(row["verification_status"])
        if status == "pending":
            anomalies["pending_verification"] += 1
        elif status not in {"verified", "pending"}:
            anomalies["integrity_failure"] += 1
        if year == "sans-date":
            anomalies["without_date"] += 1
        if progress:
            progress(index, len(rows), str(row["local_path"]))

    duplicate_groups = [sizes for sizes in hashes.values() if len(sizes) > 1]
    return {
        "library": str(root),
        "media": len(rows),
        "bytes": total_bytes,
        "verified": sum(row["verification_status"] == "verified" for row in rows),
        "years": {key: {"media": years[key], "bytes": bytes_by_year[key]} for key in sorted(years)},
        "formats": {
            key: {"media": formats[key], "bytes": bytes_by_format[key]}
            for key in sorted(formats, key=lambda item: (-formats[item], item))
        },
        "duplicates": {
            "groups": len(duplicate_groups),
            "media": sum(len(group) for group in duplicate_groups),
            "reclaimable_bytes": sum(sum(group) - max(group) for group in duplicate_groups),
        },
        "anomalies": dict(anomalies),
    }

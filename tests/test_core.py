from __future__ import annotations

import errno
import json
import os
import signal
import tarfile
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

import gphotos_backup.takeout as takeout_module
from gphotos_backup.cli import app
from gphotos_backup.config import load, write_config
from gphotos_backup.db import Database
from gphotos_backup.takeout import ZipSource, check_takeout, import_takeout
from gphotos_backup.util import safe_archive_name, sanitize


@pytest.fixture
def library(tmp_path: Path) -> tuple[Path, Database]:
    root = tmp_path / "library"
    write_config(root)
    db = Database(root)
    db.initialize()
    return root, db


def make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def test_takeout_import_is_idempotent_and_preserves_sidecar(
    library: tuple[Path, Database], tmp_path: Path
) -> None:
    root, db = library
    archive = tmp_path / "takeout.zip"
    make_zip(
        archive,
        {
            "Takeout/Google Photos/été/📷.jpg": b"photo bytes",
            "Takeout/Google Photos/été/📷.jpg.json": json.dumps(
                {"photoTakenTime": {"timestamp": "1704067200"}}
            ).encode(),
        },
    )
    first = import_takeout([archive], load(root), db)
    second = import_takeout([archive], load(root), db)
    assert first.imported == 1
    assert second.already_local == 1
    row = db.rows()[0]
    assert (root / row["local_path"]).read_bytes() == b"photo bytes"
    assert row["sidecar_path"] is not None
    assert "2024/01" in row["local_path"]
    assert first.archives[str(archive)].imported == 1
    assert first.media_types["image"].imported == 1
    assert first.media_types["image"].bytes_written == len(b"photo bytes")


def test_same_name_different_hash_gets_collision_suffix(
    library: tuple[Path, Database], tmp_path: Path
) -> None:
    root, db = library
    one, two = tmp_path / "one.zip", tmp_path / "two.zip"
    sidecar = json.dumps({"photoTakenTime": {"timestamp": "1704067200"}}).encode()
    make_zip(one, {"same.jpg": b"one", "same.jpg.json": sidecar})
    make_zip(two, {"same.jpg": b"two", "same.jpg.json": sidecar})
    import_takeout([one], load(root), db)
    import_takeout([two], load(root), db)
    paths = [row["local_path"] for row in db.rows()]
    assert len(paths) == 2
    assert any(Path(path).name.count("__") == 2 for path in paths)


def test_dry_run_does_not_write(library: tuple[Path, Database], tmp_path: Path) -> None:
    root, db = library
    archive = tmp_path / "dry.zip"
    make_zip(archive, {"x.jpg": b"x"})
    summary = import_takeout([archive], load(root), db, dry_run=True)
    assert summary.imported == 1
    assert not db.rows()
    assert not list((root / "media").rglob("*.jpg"))


def test_sidecar_absent_and_ambiguous_are_safe(
    library: tuple[Path, Database], tmp_path: Path
) -> None:
    root, db = library
    archive = tmp_path / "ambiguous.zip"
    make_zip(
        archive,
        {
            "a.jpg": b"a",
            "a.jpg.json": b"{}",
            "a.jpg.extra.json": b"{}",
            "b.jpg": b"b",
        },
    )
    summary = import_takeout([archive], load(root), db)
    assert summary.imported == 2
    assert any("Ambiguous" in warning for warning in summary.warnings)


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    make_zip(archive, {"../../escape.jpg": b"bad"})
    with pytest.raises(ValueError, match="Unsafe"):
        ZipSource(archive)
    assert not (tmp_path.parent / "escape.jpg").exists()


def test_symlink_member_is_ignored(tmp_path: Path) -> None:
    archive = tmp_path / "links.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (0o120777 << 16) | 0xA000
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(info, "/etc/passwd")
    assert ZipSource(archive).names() == []


def test_unicode_and_long_sanitization() -> None:
    assert "été" not in sanitize("été/📷?.jpg")
    assert len(sanitize("a" * 400 + ".jpg")) <= 180


def test_safe_archive_paths() -> None:
    assert str(safe_archive_name("Takeout/a.jpg")) == "Takeout/a.jpg"
    for name in ("/etc/passwd", "../secret", "a/../../b"):
        with pytest.raises(ValueError):
            safe_archive_name(name)


def test_multipart_overlap_is_idempotent(library: tuple[Path, Database], tmp_path: Path) -> None:
    root, db = library
    one, two = tmp_path / "part-1.zip", tmp_path / "part-2.zip"
    make_zip(one, {"a.jpg": b"a", "overlap.jpg": b"same"})
    make_zip(two, {"overlap.jpg": b"same", "b.jpg": b"b"})
    summary = import_takeout([one, two], load(root), db)
    assert summary.imported == 3
    assert summary.already_local == 1
    assert len(db.rows()) == 3


def test_tar_symlink_is_ignored(library: tuple[Path, Database], tmp_path: Path) -> None:
    root, db = library
    archive = tmp_path / "takeout.tar"
    with tarfile.open(archive, "w") as output:
        info = tarfile.TarInfo("unsafe-link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        output.addfile(info)
        payload = b"safe"
        media = tarfile.TarInfo("safe.jpg")
        media.size = len(payload)
        import io

        output.addfile(media, io.BytesIO(payload))
    summary = import_takeout([archive], load(root), db)
    assert summary.imported == 1
    assert db.rows()[0]["original_name"] == "safe.jpg"


def test_member_size_limit(library: tuple[Path, Database], tmp_path: Path) -> None:
    root, db = library
    archive = tmp_path / "large.zip"
    make_zip(archive, {"large.mp4": b"x" * 20})
    config = load(root)
    config.max_member_bytes = 10
    summary = import_takeout([archive], config, db)
    assert summary.failed == 1
    assert not db.rows()


def test_orphan_json_is_preserved(library: tuple[Path, Database], tmp_path: Path) -> None:
    root, db = library
    archive = tmp_path / "metadata.zip"
    make_zip(archive, {"album-metadata.json": b'{"title":"Album"}'})
    summary = import_takeout([archive], load(root), db)
    metadata = list((root / "metadata").iterdir())
    assert len(metadata) == 1
    assert metadata[0].read_bytes() == b'{"title":"Album"}'
    assert summary.warnings


def test_takeout_glob_expands_internally(library: tuple[Path, Database], tmp_path: Path) -> None:
    root, db = library
    make_zip(tmp_path / "takeout-1.zip", {"a.jpg": b"a"})
    make_zip(tmp_path / "takeout-2.zip", {"b.jpg": b"b"})
    pattern = Path(str(tmp_path / "takeout-*.zip"))
    summary = import_takeout([pattern], load(root), db)
    assert summary.imported == 2


def test_missing_glob_has_clear_error(library: tuple[Path, Database], tmp_path: Path) -> None:
    root, db = library
    pattern = Path(str(tmp_path / "missing-*.zip"))
    with pytest.raises(FileNotFoundError, match="No archive or directory matches"):
        import_takeout([pattern], load(root), db)


def test_cli_missing_library_has_no_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GPB_LIBRARY", raising=False)
    result = CliRunner().invoke(
        app,
        ["takeout", "import", str(tmp_path / "takeout-*.zip")],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "No library configured" in result.output
    assert "Traceback" not in result.output


def test_progress_is_monotonic_and_reaches_total(
    library: tuple[Path, Database], tmp_path: Path
) -> None:
    root, db = library
    archive = tmp_path / "progress.zip"
    make_zip(archive, {"a.jpg": b"a" * 10, "b.mp4": b"b" * 20})
    events: list[tuple[int, int, str]] = []
    import_takeout([archive], load(root), db, progress=lambda *event: events.append(event))
    completed = [event[0] for event in events]
    assert completed == sorted(completed)
    assert events[-1][0] == events[-1][1] == 30


def test_corrupt_zip_is_reported_and_partial_is_removed(
    library: tuple[Path, Database], tmp_path: Path
) -> None:
    root, db = library
    archive = tmp_path / "corrupt.zip"
    make_zip(archive, {"photo.jpg": b"photo"})
    with archive.open("r+b") as stream:
        stream.write(b"BROKEN")
    with pytest.raises(ValueError) as captured:
        import_takeout([archive], load(root), db)
    message = str(captured.value)
    assert "Archive Takeout ZIP corrompue" in message
    assert str(archive) in message
    assert "photo.jpg" in message
    assert "Magic attendu" in message
    assert "Magic lu" in message
    assert "Offset d'en-tête" in message
    assert "CRC-32 attendu" in message
    assert "unzip -t" in message
    assert not list((root / ".gphotos-backup").glob("*.partial"))


def test_corrupt_zip_cli_error_is_detailed_json(
    library: tuple[Path, Database], tmp_path: Path
) -> None:
    root, _ = library
    archive = tmp_path / "corrupt-cli.zip"
    make_zip(archive, {"photo.jpg": b"photo"})
    with archive.open("r+b") as stream:
        stream.write(b"BROKEN")
    result = CliRunner().invoke(
        app,
        [
            "takeout",
            "import",
            "--library",
            str(root),
            "--json",
            str(archive),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    context = payload["error"]["context"]
    assert context["archive"] == str(archive)
    assert context["member"] == "photo.jpg"
    assert context["expected_magic"] == "504b0304"
    assert context["actual_magic"] == "42524f4b"
    assert "Traceback" not in result.output


def test_takeout_check_reports_every_archive_and_continues_after_corruption(
    tmp_path: Path,
) -> None:
    make_zip(tmp_path / "takeout-001.zip", {"a.jpg": b"a" * 10})
    corrupt = tmp_path / "takeout-002.zip"
    make_zip(corrupt, {"b.jpg": b"b" * 20})
    with corrupt.open("r+b") as stream:
        stream.write(b"BROKEN")
    make_zip(tmp_path / "takeout-003.zip", {"c.jpg": b"c" * 30})

    events: list[tuple[int, int, str]] = []
    summary = check_takeout(
        [Path(str(tmp_path / "takeout-*.zip"))],
        progress=lambda *event: events.append(event),
        cache_path=tmp_path / "checks.json",
    )

    assert summary.archives_checked == 3
    assert summary.valid == 2
    assert summary.corrupt == 1
    assert [result.status for result in summary.results] == ["valid", "corrupt", "valid"]
    failed = summary.results[1]
    assert failed.path == str(corrupt)
    assert failed.context is not None
    assert failed.context["member"] == "b.jpg"
    assert events[-1][0] == events[-1][1]


def test_takeout_check_cli_needs_no_library_and_returns_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GPB_LIBRARY", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    good = tmp_path / "good.zip"
    corrupt = tmp_path / "corrupt.zip"
    make_zip(good, {"good.jpg": b"good"})
    make_zip(corrupt, {"bad.jpg": b"bad"})
    with corrupt.open("r+b") as stream:
        stream.write(b"BROKEN")

    result = CliRunner().invoke(
        app,
        ["takeout", "check", "--json", str(good), str(corrupt)],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["archives_checked"] == 2
    assert payload["valid"] == 1
    assert payload["corrupt"] == 1
    assert payload["results"][1]["context"]["archive"] == str(corrupt)


def test_takeout_check_reuses_unchanged_results_and_rechecks_replaced_file(
    tmp_path: Path,
) -> None:
    one = tmp_path / "takeout-001.zip"
    two = tmp_path / "takeout-002.zip"
    cache = tmp_path / "checks.json"
    make_zip(one, {"one.jpg": b"one"})
    make_zip(two, {"two.jpg": b"two"})

    first = check_takeout([one, two], cache_path=cache)
    second = check_takeout([one, two], cache_path=cache)
    assert first.cached == 0
    assert second.cached == 2
    assert second.bytes_checked == 0
    assert second.bytes_reused == first.bytes_checked

    two.unlink()
    make_zip(two, {"replacement.jpg": b"a different payload"})
    third = check_takeout([one, two], cache_path=cache)
    assert third.cached == 1
    assert third.valid == 2


@pytest.mark.parametrize("phase", ["before-copy", "during-copy"])
def test_real_sigint_records_interruption_and_leaves_no_partial(
    library: tuple[Path, Database],
    tmp_path: Path,
    phase: str,
) -> None:
    root, db = library
    archive = tmp_path / f"sigint-{phase}.zip"
    make_zip(archive, {"large.jpg": os.urandom(2 * 1024 * 1024)})
    signalled = False

    def interrupt(completed: int, _total: int, _label: str) -> None:
        nonlocal signalled
        should_interrupt = completed == 0 if phase == "before-copy" else completed > 0
        if should_interrupt and not signalled:
            signalled = True
            os.kill(os.getpid(), signal.SIGINT)

    with pytest.raises(KeyboardInterrupt):
        import_takeout([archive], load(root), db, progress=interrupt)

    assert signalled
    assert not list((root / ".gphotos-backup").glob("*.partial"))
    last_run = db.latest_run()
    assert last_run is not None
    assert last_run["result"] == "interrupted"
    assert last_run["errors"] == ["Interruption utilisateur (SIGINT)"]


def test_disk_full_is_recorded_without_partial_or_completed_media(
    library: tuple[Path, Database],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, db = library
    archive = tmp_path / "disk-full.zip"
    make_zip(archive, {"photo.jpg": b"x" * 1024})

    def disk_full(_stream: object, _block: bytes) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(takeout_module, "_write_block", disk_full)
    with pytest.raises(OSError) as captured:
        import_takeout([archive], load(root), db)

    assert captured.value.errno == errno.ENOSPC
    assert not db.rows()
    assert not list((root / ".gphotos-backup").glob("*.partial"))
    last_run = db.latest_run()
    assert last_run is not None
    assert last_run["result"] == "failed"
    assert "No space left on device" in str(last_run["errors"])


def test_sigint_during_sidecar_copy_keeps_media_uncommitted_and_removes_partial(
    library: tuple[Path, Database],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, db = library
    archive = tmp_path / "sidecar-sigint.zip"
    make_zip(archive, {"photo.jpg": b"photo", "photo.jpg.json": b"{}"})
    real_write = takeout_module._write_block
    writes = 0

    def interrupt_second_write(stream: object, block: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            os.kill(os.getpid(), signal.SIGINT)
        real_write(stream, block)  # type: ignore[arg-type]

    monkeypatch.setattr(takeout_module, "_write_block", interrupt_second_write)
    with pytest.raises(KeyboardInterrupt):
        import_takeout([archive], load(root), db)

    assert not db.rows()
    assert not list((root / ".gphotos-backup").glob("*.partial"))
    assert not list((root / "media").rglob("*.jpg"))
    last_run = db.latest_run()
    assert last_run is not None
    assert last_run["result"] == "interrupted"


def test_abandoned_partial_is_reported_by_import_and_status(
    library: tuple[Path, Database],
    tmp_path: Path,
) -> None:
    root, db = library
    partial = root / ".gphotos-backup" / "abandoned.partial"
    partial.write_bytes(b"incomplete")
    archive = tmp_path / "valid.zip"
    make_zip(archive, {"photo.jpg": b"photo"})

    summary = import_takeout([archive], load(root), db)
    assert summary.abandoned_partials == [str(partial)]
    assert any(".partial abandonné" in warning for warning in summary.warnings)
    assert partial.read_bytes() == b"incomplete"

    result = CliRunner().invoke(
        app,
        ["status", "--library", str(root), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["abandoned_partials"] == 1
    assert payload["partial_paths"] == [str(partial)]
    assert payload["last_run"]["result"] == "success"


def test_status_without_library_has_no_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GPB_LIBRARY", raising=False)
    result = CliRunner().invoke(
        app,
        ["status"],
        catch_exceptions=False,
        env={"PWD": str(tmp_path)},
    )
    assert result.exit_code == 2
    assert "No library configured" in result.output
    assert "Traceback" not in result.output


def test_status_distinguishes_active_partial_from_abandoned(
    library: tuple[Path, Database],
) -> None:
    root, db = library
    partial = root / ".gphotos-backup" / "active.partial"
    partial.write_bytes(b"in progress")
    db.begin_run("takeout import")

    result = CliRunner().invoke(
        app,
        ["status", "--library", str(root), "--json"],
        catch_exceptions=False,
    )
    payload = json.loads(result.output)
    assert payload["import_running"] is True
    assert payload["active_partials"] == 1
    assert payload["abandoned_partials"] == 0


def test_second_takeout_import_is_rejected_while_first_holds_lock(
    library: tuple[Path, Database], tmp_path: Path
) -> None:
    root, db = library
    archive = tmp_path / "locked.zip"
    make_zip(archive, {"photo.jpg": b"photo"})
    checked = False

    def try_second_import(_completed: int, _total: int, _label: str) -> None:
        nonlocal checked
        if checked:
            return
        checked = True
        with pytest.raises(ValueError, match="déjà en cours"):
            import_takeout([archive], load(root), db)

    summary = import_takeout([archive], load(root), db, progress=try_second_import)
    assert checked
    assert summary.imported == 1


def test_takeout_import_keeps_at_most_one_archive_open(
    library: tuple[Path, Database],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, db = library
    archives = [tmp_path / "one.zip", tmp_path / "two.zip", tmp_path / "three.zip"]
    for index, archive in enumerate(archives):
        make_zip(archive, {f"{index}.jpg": str(index).encode()})

    real_open_source = takeout_module.open_source
    active = 0
    maximum = 0

    def tracked_open(path: Path) -> takeout_module.Source:
        nonlocal active, maximum
        source = real_open_source(path)
        original_close = source.close
        closed = False
        active += 1
        maximum = max(maximum, active)

        def tracked_close() -> None:
            nonlocal active, closed
            original_close()
            if not closed:
                active -= 1
                closed = True

        source.close = tracked_close  # type: ignore[method-assign]
        return source

    monkeypatch.setattr(takeout_module, "open_source", tracked_open)
    summary = import_takeout(archives, load(root), db)
    assert summary.imported == 3
    assert active == 0
    assert maximum == 1

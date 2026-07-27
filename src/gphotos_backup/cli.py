from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from . import __version__
from . import auth as oauth
from .config import discover, load, write_config
from .db import Database
from .models import ReconcileSummary, Summary, TakeoutCheckSummary
from .takeout import (
    CorruptArchiveError,
    check_takeout,
    find_partials,
    import_is_running,
    import_takeout,
    reconcile_takeout,
)
from .util import sha256_file

app = typer.Typer(help="Reliable local Google Photos archive.")
auth_app = typer.Typer(help="OAuth authentication.")
picker_app = typer.Typer(help="Import an explicit Google Photos selection.")
takeout_app = typer.Typer(help="Import Google Takeout archives.")
app.add_typer(auth_app, name="auth")
app.add_typer(picker_app, name="picker")
app.add_typer(takeout_app, name="takeout")


def _root(value: Path | None) -> Path:
    return discover(value)


def _emit(value: Any, as_json: bool = False) -> None:
    if as_json:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        typer.echo(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))
        return
    if isinstance(value, Summary):
        typer.echo(f"Scanned:       {value.scanned:,}")
        typer.echo(f"Already local: {value.already_local:,}")
        typer.echo(f"Imported:      {value.imported:,}")
        typer.echo(f"Skipped:       {value.skipped:,}")
        typer.echo(f"Failed:        {value.failed:,}")
        typer.echo(f"Bytes written: {value.bytes_written:,}")
        if value.archives:
            typer.echo("\nPar archive :")
            for archive, counters in value.archives.items():
                typer.echo(
                    f"- {Path(archive).name}: {counters.imported:,} importé(s), "
                    f"{counters.already_local:,} déjà présent(s), "
                    f"{counters.failed:,} échec(s), {counters.bytes_written:,} octets"
                )
        if value.media_types:
            typer.echo("\nPar type de média :")
            for media_type, counters in sorted(value.media_types.items()):
                typer.echo(
                    f"- {media_type}: {counters.imported:,} importé(s), "
                    f"{counters.already_local:,} déjà présent(s), "
                    f"{counters.failed:,} échec(s), {counters.bytes_written:,} octets"
                )
        if value.abandoned_partials:
            typer.echo("\nFichiers partiels abandonnés :", err=True)
            for partial in value.abandoned_partials:
                typer.echo(f"- {partial}", err=True)
        for warning in value.warnings:
            typer.echo(f"WARNING: {warning}", err=True)
    elif isinstance(value, ReconcileSummary):
        typer.echo(f"Médias analysés       : {value.media_scanned:,}")
        typer.echo(f"Métadonnées associées : {value.metadata_matched:,}")
        typer.echo(f"Médias locaux trouvés : {value.database_matched:,}")
        typer.echo(f"Fiches mises à jour   : {value.metadata_updated:,}")
        typer.echo(f"Fichiers déplacés     : {value.files_moved:,}")
        typer.echo(f"Sidecars catalogués   : {value.sidecars_catalogued:,}")
        typer.echo(f"Sidecars orphelins    : {value.orphan_sidecars:,}")
        typer.echo(f"Associations ambiguës : {value.ambiguous_sidecars:,}")
        typer.echo(f"Octets lus            : {value.bytes_read:,}")
        for warning in value.warnings:
            typer.echo(f"WARNING: {warning}", err=True)
    elif isinstance(value, dict):
        for key, item in value.items():
            typer.echo(f"{key}: {item}")
    else:
        typer.echo(value)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", help="Show version and exit.", is_eager=True)
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable diagnostic output.")] = False,
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command("init")
def initialize(
    library: Annotated[Path, typer.Option("--library", help="Local library root.")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    root = library.expanduser().resolve()
    path = write_config(root)
    db = Database(root)
    db.initialize()
    _emit({"status": "initialized", "library": str(root), "config": str(path)}, json_output)


@auth_app.command("login")
def auth_login(library: Annotated[Path | None, typer.Option("--library")] = None) -> None:
    oauth.login(_root(library))
    typer.echo("OAuth login completed.")


@auth_app.command("status")
def auth_status(
    library: Annotated[Path | None, typer.Option("--library")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _emit(oauth.status(_root(library)), json_output)


def _latest_session(db: Database) -> str:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT id FROM picker_sessions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise typer.BadParameter("No Picker session. Run `gpb picker create-session`.")
    return str(row["id"])


@picker_app.command("create-session")
def picker_create(
    library: Annotated[Path | None, typer.Option("--library")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    from .picker import PickerClient

    root = _root(library)
    db = Database(root)
    data = PickerClient(root).create_session()
    now = datetime.now(UTC).isoformat()
    with db.connect() as connection:
        connection.execute(
            """INSERT OR REPLACE INTO picker_sessions
               (id, picker_uri, media_items_set, created_at, updated_at)
               VALUES (?, ?, 0, ?, ?)""",
            (data["id"], data["pickerUri"], now, now),
        )
    _emit(
        {
            "session_id": data["id"],
            "picker_uri": data["pickerUri"],
            "instruction": "Open picker_uri and explicitly select the media to import.",
        },
        json_output,
    )


@picker_app.command("poll")
def picker_poll(
    session: Annotated[str | None, typer.Option("--session")] = None,
    library: Annotated[Path | None, typer.Option("--library")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    from .picker import PickerClient

    root = _root(library)
    db = Database(root)
    session_id = session or _latest_session(db)
    data = PickerClient(root).get_session(session_id)
    ready = bool(data.get("mediaItemsSet"))
    with db.connect() as connection:
        connection.execute(
            "UPDATE picker_sessions SET media_items_set=?, updated_at=? WHERE id=?",
            (ready, datetime.now(UTC).isoformat(), session_id),
        )
    _emit(
        {"session_id": session_id, "ready": ready, "polling": data.get("pollingConfig")},
        json_output,
    )


@picker_app.command("download")
def picker_download(
    session: Annotated[str | None, typer.Option("--session")] = None,
    library: Annotated[Path | None, typer.Option("--library")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    jobs: Annotated[int, typer.Option("--jobs", min=1, max=32)] = 4,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    from .picker import download_session

    config = load(library)
    config.jobs = jobs
    db = Database(config.library_root)
    _emit(
        download_session(session or _latest_session(db), config, db, dry_run=dry_run), json_output
    )


@takeout_app.command("import")
def takeout_import(
    paths: Annotated[list[Path], typer.Argument(help="Archive(s) or extracted directory.")],
    library: Annotated[Path | None, typer.Option("--library")] = None,
    apply_file_times: Annotated[bool, typer.Option("--apply-file-times")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    show_progress: Annotated[
        bool, typer.Option("--progress/--no-progress", help="Afficher la progression en octets.")
    ] = True,
) -> None:
    try:
        config = load(library)
        db = Database(config.library_root)
        progress_ui = Progress(
            SpinnerColumn(),
            TextColumn("{task.description}", markup=False),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=Console(stderr=True),
            disable=json_output or not show_progress,
        )
        with progress_ui:
            task = progress_ui.add_task("Analyse des archives…", total=None)

            def update_progress(completed: int, total: int, label: str) -> None:
                progress_ui.update(
                    task,
                    completed=completed,
                    total=total,
                    description=label[-70:],
                )

            summary = import_takeout(
                paths,
                config,
                db,
                dry_run=dry_run,
                apply_file_times=apply_file_times,
                progress=update_progress,
            )
            progress_ui.update(task, description="Import terminé")
    except KeyboardInterrupt:
        message = (
            "Import interrompu proprement. Les médias terminés sont conservés ; "
            "relancez exactement la même commande pour reprendre."
        )
        if json_output:
            _emit(
                {
                    "status": "interrupted",
                    "error": {"type": "KeyboardInterrupt", "message": message},
                },
                True,
            )
        else:
            typer.echo(f"\nINTERRUPTION: {message}", err=True)
        raise typer.Exit(130) from None
    except (OSError, ValueError) as error:
        if json_output:
            details: dict[str, object] = {
                "type": type(error).__name__,
                "message": str(error),
            }
            if isinstance(error, CorruptArchiveError):
                details["context"] = error.context
            _emit({"status": "error", "error": details}, True)
        else:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(2) from None
    _emit(summary, json_output)


@takeout_app.command("check")
def takeout_check(
    paths: Annotated[list[Path], typer.Argument(help="Archive(s) or extracted directory.")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
    show_progress: Annotated[
        bool, typer.Option("--progress/--no-progress", help="Afficher la progression en octets.")
    ] = True,
    force: Annotated[
        bool, typer.Option("--force", help="Ignorer le cache et tout contrôler à nouveau.")
    ] = False,
) -> None:
    """Contrôler intégralement les archives avant leur import."""
    try:
        progress_ui = Progress(
            SpinnerColumn(),
            TextColumn("{task.description}", markup=False),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=Console(stderr=True),
            disable=json_output or not show_progress,
        )
        with progress_ui:
            task = progress_ui.add_task("Préparation du contrôle…", total=None)

            def update_progress(completed: int, total: int, label: str) -> None:
                if total == 0:
                    progress_ui.update(task, visible=False)
                    return
                progress_ui.update(
                    task,
                    completed=completed,
                    total=total,
                    description=label[-70:],
                )

            summary = check_takeout(paths, progress=update_progress, force=force)
            progress_ui.update(task, description="Contrôle terminé")
    except (FileNotFoundError, ValueError) as error:
        if json_output:
            _emit(
                {
                    "status": "error",
                    "error": {"type": type(error).__name__, "message": str(error)},
                },
                True,
            )
        else:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(2) from None

    if json_output:
        _emit(summary, True)
    else:
        _emit_check_summary(summary)
    if summary.corrupt:
        raise typer.Exit(1)


@takeout_app.command("reconcile")
def takeout_reconcile(
    paths: Annotated[list[Path], typer.Argument(help="Archives Takeout à réconcilier.")],
    library: Annotated[Path | None, typer.Option("--library")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    show_progress: Annotated[
        bool, typer.Option("--progress/--no-progress", help="Afficher la progression en octets.")
    ] = True,
) -> None:
    """Rattacher les sidecars entre volumes et corriger la bibliothèque."""
    try:
        config = load(library)
        db = Database(config.library_root)
        progress_ui = Progress(
            SpinnerColumn(),
            TextColumn("{task.description}", markup=False),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=Console(stderr=True),
            disable=json_output or not show_progress,
        )
        with progress_ui:
            task = progress_ui.add_task("Catalogue des métadonnées…", total=None)

            def update_progress(completed: int, total: int, label: str) -> None:
                progress_ui.update(
                    task,
                    completed=completed,
                    total=total,
                    description=label[-70:],
                )

            summary = reconcile_takeout(paths, config, db, progress=update_progress)
            progress_ui.update(task, description="Réconciliation terminée")
    except KeyboardInterrupt:
        typer.echo(
            "\nINTERRUPTION: réconciliation interrompue proprement ; relancez la même commande.",
            err=True,
        )
        raise typer.Exit(130) from None
    except (OSError, ValueError) as error:
        if json_output:
            _emit(
                {
                    "status": "error",
                    "error": {"type": type(error).__name__, "message": str(error)},
                },
                True,
            )
        else:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(2) from None
    _emit(summary, json_output)


def _emit_check_summary(summary: TakeoutCheckSummary) -> None:
    typer.echo(f"Archives contrôlées : {summary.archives_checked:,}")
    typer.echo(f"Archives valides    : {summary.valid:,}")
    typer.echo(f"Archives corrompues : {summary.corrupt:,}")
    typer.echo(f"Résultats réutilisés: {summary.cached:,}")
    typer.echo(f"Octets lus cette fois : {summary.bytes_checked:,}")
    typer.echo(f"Octets validés en cache: {summary.bytes_reused:,}")
    if not summary.corrupt:
        typer.echo("OK : toutes les archives sont lisibles intégralement.")
        return
    typer.echo("\nVolumes à retélécharger :", err=True)
    for result in summary.results:
        if result.status != "corrupt":
            continue
        typer.echo(f"\n- {result.path}", err=True)
        if result.error:
            typer.echo(result.error, err=True)


@app.command()
def scan(
    library: Annotated[Path | None, typer.Option("--library")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    config = load(library)
    db = Database(config.library_root)
    summary = Summary()
    indexed = {str(row["local_path"]) for row in db.rows()}
    for path in sorted((config.library_root / "media").rglob("*")):
        if not path.is_file() or path.name.endswith(".partial"):
            continue
        summary.scanned += 1
        relative = str(path.relative_to(config.library_root))
        if relative in indexed:
            summary.already_local += 1
            continue
        digest, size = sha256_file(path)
        if db.by_hash(digest):
            summary.already_local += 1
            continue
        if not dry_run:
            db.add_media(
                {
                    "source": "local",
                    "original_name": path.name,
                    "local_path": relative,
                    "size": size,
                    "sha256": digest,
                    "download_status": "complete",
                    "metadata_provenance": "filesystem",
                }
            )
        summary.imported += 1
    _emit(summary, json_output)


@app.command()
def verify(
    library: Annotated[Path | None, typer.Option("--library")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    root = _root(library)
    db = Database(root)
    summary = Summary()
    with db.connect() as connection:
        for row in db.rows():
            summary.scanned += 1
            path = root / str(row["local_path"])
            if not path.is_file():
                summary.failed += 1
                summary.warnings.append(f"Missing: {row['local_path']}")
                status = "missing"
            else:
                digest, size = sha256_file(path)
                status = (
                    "verified" if digest == row["sha256"] and size == row["size"] else "corrupt"
                )
                if status == "verified":
                    summary.already_local += 1
                else:
                    summary.failed += 1
                    summary.warnings.append(f"Integrity mismatch: {row['local_path']}")
            connection.execute(
                "UPDATE media SET verification_status=?, error=? WHERE id=?",
                (status, None if status == "verified" else status, row["id"]),
            )
    _emit(summary, json_output)
    if summary.failed:
        raise typer.Exit(1)


@app.command()
def status(
    library: Annotated[Path | None, typer.Option("--library")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        root = _root(library)
    except (FileNotFoundError, ValueError) as error:
        if json_output:
            _emit(
                {
                    "status": "error",
                    "error": {"type": type(error).__name__, "message": str(error)},
                },
                True,
            )
        else:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(2) from None
    db = Database(root)
    payload: dict[str, object] = dict(db.counts())
    payload["library"] = str(root)
    partials = find_partials(root)
    last_run = db.latest_run()
    legacy_running = last_run is not None and last_run["result"] == "running"
    running = import_is_running(root) or legacy_running
    payload["import_running"] = running
    payload["active_partials"] = len(partials) if running else 0
    payload["abandoned_partials"] = 0 if running else len(partials)
    payload["partial_paths"] = partials
    payload["last_run"] = last_run
    _emit(payload, json_output)


@app.command("export-manifest")
def export_manifest(
    library: Annotated[Path | None, typer.Option("--library")] = None,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    root = _root(library)
    db = Database(root)
    target = output or root / "manifests" / f"manifest-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.jsonl"
    temporary = target.with_suffix(target.suffix + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in db.rows():
            safe = {key: row[key] for key in row if key != "remote_url"}
            stream.write(json.dumps(safe, sort_keys=True, ensure_ascii=False) + "\n")
    temporary.replace(target)
    typer.echo(str(target))


@app.command()
def doctor(
    library: Annotated[Path | None, typer.Option("--library")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    online: Annotated[
        bool, typer.Option("--online", help="Also probe the official Picker endpoint.")
    ] = False,
) -> None:
    checks: list[dict[str, str]] = []
    checks.append(
        {
            "name": "python",
            "status": "OK" if sys.version_info >= (3, 12) else "ERROR",
            "detail": sys.version.split()[0],
        }
    )
    try:
        root = _root(library)
        config = load(root)
        writable = os.access(root, os.W_OK)
        checks.append({"name": "configuration", "status": "OK", "detail": str(root)})
        checks.append(
            {"name": "library-write", "status": "OK" if writable else "ERROR", "detail": str(root)}
        )
        usage = shutil.disk_usage(root)
        checks.append({"name": "disk-free", "status": "OK", "detail": str(usage.free)})
        partials = find_partials(root)
        running = import_is_running(root)
        checks.append(
            {
                "name": "partial-files",
                "status": "WARNING" if partials and not running else "OK",
                "detail": (
                    f"{len(partials)} actif(s): {', '.join(partials)}"
                    if partials and running
                    else f"{len(partials)} abandonné(s): {', '.join(partials)}"
                    if partials
                    else "none"
                ),
            }
        )
        db = Database(config.library_root)
        with db.connect() as connection:
            connection.execute("PRAGMA integrity_check").fetchone()
        checks.append({"name": "sqlite", "status": "OK", "detail": str(db.path)})
        state = oauth.status(root)
        checks.append(
            {
                "name": "oauth",
                "status": "OK" if state["authenticated"] else "WARNING",
                "detail": "configured" if state["authenticated"] else "run gpb auth login",
            }
        )
        credentials = oauth.credentials_path(root)
        mode_ok = not credentials.exists() or credentials.stat().st_mode & 0o077 == 0
        checks.append(
            {
                "name": "credentials-permissions",
                "status": "OK" if mode_ok else "ERROR",
                "detail": "0600 required",
            }
        )
        if online:
            import httpx

            try:
                response = httpx.get(
                    "https://photospicker.googleapis.com/v1/sessions/connectivity-probe",
                    timeout=5.0,
                )
                reachable = response.status_code in {400, 401, 403, 404}
                checks.append(
                    {
                        "name": "picker-connectivity",
                        "status": "OK" if reachable else "WARNING",
                        "detail": f"HTTP {response.status_code}",
                    }
                )
            except httpx.HTTPError as error:
                checks.append(
                    {"name": "picker-connectivity", "status": "WARNING", "detail": str(error)}
                )
        else:
            checks.append(
                {
                    "name": "picker-connectivity",
                    "status": "WARNING",
                    "detail": "not probed; pass --online",
                }
            )
    except (FileNotFoundError, ValueError, sqlite3.Error) as error:
        checks.append({"name": "library", "status": "WARNING", "detail": str(error)})
    for executable in ("ffprobe", "exiftool"):
        checks.append(
            {
                "name": executable,
                "status": "OK" if shutil.which(executable) else "WARNING",
                "detail": "optional",
            }
        )
    checks.append(
        {
            "name": "full-library-api",
            "status": "UNSUPPORTED",
            "detail": "Google Library API cannot list a pre-existing full library",
        }
    )
    if json_output:
        _emit({"checks": checks}, True)
    else:
        for check in checks:
            typer.echo(f"{check['status']:11} {check['name']}: {check['detail']}")
    if any(check["status"] == "ERROR" for check in checks):
        raise typer.Exit(1)

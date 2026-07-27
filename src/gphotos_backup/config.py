from __future__ import annotations

import os
import tomllib
from pathlib import Path

from .models import LibraryConfig

ENV_LIBRARY = "GPB_LIBRARY"
CONFIG_NAME = "config.toml"


def layout(root: Path) -> None:
    for relative in (
        "media",
        "metadata",
        "manifests",
        "quarantine",
        ".gphotos-backup/logs",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    os.chmod(root / ".gphotos-backup", 0o700)


def write_config(root: Path) -> Path:
    layout(root)
    path = root / ".gphotos-backup" / CONFIG_NAME
    escaped = str(root.resolve()).replace("\\", "\\\\").replace('"', '\\"')
    content = (
        f'library_root = "{escaped}"\n'
        'organization = "capture-date"\n'
        'filename_policy = "stable"\n'
        'hash_algorithm = "sha256"\n'
        "jobs = 4\n"
        "preserve_sidecars = true\n"
        "apply_file_times = false\n"
    )
    temporary = path.with_suffix(".partial")
    temporary.write_text(content, encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return path


def discover(explicit: Path | None = None) -> Path:
    if explicit:
        return explicit.expanduser().resolve()
    env = os.environ.get(ENV_LIBRARY)
    if env:
        return Path(env).expanduser().resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".gphotos-backup" / CONFIG_NAME).is_file():
            return candidate
    raise FileNotFoundError(
        f"No library configured. Run `gpb init --library PATH` or set {ENV_LIBRARY}."
    )


def load(root: Path | None = None) -> LibraryConfig:
    selected = discover(root)
    path = selected / ".gphotos-backup" / CONFIG_NAME
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    return LibraryConfig.model_validate(data)

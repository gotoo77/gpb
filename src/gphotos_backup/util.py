from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

CHUNK = 1024 * 1024
SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_archive_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or "\x00" in normalized:
        raise ValueError(f"Unsafe archive path: {name!r}")
    return path


def sanitize(name: str, limit: int = 180) -> str:
    value = unicodedata.normalize("NFC", Path(name).name)
    value = SAFE.sub("_", value).strip(" .")
    if not value:
        value = "unnamed"
    suffix = "".join(Path(value).suffixes)
    stem_limit = max(1, limit - len(suffix))
    return f"{Path(value).stem[:stem_limit]}{suffix}"[:limit]


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(CHUNK):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def parse_time(value: object) -> datetime | None:
    if isinstance(value, dict):
        value = value.get("timestamp") or value.get("formatted")
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            return datetime.fromtimestamp(int(value), tz=UTC)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, OverflowError):
            return None
    return None


def destination(root: Path, original: str, capture: datetime | None, digest: str) -> Path:
    moment = capture or datetime.fromtimestamp(0, UTC)
    directory = root / "media" / f"{moment.year:04d}" / f"{moment.month:02d}"
    prefix = moment.strftime("%Y-%m-%d_%H-%M-%S")
    candidate = directory / f"{prefix}__{sanitize(original)}"
    if candidate.exists():
        candidate = directory / f"{prefix}__{digest[:10]}__{sanitize(original)}"
    return candidate

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Source(StrEnum):
    PICKER = "picker"
    TAKEOUT = "takeout"
    ANDROID = "android"
    LOCAL = "local"


class LibraryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_root: Path
    organization: str = "capture-date"
    filename_policy: str = "stable"
    hash_algorithm: str = "sha256"
    jobs: int = Field(default=4, ge=1, le=32)
    preserve_sidecars: bool = True
    apply_file_times: bool = False
    max_member_bytes: int = Field(default=100 * 1024**3, gt=0)
    max_archive_bytes: int = Field(default=2 * 1024**4, gt=0)


class ImportBreakdown(BaseModel):
    scanned: int = 0
    imported: int = 0
    already_local: int = 0
    failed: int = 0
    bytes_written: int = 0


class Summary(BaseModel):
    scanned: int = 0
    already_local: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_written: int = 0
    warnings: list[str] = Field(default_factory=list)
    abandoned_partials: list[str] = Field(default_factory=list)
    archives: dict[str, ImportBreakdown] = Field(default_factory=dict)
    media_types: dict[str, ImportBreakdown] = Field(default_factory=dict)


class ArchiveCheckResult(BaseModel):
    path: str
    status: str
    cached: bool = False
    members_checked: int = 0
    bytes_checked: int = 0
    error: str | None = None
    context: dict[str, object] | None = None


class TakeoutCheckSummary(BaseModel):
    archives_checked: int = 0
    valid: int = 0
    corrupt: int = 0
    cached: int = 0
    bytes_checked: int = 0
    bytes_reused: int = 0
    results: list[ArchiveCheckResult] = Field(default_factory=list)


class PickedMedia(BaseModel):
    provider_id: str
    filename: str
    mime_type: str
    base_url: str
    create_time: datetime | None = None
    width: int | None = None
    height: int | None = None
    duration: str | None = None
    media_type: str = "TYPE_UNSPECIFIED"

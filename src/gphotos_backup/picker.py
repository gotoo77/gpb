from __future__ import annotations

import hashlib
import mimetypes
import os
import random
import time
from pathlib import Path
from typing import Any

import httpx

from .auth import get_credentials
from .db import Database
from .models import LibraryConfig, PickedMedia, Summary
from .util import destination

API = "https://photospicker.googleapis.com/v1"


class PickerClient:
    def __init__(self, root: Path, transport: httpx.BaseTransport | None = None) -> None:
        self.root = root
        self.credentials = get_credentials(root)
        self.client = httpx.Client(
            timeout=httpx.Timeout(30.0, read=120.0),
            follow_redirects=True,
            transport=transport,
        )

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credentials.token}"}

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(5):
            response = self.client.request(method, url, headers=self.headers(), **kwargs)
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response
            if attempt == 4:
                response.raise_for_status()
            time.sleep(min(8.0, 0.5 * 2**attempt) + random.random() * 0.25)
        raise RuntimeError("unreachable")

    def create_session(self) -> dict[str, Any]:
        return dict(self.request("POST", f"{API}/sessions", json={}).json())

    def get_session(self, session_id: str) -> dict[str, Any]:
        return dict(self.request("GET", f"{API}/sessions/{session_id}").json())

    def list_items(self, session_id: str) -> list[PickedMedia]:
        items: list[PickedMedia] = []
        token: str | None = None
        while True:
            params = {"sessionId": session_id, "pageSize": "100"}
            if token:
                params["pageToken"] = token
            data = self.request("GET", f"{API}/mediaItems", params=params).json()
            for raw in data.get("mediaItems", []):
                media = raw["mediaFile"]
                metadata = media.get("mediaFileMetadata", {})
                items.append(
                    PickedMedia(
                        provider_id=raw["id"],
                        filename=media["filename"],
                        mime_type=media["mimeType"],
                        base_url=media["baseUrl"],
                        create_time=raw.get("createTime"),
                        width=metadata.get("width"),
                        height=metadata.get("height"),
                        duration=(metadata.get("videoMetadata") or {}).get("duration"),
                        media_type=raw.get("type", "TYPE_UNSPECIFIED"),
                    )
                )
            token = data.get("nextPageToken")
            if not token:
                return items


def content_url(item: PickedMedia) -> str:
    return f"{item.base_url}=dv" if item.media_type == "VIDEO" else f"{item.base_url}=d"


def download_session(
    session_id: str, config: LibraryConfig, db: Database, *, dry_run: bool = False
) -> Summary:
    client = PickerClient(config.library_root)
    summary = Summary()
    for item in client.list_items(session_id):
        summary.scanned += 1
        if db.by_provider("picker", item.provider_id):
            summary.already_local += 1
            continue
        if dry_run:
            summary.imported += 1
            continue
        partial_id = hashlib.sha256(item.provider_id.encode()).hexdigest()[:24]
        partial = config.library_root / ".gphotos-backup" / f"{partial_id}.partial"
        digest = hashlib.sha256()
        size = 0
        try:
            with client.client.stream(
                "GET", content_url(item), headers=client.headers(), follow_redirects=True
            ) as response:
                response.raise_for_status()
                expected = response.headers.get("content-length")
                with partial.open("wb") as output:
                    for block in response.iter_bytes(1024 * 1024):
                        output.write(block)
                        digest.update(block)
                        size += len(block)
                if expected is not None and size != int(expected):
                    raise OSError(f"Short download: expected {expected} bytes, received {size}")
            hexdigest = digest.hexdigest()
            if db.by_hash(hexdigest):
                summary.already_local += 1
                continue
            target = destination(config.library_root, item.filename, item.create_time, hexdigest)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(partial, target)
            db.add_media(
                {
                    "provider_id": item.provider_id,
                    "source": "picker",
                    "original_name": item.filename,
                    "local_path": str(target.relative_to(config.library_root)),
                    "mime_type": item.mime_type or mimetypes.guess_type(item.filename)[0],
                    "size": size,
                    "sha256": hexdigest,
                    "capture_time": item.create_time.isoformat() if item.create_time else None,
                    "remote_creation_time": item.create_time.isoformat()
                    if item.create_time
                    else None,
                    "width": item.width,
                    "height": item.height,
                    "download_status": "complete",
                    "metadata_provenance": "picker",
                }
            )
            summary.imported += 1
            summary.bytes_written += size
        except (OSError, httpx.HTTPError) as error:
            summary.failed += 1
            summary.warnings.append(f"{item.filename}: {error}")
        finally:
            partial.unlink(missing_ok=True)
    return summary

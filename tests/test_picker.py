from __future__ import annotations

from types import SimpleNamespace

import httpx

from gphotos_backup import picker
from gphotos_backup.config import load, write_config
from gphotos_backup.db import Database
from gphotos_backup.models import PickedMedia
from gphotos_backup.picker import PickerClient, content_url, download_session


def test_picker_content_parameters() -> None:
    photo = PickedMedia(
        provider_id="p", filename="p.jpg", mime_type="image/jpeg", base_url="https://x/p"
    )
    video = PickedMedia(
        provider_id="v",
        filename="v.mp4",
        mime_type="video/mp4",
        base_url="https://x/v",
        media_type="VIDEO",
    )
    assert content_url(photo).endswith("=d")
    assert content_url(video).endswith("=dv")


def test_http_mock_can_paginate() -> None:
    pages = {
        None: {"mediaItems": [{"id": "1"}], "nextPageToken": "next"},
        "next": {"mediaItems": [{"id": "2"}]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages.get(request.url.params.get("pageToken")))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    first = client.get("https://example.test", params={}).json()
    second = client.get("https://example.test", params={"pageToken": first["nextPageToken"]}).json()
    assert [first["mediaItems"][0]["id"], second["mediaItems"][0]["id"]] == ["1", "2"]


def test_picker_client_paginates_and_retries(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(picker, "get_credentials", lambda root: SimpleNamespace(token="safe-token"))
    monkeypatch.setattr(picker.time, "sleep", lambda seconds: None)
    calls = 0

    def item(identifier: str) -> dict[str, object]:
        return {
            "id": identifier,
            "type": "PHOTO",
            "mediaFile": {
                "filename": f"{identifier}.jpg",
                "mimeType": "image/jpeg",
                "baseUrl": f"https://media/{identifier}",
                "mediaFileMetadata": {"width": 10, "height": 20},
            },
        }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429)
        if request.url.params.get("pageToken") == "next":
            return httpx.Response(200, json={"mediaItems": [item("2")]})
        return httpx.Response(200, json={"mediaItems": [item("1")], "nextPageToken": "next"})

    client = PickerClient(tmp_path, transport=httpx.MockTransport(handler))
    assert [value.provider_id for value in client.list_items("session")] == ["1", "2"]
    assert calls == 3


def test_picker_download_reports_item_and_byte_progress(monkeypatch, tmp_path) -> None:
    root = tmp_path / "library"
    write_config(root)
    db = Database(root)
    db.initialize()
    item = PickedMedia(
        provider_id="photo",
        filename="photo.jpg",
        mime_type="image/jpeg",
        base_url="https://media/photo",
    )

    class Response:
        def __init__(self) -> None:
            self.headers = {"content-length": "6"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, _size: int):
            yield b"abc"
            yield b"def"

    class HttpClient:
        def stream(self, *_args, **_kwargs):
            return Response()

    class Client:
        client = HttpClient()

        def __init__(self, _root) -> None:
            pass

        def list_items(self, _session: str):
            return [item]

        def headers(self):
            return {"Authorization": "Bearer test"}

    monkeypatch.setattr(picker, "PickerClient", Client)
    events: list[tuple[int, int, int, int | None, str]] = []

    summary = download_session(
        "session",
        load(root),
        db,
        progress=lambda *event: events.append(event),
    )

    assert summary.imported == 1
    assert events[-1][:4] == (1, 1, 6, 6)
    assert "terminé" in events[-1][4]

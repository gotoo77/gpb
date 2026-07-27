from __future__ import annotations

from types import SimpleNamespace

import httpx

from gphotos_backup import picker
from gphotos_backup.models import PickedMedia
from gphotos_backup.picker import PickerClient, content_url


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

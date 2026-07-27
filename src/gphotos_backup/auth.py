from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"


def credentials_path(root: Path) -> Path:
    return root / ".gphotos-backup" / "credentials.json"


def token_path(root: Path) -> Path:
    return root / ".gphotos-backup" / "token.json"


def login(root: Path) -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError("OAuth dependencies are not installed; run `uv sync`.") from error
    path = credentials_path(root)
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {path}. Copy a Desktop OAuth client JSON there and chmod 600 it."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(path), [SCOPE])
    credentials = flow.run_local_server(port=0, open_browser=True)
    target = token_path(root)
    temporary = target.with_suffix(".partial")
    temporary.write_text(credentials.to_json(), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(target)


def get_credentials(root: Path) -> Any:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as error:
        raise RuntimeError("OAuth dependencies are not installed; run `uv sync`.") from error
    target = token_path(root)
    if not target.is_file():
        raise FileNotFoundError("Not authenticated. Run `gpb auth login`.")
    credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
        str(target), [SCOPE]
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        temporary = target.with_suffix(".partial")
        temporary.write_text(credentials.to_json(), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(target)
    if not credentials.valid:
        raise RuntimeError("OAuth token is invalid. Run `gpb auth login` again.")
    return credentials


def status(root: Path) -> dict[str, object]:
    path = token_path(root)
    if not path.exists():
        return {"authenticated": False, "token_path": str(path)}
    try:
        data = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        return {
            "authenticated": True,
            "token_path": str(path),
            "scopes": data.get("scopes", []),
            "permissions_ok": path.stat().st_mode & 0o077 == 0,
        }
    except (json.JSONDecodeError, OSError):
        return {"authenticated": False, "token_path": str(path), "error": "invalid token file"}

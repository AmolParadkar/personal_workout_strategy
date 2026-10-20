"""Minimal Supabase API client for integration tests. Reads keys from the .env files."""

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


_backend = _load_env(ROOT / "backend" / ".env")
_frontend = _load_env(ROOT / "frontend" / ".env")

URL = _backend.get("SUPABASE_URL", "").rstrip("/")
SECRET_KEY = _backend.get("SUPABASE_SECRET_KEY", "")
PUBLISHABLE_KEY = _frontend.get("EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "")
CONFIGURED = bool(URL and SECRET_KEY and PUBLISHABLE_KEY)


def call(
    method: str,
    path: str,
    key: str,
    token: str | None = None,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """Call the Supabase API and return (status code, parsed JSON body)."""
    request_headers = {"apikey": key, "Content-Type": "application/json"}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    request_headers.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(URL + path, method=method, headers=request_headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read()
            return response.status, json.loads(text) if text else None
    except urllib.error.HTTPError as error:
        text = error.read()
        try:
            return error.code, json.loads(text)
        except ValueError:
            return error.code, text

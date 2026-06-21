"""flightsim.to integration.

flightsim.to is a single-page app guarded by Cloudflare, and its public REST
API (``api.flightsim.to/v1``) needs a personal Bearer token; the one-click
auto-installer is a Premium feature. So LiftOff integrates in the ways that are
robust and work for everyone:

* **Downloads watcher** — spot freshly downloaded add-on archives and install
  them in one keystroke.
* **Browser hand-off** — open searches/categories on flightsim.to directly.
* **Optional API** — if the user pastes their own API token we use the official
  endpoints for in-app search and direct download. Kept best-effort and isolated
  so the rest of the app never depends on it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from .install import ARCHIVE_SUFFIXES

BASE_URL = "https://flightsim.to"
API_URL = "https://api.flightsim.to/v1"
USER_AGENT = "LiftOff/1.0 (+https://github.com/NilsBriggen/LiftOff)"


# ------------------------------------------------------------- browser hand-off
def search_url(query: str = "", category: str = "") -> str:
    if category:
        return f"{BASE_URL}/{category.strip('/')}"
    if query:
        return f"{BASE_URL}/search?search={urllib.parse.quote(query)}"
    return BASE_URL


def open_in_browser(url: str) -> bool:
    try:
        return webbrowser.open(url)
    except Exception:
        return False


# --------------------------------------------------------------- downloads scan
def find_downloads(downloads_dir: Path, limit: int = 100) -> list[Path]:
    """Return add-on archives in *downloads_dir*, newest first."""
    if not downloads_dir.is_dir():
        return []
    files = [
        p
        for p in downloads_dir.iterdir()
        if p.is_file() and p.suffix.lower() in ARCHIVE_SUFFIXES
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


# -------------------------------------------------------------- optional API
@dataclass
class RemoteFile:
    id: str
    title: str
    author: str = ""
    url: str = ""
    category: str = ""


class ApiError(Exception):
    """flightsim.to API problem (network, auth or unexpected response)."""


class FlightSimToClient:
    """Thin, defensive wrapper over the official flightsim.to API."""

    def __init__(self, token: str, timeout: float = 20.0):
        self.token = token.strip()
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _get(self, path: str, **params) -> dict:
        if not self.enabled:
            raise ApiError("No flightsim.to API token configured (see Settings).")
        url = f"{API_URL}/{path.lstrip('/')}"
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, "")}
            url += "?" + urllib.parse.urlencode(clean)
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.token}", "User-Agent": USER_AGENT,
                     "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ApiError("flightsim.to rejected the API token (401). Check Settings.") \
                    from exc
            raise ApiError(f"flightsim.to API error {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"Could not reach flightsim.to: {exc.reason}") from exc
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise ApiError("flightsim.to returned an unexpected response.") from exc
        if isinstance(data, dict) and data.get("error"):
            raise ApiError(str(data["error"]))
        return data if isinstance(data, dict) else {"data": data}

    @staticmethod
    def _normalise(item: dict) -> RemoteFile:
        fid = str(item.get("id") or item.get("file_id") or item.get("fileId") or "")
        author = item.get("author") or item.get("creator") or item.get("user") or ""
        if isinstance(author, dict):
            author = author.get("name") or author.get("username") or ""
        return RemoteFile(
            id=fid,
            title=str(item.get("title") or item.get("name") or "Untitled"),
            author=str(author),
            url=str(item.get("url") or (f"{BASE_URL}/file/{fid}" if fid else "")),
            category=str(item.get("category") or item.get("category_name") or ""),
        )

    def _files_from(self, data: dict) -> list[RemoteFile]:
        items = data.get("data") or data.get("files") or data.get("results") or []
        if isinstance(items, dict):
            items = list(items.values())
        return [self._normalise(it) for it in items if isinstance(it, dict)]

    def search(self, query: str, limit: int = 30) -> list[RemoteFile]:
        return self._files_from(self._get("files", search=query, limit=limit))

    def popular(self, limit: int = 30) -> list[RemoteFile]:
        return self._files_from(self._get("files/popular", limit=limit))

from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timezone

from .config import BASE_HEADERS


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FetchError(RuntimeError):
    pass


_MIN_BODY = 2000
_CF_MARKERS = ("Just a moment", "__cf_chl", "cf-chl", "challenge-platform")


def _is_challenge(body: str) -> bool:
    return any(m in body for m in _CF_MARKERS)


def fetch(url: str, *, headers: dict | None = None, retries: int = 3, delay: float = 1.5) -> str:
    """Fetch a URL, preferring curl (its TLS fingerprint passes Cloudflare bot
    detection, which httpx often fails). Falls back to httpx if curl is missing."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            body = _fetch_curl(url, headers)
            if body is not None and len(body) >= _MIN_BODY and not _is_challenge(body):
                return body
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        time.sleep(delay * (attempt + 1))
    if last_exc is not None:
        raise FetchError(f"failed to fetch {url}: {last_exc}") from last_exc
    raise FetchError(f"failed to fetch {url}: short or empty response")


def _fetch_curl(url: str, headers: dict | None = None) -> str | None:
    ua = BASE_HEADERS.get("User-Agent", "")
    cmd = [
        "curl",
        "-s",
        "--compressed",
        "-f",  # fail (non-zero rc) on HTTP errors, e.g. 403 challenge
        "-A", ua,
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: en-US,en;q=0.9",
    ]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None
    return r.stdout


def _fetch_httpx(url: str, headers: dict | None = None) -> str:
    import httpx

    client = httpx.Client(headers=BASE_HEADERS, follow_redirects=True, timeout=30.0, http2=False)
    try:
        h = dict(client.headers)
        if headers:
            h.update(headers)
        resp = client.get(url, headers=h)
        resp.raise_for_status()
        return resp.text
    finally:
        client.close()


def slugify(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name
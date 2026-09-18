from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import BASE_HEADERS

COOKIE_JAR = Path(__file__).resolve().parent.parent / ".fetch_cookies.json"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FetchError(RuntimeError):
    pass


_MIN_BODY = 2000
# Strong Cloudflare-challenge signals. "challenge-platform" is deliberately NOT
# included: after a challenge is solved, Cloudflare leaves a dead
# /cdn-cgi/challenge-platform script in the DOM, so that marker is present on
# pages that are otherwise perfectly loadable.
_CF_MARKERS = ("Just a moment", "__cf_chl", "cf-chl")


def _is_challenge(body: str) -> bool:
    return any(m in body for m in _CF_MARKERS)


def _host(url: str) -> str:
    return url.split("/")[2].split(":")[0]


def _load_cookies(url: str) -> str:
    """Return 'name=value; ...' Cookie header for cookies matching url's host."""
    host = _host(url)
    try:
        cookies = json.loads(COOKIE_JAR.read_text())
    except (OSError, ValueError):
        return ""
    now = time.time()
    pairs = []
    for c in cookies:
        if c.get("expiry") and c["expiry"] <= now:
            continue
        dom = (c.get("domain") or "").lstrip(".")
        if not dom or not (host == dom or host.endswith("." + dom)):
            continue
        if c.get("name") and c.get("value"):
            pairs.append(f"{c['name']}={c['value']}")
    return "; ".join(pairs)


def _save_cookies(url: str, cookies: list[dict]) -> None:
    """Merge Playwright context cookies for url's host into the jar."""
    host = _host(url)
    existing = []
    try:
        existing = json.loads(COOKIE_JAR.read_text())
    except (OSError, ValueError):
        pass
    keep = [c for c in existing if (c.get("domain") or "").lstrip(".") and
            host != (c.get("domain") or "").lstrip(".") and
            not host.endswith("." + (c.get("domain") or "").lstrip("."))]
    for c in cookies:
        dom = (c.get("domain") or "").lstrip(".")
        if dom and (host == dom or host.endswith("." + dom)) and c.get("name") and c.get("value"):
            keep.append({"name": c["name"], "value": c["value"],
                         "domain": c.get("domain", ""), "path": c.get("path", "/"),
                         "expiry": c.get("expires", 0) or c.get("expiry", 0)})
    try:
        COOKIE_JAR.write_text(json.dumps(keep))
    except OSError:
        pass


def fetch(url: str, *, headers: dict | None = None, retries: int = 3, delay: float = 1.5) -> str:
    """Fetch a URL, preferring curl (its TLS fingerprint passes Cloudflare bot
    detection, which httpx often fails). If every attempt returns empty or a
    Cloudflare JS challenge, fall back to a headless Firefox (Playwright),
    which passes the Turnstile challenge far more often than Chromium. Cloudflare
    intermittently opens a hostile window for a few minutes, so the browser path
    retries with growing backoff to wait it out."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            body = _fetch_curl(url, headers)
            if body is not None and len(body) >= _MIN_BODY and not _is_challenge(body):
                return body
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        time.sleep(delay * (attempt + 1))
    for i, backoff in enumerate((10, 45)):
        if i:
            time.sleep(backoff)
        body = _fetch_playwright(url, save_cookies=True)
        if body is not None and len(body) >= _MIN_BODY and not _is_challenge(body):
            return body
    if last_exc is not None:
        raise FetchError(f"failed to fetch {url}: {last_exc}") from last_exc
    raise FetchError(f"failed to fetch {url}: short or empty response")


def _fetch_curl(url: str, headers: dict | None = None) -> str | None:
    ua = BASE_HEADERS.get("User-Agent", "")
    cmd = [
        "curl",
        "-s",
        "--compressed",
        "-L",  # follow redirects (Flashscore match pages 307 to canonical slugs)
        "-f",  # fail (non-zero rc) on HTTP errors, e.g. 403 challenge
        "-A", ua,
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: en-US,en;q=0.9",
    ]
    cookies = _load_cookies(url)
    if cookies:
        cmd += ["-H", f"Cookie: {cookies}"]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None
    return r.stdout


def _fetch_playwright(url: str, *, save_cookies: bool = False) -> str | None:
    """Load a URL in a headless Firefox, waiting out any Cloudflare JS
    challenge. Polls until the page settles (content stable across consecutive
    samples) so JS-fed content has rendered. Resets the session if the page
    stays challenged (a fresh session has the best odds of passing Turnstile)."""
    context = _pw_session()
    if context is None:
        return None
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        deadline = time.monotonic() + 50
        solved = False
        last_body = ""
        stable = 0
        while time.monotonic() < deadline:
            body = page.content()
            if _is_challenge(body):
                stable = 0
            elif len(body) >= _MIN_BODY:
                solved = True
                if body == last_body:
                    stable += 1
                    if stable >= 3:
                        break
                else:
                    stable = 0
            last_body = body
            time.sleep(2.0)
        body = page.content() if solved else last_body
        if solved and len(body) >= _MIN_BODY:
            if save_cookies:
                try:
                    _save_cookies(url, context.cookies())
                except Exception:  # noqa: BLE001
                    pass
            return body
    except Exception:  # noqa: BLE001
        pass
    finally:
        page.close()
    _pw_reset()
    return None


_pw_playwright = None
_pw_browser = None
_pw_context = None


def _pw_session():
    """Return a process-wide persistent Playwright context backed by Firefox
    (its default fingerprint passes Cloudflare's invisible Turnstile far more
    reliably than headless Chromium)."""
    global _pw_playwright, _pw_browser, _pw_context
    if _pw_context is not None:
        return _pw_context
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        _pw_playwright = sync_playwright().start()
        _pw_browser = _pw_playwright.firefox.launch(headless=True)
        _pw_context = _pw_browser.new_context(
            user_agent=BASE_HEADERS.get("User-Agent", ""),
            locale="en-US",
        )
        return _pw_context
    except Exception:
        return None


def _pw_reset() -> None:
    global _pw_playwright, _pw_browser, _pw_context
    try:
        if _pw_context is not None:
            _pw_context.close()
        if _pw_browser is not None:
            _pw_browser.close()
        if _pw_playwright is not None:
            _pw_playwright.stop()
    except Exception:  # noqa: BLE001
        pass
    _pw_playwright = _pw_browser = _pw_context = None


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
"""Bookmaker odds via the ESPN public API (DraftKings + Bet365).

Scrapes per-event prices into data/raw/odds.csv, one snapshot per day
(re-running the same UTC day replaces that day's rows, older days are kept,
which gives us a free opening-line history for later CLV work).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import CANONICAL_DIR, ESPN, RAW_DIR
from .http import FetchError, fetch, slugify
from .storage import read_csv, write_csv

ODDS_PATH = RAW_DIR / "odds.csv"
ODDS_COLUMNS = [
    "fixture_id", "date", "home", "away", "league", "state",
    "provider", "market", "outcome", "odds", "line", "opened", "scraped_at",
]

_B365_KEYS = {
    "preMatchFullTimeResultHome": ("1x2", "1"),
    "preMatchFullTimeResultDraw": ("1x2", "X"),
    "preMatchFullTimeResultAway": ("1x2", "2"),
    "preMatchDoubleChanceHomeOrDraw": ("double_chance", "1X"),
    "preMatchDoubleChanceDrawOrAway": ("double_chance", "X2"),
    "preMatchDoubleChanceHomeOrAway": ("double_chance", "12"),
}


def american_to_decimal(a: float) -> float:
    a = float(a)
    return a / 100.0 + 1.0 if a > 0 else 100.0 / (-a) + 1.0


def fraction_to_decimal(value: str) -> float:
    """Bet365 quotes fractional strings like '23/20' or '4/6'."""
    value = str(value).strip()
    if "/" in value:
        num, den = value.split("/", 1)
        return float(num) / float(den) + 1.0
    return float(value)


def _fmt(x: float) -> str:
    return f"{x:.3f}"


def _dk_decimal(node: dict | None) -> float | None:
    """Current moneyline as decimal from a DraftKings odds node.

    The nested {current, open}.moneyLine objects carry an explicit `decimal`;
    the bare top-level `moneyLine` number is American.
    """
    if not isinstance(node, dict):
        return None
    cur = (node.get("current") or {}).get("moneyLine")
    if isinstance(cur, dict) and cur.get("decimal"):
        return float(cur["decimal"])
    ml = node.get("moneyLine")
    if isinstance(ml, dict):
        if ml.get("decimal"):
            return float(ml["decimal"])
        ml = ml.get("american") or ml.get("value")
    if ml is None:
        return None
    return american_to_decimal(float(ml))


def _dk_open(node: dict | None) -> float | None:
    if not isinstance(node, dict):
        return None
    op = (node.get("open") or {}).get("moneyLine")
    if isinstance(op, dict) and op.get("decimal"):
        return float(op["decimal"])
    return None


def parse_draftkings(item: dict) -> list[dict]:
    out: list[dict] = []

    def add(market: str, outcome: str, odds: float | None, line: str = "",
            opened: float | None = None) -> None:
        if odds and odds > 1.0:
            out.append({
                "provider": "DraftKings", "market": market, "outcome": outcome,
                "odds": _fmt(odds), "line": line,
                "opened": _fmt(opened) if opened and opened > 1.0 else "",
            })

    add("1x2", "1", _dk_decimal(item.get("homeTeamOdds")), opened=_dk_open(item.get("homeTeamOdds")))
    add("1x2", "X", _dk_decimal(item.get("drawOdds")))
    add("1x2", "2", _dk_decimal(item.get("awayTeamOdds")), opened=_dk_open(item.get("awayTeamOdds")))

    line = item.get("overUnder")
    if line:
        over, under = item.get("overOdds"), item.get("underOdds")
        if over is not None:
            add("over_under", "Over", american_to_decimal(float(over)), line=str(line))
        if under is not None:
            add("over_under", "Under", american_to_decimal(float(under)), line=str(line))
    return out


def parse_bet365(item: dict) -> list[dict]:
    out: list[dict] = []
    team = (item.get("bettingOdds") or {}).get("teamOdds") or {}
    for key, (market, outcome) in _B365_KEYS.items():
        node = team.get(key)
        if not isinstance(node, dict) or not node.get("value"):
            continue
        try:
            odds = fraction_to_decimal(node["value"])
        except (TypeError, ValueError):
            continue
        if odds > 1.0:
            out.append({
                "provider": "Bet365", "market": market, "outcome": outcome,
                "odds": _fmt(odds), "line": "", "opened": "",
            })
    return out


def parse_provider(item: dict) -> list[dict]:
    name = (item.get("provider") or {}).get("name", "")
    if name == "DraftKings":
        return parse_draftkings(item)
    if name == "Bet 365":
        return parse_bet365(item)
    return []


def match_fixture(home: str, away: str, date: str, fixtures: set[str],
                  aliases: dict[tuple[str, str], str]) -> str | None:
    """Map an ESPN event onto a canonical fixture_id (date|home|vs|away).

    Tries the event's UTC date first, then ±1 day for late kickoffs. Team
    names resolve through aliases.csv (site='espn') with slugify fallback.
    """
    home_id = aliases.get(("espn", home)) or slugify(home)
    away_id = aliases.get(("espn", away)) or slugify(away)
    day = datetime.fromisoformat(date).date()
    for delta in (0, -1, 1):
        fid = f"{(day + timedelta(days=delta)).isoformat()}|{home_id}|vs|{away_id}"
        if fid in fixtures:
            return fid
    return None


def _event_teams(event: dict) -> tuple[str, str]:
    comps = event.get("competitions") or [{}]
    home = away = ""
    for c in comps[0].get("competitors") or []:
        name = ((c.get("team") or {}).get("displayName")) or ""
        if c.get("homeAway") == "home":
            home = name
        elif c.get("homeAway") == "away":
            away = name
    return home, away


def _espn(url: str, retries: int = 2) -> dict | None:
    """Curl-only JSON fetch for the ESPN APIs (never Cloudflare-challenged).

    Many far-future events have no odds yet - a 404 or an empty {"count":0}
    payload is a normal answer there, not a retry-worthy failure, so the
    Playwright fallback would just burn minutes. Returns None on any miss.
    """
    try:
        data = json.loads(fetch(url, retries=retries, delay=0.5, browser=False, min_body=2))
    except (FetchError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def scrape(date: str | None = None) -> list[dict]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = date or now[:10]
    fixtures = {r["fixture_id"] for r in read_csv(CANONICAL_DIR / "fixtures.csv")}
    aliases = {
        (r["site"], r["team_name"]): r["canonical_id"]
        for r in read_csv(CANONICAL_DIR / "aliases.csv")
    }

    rows: list[dict] = []
    unmatched: list[tuple[str, str, str]] = []
    failed = 0
    for slug in ESPN["leagues"]:
        url = ESPN["scoreboard"].format(league=slug) + f"?dates={day.replace('-', '')}"
        board = _espn(url, retries=3)
        if board is None:
            failed += 1
            continue
        for event in board.get("events") or []:
            state = ((event.get("status") or {}).get("type") or {}).get("state")
            if state == "final":
                continue
            home, away = _event_teams(event)
            if not home or not away:
                continue
            event_date = (event.get("date") or day)[:10]
            odds = _espn(ESPN["odds"].format(league=slug, event=event["id"]))
            if odds is None:
                continue
            parsed: list[dict] = []
            for item in odds.get("items") or []:
                parsed.extend(parse_provider(item))
            if not parsed:
                continue
            fid = match_fixture(home, away, event_date, fixtures, aliases)
            if not fid:
                unmatched.append((home, away, event_date))
            for r in parsed:
                rows.append({
                    "fixture_id": fid or "", "date": event_date,
                    "home": home, "away": away, "league": slug,
                    "state": state or "",
                    **r, "scraped_at": now,
                })
    if unmatched:
        for home, away, d in unmatched:
            print(f"  no fixture match: {d} {home} vs {away}")
    if failed:
        print(f"  {day}: {failed} league scoreboards failed to fetch")
    return rows


def save_odds(rows: list[dict], path: Path | None = None) -> None:
    """Append today's snapshot, replacing any earlier snapshot from the same day."""
    path = path or ODDS_PATH
    today = max((r.get("scraped_at") or "")[:10] for r in rows) if rows else None
    keep = [
        r for r in read_csv(path)
        if not today or (r.get("scraped_at") or "")[:10] != today
    ]
    write_csv(path, keep + rows, ODDS_COLUMNS)


def load_odds(date: str | None = None, path: Path | None = None) -> list[dict]:
    """All stored price rows, or just one snapshot day (scraped_at date) if given.

    No date means the full history: every snapshot day, in scrape order.
    build_ev collapses it to the latest price per bet, so keeping older days
    is how we bank opening lines for later CLV comparison.
    """
    path = path or ODDS_PATH
    rows = read_csv(path)
    if date is None:
        return rows
    return [r for r in rows if (r.get("scraped_at") or "").startswith(date)]


def rebind(path: Path | None = None) -> int:
    """Attach stored odds rows to fixtures that didn't exist when they were
    scraped (ESPN lists next week's games with prices before our site scrapes
    create the fixture). Returns how many rows newly bound."""
    path = path or ODDS_PATH
    rows = read_csv(path)
    fixtures = {r["fixture_id"] for r in read_csv(CANONICAL_DIR / "fixtures.csv")}
    aliases = {
        (r["site"], r["team_name"]): r["canonical_id"]
        for r in read_csv(CANONICAL_DIR / "aliases.csv")
    }
    n = 0
    for r in rows:
        if r.get("fixture_id"):
            continue
        fid = match_fixture(r.get("home") or "", r.get("away") or "",
                            r.get("date") or "", fixtures, aliases)
        if fid:
            r["fixture_id"] = fid
            n += 1
    if n:
        write_csv(path, rows, ODDS_COLUMNS)
    return n

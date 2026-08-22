from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..config import SPORTYTRADER, is_top_league
from ..http import fetch, utcnow

_REQUEST_DELAY = 1.0

_DATE_RE = re.compile(r"^(\d{1,2}) (\w{3}) (\d{4}), (\d{2}:\d{2})$")

_OU_RE = re.compile(r"^(over|under)\s+(\d+(?:\.\d+)?)\s+goals$", re.IGNORECASE)
_WIN_RE = re.compile(r"^(.+?)\s+(?:to\s+)?wins?$", re.IGNORECASE)
_COMPOUND_RE = re.compile(
    r"^(?P<a>.+?)\s*(?:&|and)\s*(?P<b>BTTS|(?:over|under)\s+\d+(?:\.\d+)?\s+goals)$",
    re.IGNORECASE,
)


def _sleep() -> None:
    time.sleep(_REQUEST_DELAY)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _team_match(team: str, home: str, away: str) -> str | None:
    """Resolve a tip's team mention to 'home'/'away'/None (containment-tolerant)."""
    t = _norm(team).lower()
    h = _norm(home).lower()
    a = _norm(away).lower()
    if not t:
        return None

    def same(x: str, y: str) -> bool:
        return bool(x) and bool(y) and (x == y or x in y or y in x)

    th, ta = same(t, h), same(t, a)
    if th and not ta:
        return "home"
    if ta and not th:
        return "away"
    return None


def parse_pick(tip: str, home: str, away: str) -> list[tuple[str, str]]:
    """Map a sportytrader tip string to (market, pick) pairs; [] if unmappable."""
    tip = _norm(tip)

    def ou(pick: str) -> tuple[str, str]:
        return ("over_under", pick)

    m = _OU_RE.match(tip)
    if m:
        return [ou(m.group(1).capitalize())]

    low = tip.lower()
    if low == "btts":
        return [("btts", "Yes")]
    if low in ("btts: no", "no btts"):
        return [("btts", "No")]

    comp = _COMPOUND_RE.match(tip)
    if comp:
        a, b = comp.group("a").strip(), comp.group("b").strip()
        out: list[tuple[str, str]] = []
        if a.lower() == "draw":
            out.append(("1x2", "X"))
        else:
            side = _team_match(a, home, away)
            if side:
                out.append(("1x2", "1" if side == "home" else "2"))
        mb = _OU_RE.match(b)
        if mb:
            out.append(ou(mb.group(1).capitalize()))
        elif b.lower() == "btts":
            out.append(("btts", "Yes"))
        return out

    if low == "draw":
        return [("1x2", "X")]

    win = _WIN_RE.match(tip)
    if win:
        side = _team_match(win.group(1), home, away)
        if side:
            return [("1x2", "1" if side == "home" else "2")]

    # double chance, HT/FT, handicaps, team totals, "to nil", ...
    return []


def parse_card(card) -> dict | None:
    """Extract fixture + tip metadata from one card element."""
    url = card.get("data-navigation-url-value") or ""
    m = re.search(r"/en/betting-tips/([a-z0-9-]+)-(\d+)/?$", url)
    if not m:
        return None

    league = ""
    for p in card.select("p.text-sm"):
        t = _norm(p.get_text())
        if " - " in t and "," not in t:
            league = t.split(" - ", 1)[1]
            break

    date_p = card.select_one("p.font-bold")
    date = kickoff = ""
    if date_p:
        dm = _DATE_RE.match(_norm(date_p.get_text()))
        if dm:
            try:
                dt = datetime.strptime(
                    f"{dm.group(1)} {dm.group(2)} {dm.group(3)} {dm.group(4)}",
                    "%d %b %Y %H:%M",
                )
                date = dt.strftime("%Y-%m-%d")
                kickoff = dt.strftime("%H:%M")
            except ValueError:
                pass
    if not date:
        return None

    teams = [_norm(s.get_text()) for s in card.select("span.font-semibold")]
    if len(teams) < 2 or not all(teams[:2]):
        return None

    tip_box = card.select_one("div.bg-gray-100")
    tip = ""
    odds = ""
    if tip_box:
        ps = tip_box.select("p")
        if ps:
            tip = _norm(ps[-1].get_text())
        odds_el = tip_box.select_one(".tabular-nums")
        if odds_el:
            odds = _norm(odds_el.get_text())

    return {
        "source_id": f"{m.group(1)}-{m.group(2)}",
        "league": league,
        "date": date,
        "kickoff": kickoff,
        "home_team": teams[0],
        "away_team": teams[1],
        "tip": tip,
        "odds": odds,
    }


def scrape(leagues_only: bool = True, horizon_days: int = 5) -> list[dict]:
    base = SPORTYTRADER["base"]
    now = utcnow()
    today = datetime.now(timezone.utc).date()
    rows: list[dict] = []

    _sleep()
    html = fetch(base + SPORTYTRADER["today"])
    soup = BeautifulSoup(html, "html.parser")

    seen: set[str] = set()
    for card in soup.select("div.card[data-navigation-url-value]"):
        parsed = parse_card(card)
        if not parsed or parsed["source_id"] in seen:
            continue
        seen.add(parsed["source_id"])

        if leagues_only and not is_top_league("sportytrader", parsed["league"]):
            continue
        try:
            d = datetime.strptime(parsed["date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        delta = (d - today).days
        if delta < -1 or delta > horizon_days:
            continue

        picks = parse_pick(parsed["tip"], parsed["home_team"], parsed["away_team"])
        note = f"{parsed['tip']} @ {parsed['odds']}".strip(" @")
        for market, pick in picks:
            rows.append({
                "site": "sportytrader",
                **{k: parsed[k] for k in (
                    "source_id", "league", "date", "kickoff",
                    "home_team", "away_team")},
                "market": market,
                "pick": pick,
                "p1": "",
                "p2": "",
                "p3": "",
                "note": note,
                "scraped_at": now,
            })
    return rows

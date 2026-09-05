from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..config import EAGLEPREDICT
from ..http import FetchError, fetch, utcnow

_DAY_RE = re.compile(
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*-\s*(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4})\b"
)
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def _parse_date(text: str) -> str:
    m = _DAY_RE.search(text)
    if not m:
        return ""
    day, mon, year = m.groups()
    return f"{year}-{_MONTHS[mon]:02d}-{int(day):02d}"


def _find_container(header) -> object | None:
    sib = header.find_next_sibling()
    while sib is not None:
        if sib.name == "div" and "flex-col" in (sib.get("class") or []):
            return sib
        sib = sib.find_next_sibling()
    return None


def parse_card(card) -> dict:
    grid = card.select_one("div[data-f-id]")
    fid = grid["data-f-id"] if grid and grid.get("data-f-id") else ""
    time_el = card.select_one('div[class*="md:hidden"] > div[class*="items-center"]')
    home_el = grid.select_one("div.ml-auto.text-right") if grid else None
    away_cols = grid.select('div[class*="col-span-4"]') if grid else []
    away_el = away_cols[-1].select_one("div") if away_cols else None
    score_el = grid.select_one("div.text-center") if grid else None
    pred_el = card.select_one("span.btn-prediction-calendar")
    odds_el = card.select_one('a[class*="text-success"]')
    link = card.select_one("a[href*='/predictions/match/']")
    return {
        "source_id": fid,
        "home_team": home_el.get_text(strip=True) if home_el else "",
        "away_team": away_el.get_text(strip=True) if away_el else "",
        "kickoff": time_el.get_text(strip=True) if time_el else "",
        "score": score_el.get_text(" ", strip=True) if score_el else "",
        "pick": pred_el.get_text(" ", strip=True) if pred_el else "",
        "odds": odds_el.get_text(strip=True) if odds_el else "",
        "url": link["href"] if link and link.get("href") else "",
    }


def parse_league(html: str) -> list[dict]:
    """Parse a per-league predictions page into raw match cards.

    League pages list each fixture once with its *main* prediction, which may
    be a win tip, a total-goals tip, BTTS, a double chance, etc. Each matchday
    (usually one section per day) looks like:

        <div class="... bg-primary/30 cursor-pointer card">Premier League Sat - 05 Sep 2026</div>
        <div class="flex flex-col gap-4">
          <div class="card bg-base-300 p-4">...pick...</div>
        </div>

    Unlike the homepage, every league is fully expanded here — collapsed sections
    render client-side (Alpine.js) so their cards never exist in the fetched HTML.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for header in soup.select('div[class*="bg-primary/30"]'):
        container = header.find_next_sibling()
        if container is None or container.name != "div" or "flex-col" not in (container.get("class") or []):
            continue
        header_text = header.get_text(" ", strip=True)
        league = _DAY_RE.sub("", header_text).strip()
        date = _parse_date(header_text)
        if not league or not date:
            continue
        for card in container.select("div.card.bg-base-300.p-4"):
            row = parse_card(card)
            if not row["source_id"]:
                continue
            row["league"] = league
            row["date"] = date
            out.append(row)
    return out


def map_pick(row: dict) -> list[tuple[str, str]]:
    """Map a league page's main prediction onto (market, pick) rows the pipeline knows.

    Prediction styles seen on the site:
      "{Team} Win"                          -> 1x2
      "Double Chance: X or Y"               -> double_chance (normalized in normalize.py)
      "Over/Under N Goals"                  -> over_under
      "BTTS - Yes"/"BTTS - No"              -> btts
    """
    pick = (row.get("pick") or "").strip()
    low = pick.lower()
    if not pick:
        return []
    if low.endswith("win"):
        return [("1x2", pick)]
    if low.startswith("double chance"):
        return [("double_chance", pick)]
    if "goal" in low:
        if low.startswith("over"):
            return [("over_under", pick)]
        if low.startswith("under"):
            return [("over_under", pick)]
    if low.startswith("btss") or low.startswith("btts"):
        return [("btts", "BTTS - No" if "no" in low else "BTTS - Yes")]
    if "both teams to score" in low:
        return [("btts", "BTTS - Yes" if low.endswith("yes") else "BTTS - No")]
    return []


def parse_market(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for anchor in soup.select("a[href*='/predictions/league/']"):
        header = anchor.find_parent("div", class_="card")
        if not header:
            continue
        league_el = anchor.select_one("div.flex.items-center.gap-2")
        league = league_el.get_text(" ", strip=True) if league_el else ""
        date = _parse_date(header.get_text(" ", strip=True))
        container = _find_container(header)
        if container is None:
            continue
        for card in container.select("div.card.bg-base-300.p-4"):
            row = parse_card(card)
            row["league"] = league
            row["date"] = date
            out.append(row)
    return out


def scrape(leagues_only: bool = True) -> list[dict]:
    """Scrape each top league's page for main predictions per match.

    The per-market pages (/predictions/straight-win/, /predictions/over-25-goals/,
    /predictions/both-teams-to-score/) only carry a rolling today-window of
    fixtures, which frequently contains no top-league matches. The league pages
    list every scheduled fixture once with whichever market the tipster actually
    picked, and (unlike the homepage) have no client-side collapsed sections.
    """
    import time

    from ..config import is_top_league

    base = EAGLEPREDICT["base"]
    now = utcnow()
    rows: list[dict] = []
    for cfg in EAGLEPREDICT["leagues"]:
        time.sleep(2.0)
        try:
            html = fetch(base + cfg["url"])
        except FetchError:
            print(f"eaglepredict: skipping {cfg['name']} (fetch failed)")
            continue
        for r in parse_league(html):
            if leagues_only and not is_top_league("eaglepredict", r["league"]):
                continue
            for market, pick in map_pick(r):
                if not pick:
                    continue
                rows.append({
                    "site": "eaglepredict",
                    "source_id": r["source_id"],
                    "league": r["league"],
                    "date": r["date"],
                    "kickoff": r["kickoff"],
                    "home_team": r["home_team"],
                    "away_team": r["away_team"],
                    "market": market,
                    "pick": pick,
                    "p1": "", "p2": "", "p3": "",
                    "note": r["odds"],
                    "scraped_at": now,
                })
    return rows
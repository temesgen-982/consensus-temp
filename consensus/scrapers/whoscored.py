from __future__ import annotations

import json
import re
import time
from datetime import datetime

from bs4 import BeautifulSoup

from ..config import WHOSCORED
from ..http import fetch, utcnow

_FIXTURES_RE = re.compile(
    r'href="(/regions/\d+/tournaments/\d+/seasons/\d+/stages/\d+/fixtures/[^"]+)"'
)
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
_REQUEST_DELAY = 4.0


def _sleep() -> None:
    time.sleep(_REQUEST_DELAY)


def fixtures_url(league_html: str) -> str:
    m = _FIXTURES_RE.search(league_html)
    return m.group(1) if m else ""


def _parse_date(day: str) -> str:
    # e.g. "Saturday, Aug 15 2026"
    m = re.search(r"([A-Z][a-z]{2}) (\d{1,2}),? (\d{4})", day)
    if not m:
        return ""
    mon, d, y = m.groups()
    return f"{y}-{_MONTHS[mon]:02d}-{int(d):02d}"


def parse_fixtures(html: str) -> list[dict]:
    """Parse the league fixtures page -> matches with preview availability."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for header in soup.select('div[class*="Accordion-module_header"]'):
        day_el = header.select_one("div > span")
        if not day_el:
            continue
        date = _parse_date(day_el.get_text(strip=True))
        container = header.find_next_sibling()
        if container is None:
            continue
        for match in container.select('div[class*="Match-module_match"]'):
            time_el = match.select_one('span[class*="Match-module_startTime"]')
            teams = match.select('a[class*="Match-module_teamNameText"]')
            id_el = match.select_one("a[id^='scoresBtn-']")
            preview_el = match.select_one("a[id^='previewBtn-']")
            if not id_el:
                continue
            mid = re.search(r"-(\d+)$", id_el.get("id", ""))
            if not mid:
                continue
            home = teams[0].get_text(strip=True) if len(teams) > 0 else ""
            away = teams[1].get_text(strip=True) if len(teams) > 1 else ""
            out.append({
                "source_id": mid.group(1),
                "date": date,
                "kickoff": time_el.get_text(strip=True) if time_el else "",
                "home_team": home,
                "away_team": away,
                "preview": preview_el.get("href") if preview_el else "",
            })
    return out


def parse_scores(html: str) -> list[dict]:
    """Parse a league fixtures page -> finished matches with final scores."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for header in soup.select('div[class*="Accordion-module_header"]'):
        day_el = header.select_one("div > span")
        date = _parse_date(day_el.get_text(strip=True)) if day_el else ""
        container = header.find_next_sibling()
        if container is None:
            continue
        for match in container.select('div[class*="Match-module_match"]'):
            ft = match.select_one('span[class*="Match-module_FT"]')
            if ft is None:
                continue
            id_el = match.select_one("a[id^='scoresBtn-']")
            if not id_el:
                continue
            mid = re.search(r"-(\d+)$", id_el.get("id", ""))
            if not mid:
                continue
            spans = id_el.select("span")
            if len(spans) < 2:
                continue
            home_goals = spans[0].get_text(strip=True)
            away_goals = spans[1].get_text(strip=True)
            if home_goals == "-" or away_goals == "-":
                continue
            teams = match.select('a[class*="Match-module_teamNameText"]')
            time_el = match.select_one('span[class*="Match-module_startTime"]')
            out.append({
                "source_id": mid.group(1),
                "date": date,
                "kickoff": time_el.get_text(strip=True) if time_el else "",
                "home_team": teams[0].get_text(strip=True) if len(teams) > 0 else "",
                "away_team": teams[1].get_text(strip=True) if len(teams) > 1 else "",
                "home_goals": home_goals,
                "away_goals": away_goals,
            })
    return out


def parse_prediction(html: str) -> dict:
    """Parse a match preview page -> predicted scoreline + odds."""
    soup = BeautifulSoup(html, "lxml")
    pred = soup.select_one("#preview-prediction")
    home = away = ""
    if pred:
        scores = pred.select("span.predicted-score")
        if len(scores) > 0:
            home = scores[0].get_text(strip=True)
        if len(scores) > 1:
            away = scores[1].get_text(strip=True)

    odds: dict[str, str] = {}
    for script in soup.select('script[data-hypernova-key="matchodds"]'):
        m = re.search(r"<!--(.*?)-->", script.string or "", re.S)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except (ValueError, KeyError):
            continue
        for bet in data.get("bets", []):
            offers = bet.get("offers", [])
            if offers:
                best = min(offers, key=lambda o: float(o["oddsDecimal"]))
                odds[bet["betName"]] = best["oddsDecimal"]

    return {"home_goals": home, "away_goals": away, "odds": odds}


def scrape(leagues_only: bool = True) -> list[dict]:
    base = WHOSCORED["base"]
    now = utcnow()
    rows: list[dict] = []

    for league in WHOSCORED["leagues"]:
        _sleep()
        league_html = fetch(base + league["url"], retries=6, delay=3.0)
        fix_url = fixtures_url(league_html)
        if not fix_url:
            continue

        _sleep()
        fixtures = parse_fixtures(fetch(base + fix_url, retries=10, delay=4.0))

        for fx in fixtures:
            if not fx["preview"]:
                continue
            _sleep()
            try:
                pred = parse_prediction(fetch(base + fx["preview"]))
            except Exception:  # noqa: BLE001
                continue
            hg = pred["home_goals"]
            ag = pred["away_goals"]
            if not hg and not ag:
                continue

            common = {
                "site": "whoscored",
                "source_id": fx["source_id"],
                "league": league["name"],
                "date": fx["date"],
                "kickoff": fx["kickoff"],
                "home_team": fx["home_team"],
                "away_team": fx["away_team"],
                "scraped_at": now,
            }
            odds = pred["odds"]

            # 1X2
            pick_1x2 = "1" if int(hg) > int(ag) else ("X" if int(hg) == int(ag) else "2")
            win_label = {"1": "Home win", "X": "Draw", "2": "Away win"}[pick_1x2]
            rows.append({
                **common,
                "market": "1x2",
                "pick": pick_1x2,
                "p1": "", "p2": "", "p3": "",
                "note": odds.get(win_label, ""),
            })

            # Over/Under 2.5 from predicted total
            total = int(hg) + int(ag)
            pick_ou = "Over" if total >= 3 else "Under"
            ou_label = "Over 2.5 goals" if pick_ou == "Over" else "Under 2.5 goals"
            rows.append({
                **common,
                "market": "over_under",
                "pick": pick_ou,
                "p1": "", "p2": "", "p3": "",
                "note": odds.get(ou_label, ""),
            })

            # BTTS from predicted scoreline
            pick_btts = "Yes" if int(hg) > 0 and int(ag) > 0 else "No"
            rows.append({
                **common,
                "market": "btts",
                "pick": pick_btts,
                "p1": "", "p2": "", "p3": "",
                "note": "",
            })

            # Correct score
            rows.append({
                **common,
                "market": "correct_score",
                "pick": f"{hg} - {ag}",
                "p1": "", "p2": "", "p3": "",
                "note": odds.get(f"{hg}-{ag}", ""),
            })
    return rows
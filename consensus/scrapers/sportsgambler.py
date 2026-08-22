from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..config import SPORTSGAMBLER
from ..http import fetch, utcnow
from ..markets import derive_from_score

_REQUEST_DELAY = 2.0

_SLUG_RE = re.compile(r"^/betting-tips/football/(.+)-prediction-lineups-odds-(\d{4}-\d{2}-\d{2})/$")


def _sleep() -> None:
    time.sleep(_REQUEST_DELAY)


def parse_league(html: str) -> list[dict]:
    """Extract fixture links from a league predictions listing page."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for a in soup.select("a.betlist-item"):
        href = a.get("href") or ""
        m = _SLUG_RE.match(href)
        if not m:
            continue
        teams = [s.get_text(" ", strip=True) for s in a.select(".betlist-teams span")]
        if len(teams) != 2 or not all(teams):
            continue
        kickoff = ""
        td = a.select_one(".timedate")
        if td:
            kickoff = re.sub(r"\s+", " ", td.get_text(" ", strip=True))
            kickoff = re.sub(r"^[^0-9]*", "", kickoff).strip()
        out.append({
            "source_id": m.group(1),
            "date": m.group(2),
            "home_team": teams[0],
            "away_team": teams[1],
            "kickoff": kickoff,
            "path": href,
        })
    return out


def parse_match(html: str) -> dict:
    """Pull the correct-score board and the main tip from a match page."""
    soup = BeautifulSoup(html, "html.parser")
    out = {"home_goals": "", "away_goals": "", "main_tip": ""}

    boxes = soup.select(".correct-score .cs-score-box")
    if len(boxes) >= 3:
        hg, ag = boxes[0].get_text(strip=True), boxes[2].get_text(strip=True)
        if hg.isdigit() and ag.isdigit():
            out["home_goals"] = hg
            out["away_goals"] = ag

    tip = soup.select_one("a.tpbot_tip span")
    if tip:
        out["main_tip"] = re.sub(r"\s+", " ", tip.get_text(" ", strip=True))

    return out


def scrape(leagues_only: bool = True, horizon_days: int = 5) -> list[dict]:
    base = SPORTSGAMBLER["base"]
    now = utcnow()
    today = datetime.now(timezone.utc).date()
    rows: list[dict] = []

    for league in SPORTSGAMBLER["leagues"]:
        _sleep()
        try:
            league_html = fetch(base + league["url"])
        except Exception:  # noqa: BLE001
            continue
        fixtures = parse_league(league_html)

        for fx in fixtures:
            try:
                d = datetime.strptime(fx["date"], "%Y-%m-%d").date()
            except ValueError:
                continue
            delta = (d - today).days
            if delta < -1 or delta > horizon_days:
                continue

            _sleep()
            try:
                match_html = fetch(base + fx["path"])
            except Exception:  # noqa: BLE001
                continue
            pred = parse_match(match_html)
            if not pred["home_goals"] and not pred["away_goals"]:
                continue

            hg, ag = int(pred["home_goals"]), int(pred["away_goals"])
            common = {
                "site": "sportsgambler",
                "source_id": fx["source_id"],
                "league": league["name"],
                "date": fx["date"],
                "kickoff": fx["kickoff"],
                "home_team": fx["home_team"],
                "away_team": fx["away_team"],
                "p1": "",
                "p2": "",
                "p3": "",
                "note": pred["main_tip"],
                "scraped_at": now,
            }
            rows.append({
                **common,
                "market": "correct_score",
                "pick": f"{pred['home_goals']} - {pred['away_goals']}",
            })
            for market, pick in derive_from_score(hg, ag).items():
                rows.append({**common, "market": market, "pick": pick})
    return rows

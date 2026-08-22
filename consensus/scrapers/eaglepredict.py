from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..config import EAGLEPREDICT
from ..http import fetch, utcnow

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
    from ..config import is_top_league

    base = EAGLEPREDICT["base"]
    straight = parse_market(fetch(base + EAGLEPREDICT["straight_win"]))
    over_under = parse_market(fetch(base + EAGLEPREDICT["over_under"]))
    btts = parse_market(fetch(base + EAGLEPREDICT["both_to_score"]))

    st = {r["source_id"]: r for r in straight}
    ou = {r["source_id"]: r for r in over_under}
    bt = {r["source_id"]: r for r in btts}

    now = utcnow()
    rows: list[dict] = []
    for source_id in {**st, **ou, **bt}:
        r = st.get(source_id) or ou.get(source_id) or bt.get(source_id)
        if leagues_only and not is_top_league("eaglepredict", r["league"]):
            continue
        common = {
            "site": "eaglepredict",
            "source_id": source_id,
            "league": r["league"],
            "date": r["date"],
            "kickoff": r["kickoff"],
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "scraped_at": now,
        }
        sr = st.get(source_id)
        if sr and sr["pick"]:
            rows.append({
                **common,
                "market": "1x2",
                "pick": sr["pick"],
                "p1": "", "p2": "", "p3": "",
                "note": sr["odds"],
            })
        ou_r = ou.get(source_id)
        if ou_r and ou_r["pick"] and ou_r["pick"].lower().startswith(("over", "under")):
            rows.append({
                **common,
                "market": "over_under",
                "pick": ou_r["pick"],
                "p1": "", "p2": "", "p3": "",
                "note": ou_r["odds"],
            })
        bt_r = bt.get(source_id)
        if bt_r and bt_r["pick"] in ("BTTS - Yes", "BTTS - No"):
            rows.append({
                **common,
                "market": "btts",
                "pick": bt_r["pick"],
                "p1": "", "p2": "", "p3": "",
                "note": bt_r["odds"],
            })
    return rows
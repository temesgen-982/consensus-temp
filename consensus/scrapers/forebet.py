from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..config import FOREBET
from ..http import fetch, utcnow

_LEAGUE_RE = re.compile(r"getstag\(this,\d+,'[^']*','([^']*)'")


def _row_fid(row) -> str | None:
    fav = row.select_one("div.fav_icon")
    if fav and fav.get("id"):
        return fav["id"]
    link = row.select_one("a.tnmscn")
    if link and link.get("href"):
        m = re.search(r"-(\d+)$", link["href"])
        if m:
            return m.group(1)
    return None


def _league(row) -> str:
    m = _LEAGUE_RE.search(str(row))
    return m.group(1) if m else ""


def _row_meta(row) -> dict:
    home_el = row.select_one("span.homeTeam span[itemprop='name']") or row.select_one("span.homeTeam")
    away_el = row.select_one("span.awayTeam span[itemprop='name']") or row.select_one("span.awayTeam")
    time_el = row.select_one("time[datetime]")
    kick_el = row.select_one("span.date_bah")
    return {
        "source_id": _row_fid(row) or "",
        "league": _league(row),
        "home_team": home_el.get_text(strip=True) if home_el else "",
        "away_team": away_el.get_text(strip=True) if away_el else "",
        "date": time_el["datetime"].strip() if time_el and time_el.get("datetime") else "",
        "kickoff": kick_el.get_text(strip=True) if kick_el else "",
    }


def _probs(row) -> list[str]:
    fprc = row.select_one("div.fprc")
    if fprc is None:
        return []
    return [s.get_text(strip=True) for s in fprc.select("span")]


def parse_predictions(html: str) -> dict:
    """Parse the 1X2 predictions list page -> {fid: {meta, p1,p2,p3,pick,cs,avg}}."""
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, dict] = {}
    for row in soup.select("div.rcnt"):
        fid = _row_fid(row)
        if not fid:
            continue
        meta = _row_meta(row)
        probs = _probs(row)
        pred_el = row.select_one("div[class*='predict'] span.forepr")
        cs_el = row.select_one(".ex_sc.tabonly") or row.select_one("span.scrmobpred.ex_sc")
        avg_el = row.select_one(".avg_sc")
        out[fid] = {
            **meta,
            "p1": probs[0] if len(probs) > 0 else "",
            "p2": probs[1] if len(probs) > 1 else "",
            "p3": probs[2] if len(probs) > 2 else "",
            "pick": pred_el.get_text(strip=True) if pred_el else "",
            "cs": cs_el.get_text(" ", strip=True) if cs_el else "",
            "avg": avg_el.get_text(strip=True) if avg_el else "",
        }
    return out


def parse_market(html: str) -> dict:
    """Parse an O/U or BTTS list page -> {fid: {p1,p2,pick}} (two-way market)."""
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, dict] = {}
    for row in soup.select("div.rcnt"):
        fid = _row_fid(row)
        if not fid:
            continue
        probs = _probs(row)
        pred_el = row.select_one("div[class*='predict'] span.forepr.forepr-tx")
        out[fid] = {
            "p1": probs[0] if len(probs) > 0 else "",
            "p2": probs[1] if len(probs) > 1 else "",
            "pick": pred_el.get_text(strip=True) if pred_el else "",
        }
    return out


def scrape(leagues_only: bool = True) -> list[dict]:
    from ..config import is_top_league

    base = FOREBET["base"]
    now = utcnow()
    rows = []
    seen: set[tuple[str, str]] = set()

    for league_path in FOREBET["leagues"]:
        predictions = parse_predictions(fetch(base + league_path))
        over_under = parse_market(fetch(base + league_path + "/under-over"))
        btts = parse_market(fetch(base + league_path + "/bothtoscore"))

        for fid, data in predictions.items():
            if leagues_only and not is_top_league("forebet", data["league"]):
                continue
            if (fid, "1x2") in seen:
                continue
            seen.add((fid, "1x2"))
            common = {
                "site": "forebet",
                "source_id": fid,
                "league": data["league"],
                "date": data["date"],
                "kickoff": data["kickoff"],
                "home_team": data["home_team"],
                "away_team": data["away_team"],
                "scraped_at": now,
            }
            rows.append(
                {
                    **common,
                    "market": "1x2",
                    "pick": data["pick"],
                    "p1": data["p1"],
                    "p2": data["p2"],
                    "p3": data["p3"],
                    "note": f"avg={data['avg']}" if data["avg"] else "",
                }
            )
            if data["cs"]:
                rows.append(
                    {
                        **common,
                        "market": "correct_score",
                        "pick": data["cs"],
                        "p1": "",
                        "p2": "",
                        "p3": "",
                        "note": f"avg={data['avg']}" if data["avg"] else "",
                    }
                )

            ou = over_under.get(fid, {})
            if ou.get("pick"):
                rows.append(
                    {
                        **common,
                        "market": "over_under",
                        "pick": ou["pick"],
                        "p1": ou.get("p1", ""),
                        "p2": ou.get("p2", ""),
                        "p3": "",
                        "note": "",
                    }
                )

            bt = btts.get(fid, {})
            if bt.get("pick"):
                rows.append(
                    {
                        **common,
                        "market": "btts",
                        "pick": bt["pick"],
                        "p1": bt.get("p1", ""),
                        "p2": bt.get("p2", ""),
                        "p3": "",
                        "note": "",
                    }
                )
    return rows
from __future__ import annotations

from collections import Counter, defaultdict

from .config import CANONICAL_DIR, CONSENSUS_DIR
from .storage import read_csv

MARKETS = ["1x2", "over_under", "btts", "correct_score"]
SITES_ORDER = ("forebet", "eaglepredict", "whoscored", "flashscore")
MARKET_LABELS = {
    "1x2": "1X2",
    "over_under": "Over/Under 2.5",
    "btts": "Both To Score",
    "correct_score": "Correct Score",
}


def _fmt_prob(market: str, row: dict) -> str:
    if market == "1x2":
        if row.get("p1"):
            return f"({row['p1']}/{row['p2']}/{row['p3']})"
        return ""
    if market in ("over_under", "btts"):
        if row.get("p1"):
            return f"({row['p1']}/{row['p2']})"
        return ""
    return ""


def _site_value(site: str, market: str, rows: list[dict]) -> str:
    if not rows:
        return "-"
    row = rows[0]
    pick = row.get("pick_norm") or row.get("pick") or "-"
    probs = _fmt_prob(market, row)
    odds = row.get("note") or ""
    if site == "flashscore" and len(odds) > 60:
        odds = odds[:60] + "…"
    parts = [pick]
    if probs:
        parts.append(probs)
    if odds:
        parts.append(f"[{odds}]")
    return " ".join(parts)


def load_fixtures() -> list[dict]:
    return read_csv(CANONICAL_DIR / "fixtures.csv")


def picks_by_site(sites: dict, market: str) -> dict[str, str]:
    """Return {site: pick_norm} for sites that have a pick on this market."""
    out: dict[str, str] = {}
    for site, rows in sites.items():
        for row in rows.get(market, []):
            pick = (row.get("pick_norm") or "").strip()
            if pick:
                out[site] = pick
                break
    return out


def majority_pick(sites: dict, market: str) -> str | None:
    """Clear majority pick across sites, or None if tied."""
    picks = list(picks_by_site(sites, market).values())
    if not picks:
        return None
    counter = Counter(picks)
    top_pick, top_n = counter.most_common(1)[0]
    if len(counter) > 1 and list(counter.values()).count(top_n) > 1:
        return None
    return top_pick


def agreement_tag(sites: dict, market: str) -> str:
    """Return 'agree', 'split', or 'single' for a fixture market."""
    by_site = picks_by_site(sites, market)
    if len(by_site) < 2:
        return "single"
    if len(set(by_site.values())) == 1:
        return "agree"
    return "split"


def build_report_data() -> list[dict]:
    consensus = read_csv(CONSENSUS_DIR / "consensus.csv")
    by_fid: dict[str, dict[str, dict[str, list[dict]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for row in consensus:
        by_fid[row["fixture_id"]][row["site"]][row["market"]].append(row)

    out = []
    for fixture in load_fixtures():
        fid = fixture["fixture_id"]
        sites = by_fid.get(fid, {})
        out.append({"fixture": fixture, "sites": sites})
    out.sort(key=lambda x: (x["fixture"]["date"], x["fixture"]["kickoff"], x["fixture"]["home_id"]))
    return out


def render_report(data: list[dict], *, date: str | None = None,
                  league: str | None = None, fixture_id: str | None = None,
                  upcoming_only: bool = False) -> str:
    import datetime as dt

    today = dt.date.today().isoformat()
    lines: list[str] = []
    shown = 0
    for item in data:
        fx = item["fixture"]
        if date and fx["date"] != date:
            continue
        if league and league.lower() not in fx["league"].lower():
            continue
        if fixture_id and fx["fixture_id"] != fixture_id:
            continue
        if upcoming_only and fx["date"] < today:
            continue
        shown += 1

        sites = item["sites"]
        lines.append(f"{fx['date']}  {fx['kickoff'] or '--:--'}  {fx['league'] or '?'}")
        lines.append(f"  {fx['home_id']}  vs  {fx['away_id']}  [{fx['fixture_id']}]")

        for market in MARKETS:
            rows_by_site = {s: sites[s].get(market, []) for s in sites}
            cells = []
            for site in SITES_ORDER:
                label = {"forebet": "fore", "eaglepredict": "eagl", "whoscored": "wsco",
                         "flashscore": "fscr"}[site]
                cells.append(f"{label}: {_site_value(site, market, rows_by_site.get(site, []))}")
            picks = {row["pick_norm"] for s in rows_by_site for row in rows_by_site[s] if row.get("pick_norm")}
            mark = ""
            if len([s for s in rows_by_site if rows_by_site[s]]) >= 2 and len(picks) == 1 and "" not in picks:
                mark = "  <-- AGREE"
            elif len([s for s in rows_by_site if rows_by_site[s]]) >= 2 and len(picks) > 1:
                mark = "  <-- SPLIT"
            lines.append(f"    {MARKET_LABELS[market]:<18} " + "   ".join(cells) + mark)
        lines.append("")
    lines.append(f"{shown} fixture(s) shown")
    return "\n".join(lines)
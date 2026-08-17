from __future__ import annotations

from collections import defaultdict

from .config import CONSENSUS_DIR, RESULTS_DIR, WHOSCORED
from .http import fetch, slugify, utcnow
from .report import MARKETS, MARKET_LABELS, agreement_tag, majority_pick, picks_by_site
from .scrapers.whoscored import fixtures_url, parse_scores
from .storage import read_csv, write_csv

RESULT_COLUMNS = [
    "site", "source_id", "league", "date", "kickoff",
    "home_team", "away_team", "home_goals", "away_goals", "scraped_at",
]

_REQUEST_DELAY = 3.0


def scrape_results() -> list[dict]:
    """Fetch finished-match scores from WhoScored league fixtures pages."""
    import time

    base = WHOSCORED["base"]
    now = utcnow()
    rows: list[dict] = []

    for league in WHOSCORED["leagues"]:
        time.sleep(_REQUEST_DELAY)
        league_html = fetch(base + league["url"], retries=8, delay=4.0)
        fix_url = fixtures_url(league_html)
        if not fix_url:
            continue

        time.sleep(_REQUEST_DELAY)
        for m in parse_scores(fetch(base + fix_url, retries=8, delay=4.0)):
            rows.append({
                "site": "whoscored",
                "source_id": m["source_id"],
                "league": league["name"],
                "date": m["date"],
                "kickoff": m["kickoff"],
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "home_goals": m["home_goals"],
                "away_goals": m["away_goals"],
                "scraped_at": now,
            })
    return rows


def _load_aliases() -> dict[tuple[str, str], str]:
    from .config import CANONICAL_DIR

    rows = read_csv(CANONICAL_DIR / "aliases.csv")
    return {(r["site"], r["team_name"]): r["canonical_id"] for r in rows}


def attach_results(results: list[dict]) -> dict:
    """Map each result onto a canonical fixture_id (date|home|vs|away)."""
    aliases = _load_aliases()
    out: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        home_id = aliases.get(("whoscored", r["home_team"])) or slugify(r["home_team"])
        away_id = aliases.get(("whoscored", r["away_team"])) or slugify(r["away_team"])
        fid = f"{r['date']}|{home_id}|vs|{away_id}"
        out[fid].append(r)
    return dict(out)


def evaluate_pick(market: str, pick: str, home_goals: int, away_goals: int) -> bool | None:
    """Return True/False if pick can be graded, None if not applicable."""
    pick = (pick or "").strip()
    if not pick:
        return None
    try:
        hg, ag = int(home_goals), int(away_goals)
    except (TypeError, ValueError):
        return None
    if market == "1x2":
        actual = "1" if hg > ag else ("X" if hg == ag else "2")
        return pick == actual
    if market == "over_under":
        actual = "Over" if hg + ag >= 3 else "Under"
        return pick == actual
    if market == "btts":
        actual = "Yes" if hg > 0 and ag > 0 else "No"
        return pick == actual
    if market == "correct_score":
        return pick == f"{hg} - {ag}"
    return None


def _consensus_by_fixture(consensus: list[dict]) -> dict[str, dict[str, dict[str, list[dict]]]]:
    by_fid: dict[str, dict[str, dict[str, list[dict]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for row in consensus:
        by_fid[row["fixture_id"]][row["site"]][row["market"]].append(row)
    return dict(by_fid)


def grade(results: list[dict]) -> dict:
    """Compare consensus picks against actual results, per site + market."""
    attached = attach_results(results)
    consensus = read_csv(CONSENSUS_DIR / "consensus.csv")
    by_fixture = _consensus_by_fixture(consensus)

    stats: dict[tuple[str, str], list[bool]] = defaultdict(list)
    per_fixture: dict[str, list[dict]] = defaultdict(list)
    agree_stats: dict[str, list[bool]] = defaultdict(list)
    majority_stats: dict[str, list[bool]] = defaultdict(list)
    split_stats: dict[tuple[str, str], list[bool]] = defaultdict(list)

    for fid, sites in by_fixture.items():
        for result in attached.get(fid, []):
            try:
                hg, ag = int(result["home_goals"]), int(result["away_goals"])
            except (TypeError, ValueError):
                continue

            for market in MARKETS:
                by_site = picks_by_site(sites, market)
                if not by_site:
                    continue

                tag = agreement_tag(sites, market)
                for site, pick in by_site.items():
                    ok = evaluate_pick(market, pick, hg, ag)
                    if ok is None:
                        continue
                    stats[(site, market)].append(ok)
                    sample = next(
                        r for s in sites for r in sites[s].get(market, []) if s == site
                    )
                    per_fixture[fid].append({
                        "fixture_id": fid,
                        "home": sample["home"],
                        "away": sample["away"],
                        "home_goals": result["home_goals"],
                        "away_goals": result["away_goals"],
                        "site": site,
                        "market": market,
                        "pick": pick,
                        "result": ok,
                    })
                    if tag == "split":
                        split_stats[(site, market)].append(ok)

                if tag == "agree":
                    pick = next(iter(by_site.values()))
                    ok = evaluate_pick(market, pick, hg, ag)
                    if ok is not None:
                        agree_stats[market].append(ok)
                elif tag == "split":
                    pick = majority_pick(sites, market)
                    if pick:
                        ok = evaluate_pick(market, pick, hg, ag)
                        if ok is not None:
                            majority_stats[market].append(ok)

    return {
        "stats": stats,
        "per_fixture": per_fixture,
        "consensus": {
            "agree": dict(agree_stats),
            "majority": dict(majority_stats),
        },
        "split": dict(split_stats),
    }


def _fmt_rate(vals: list[bool]) -> str:
    if not vals:
        return "-"
    hits = sum(vals)
    return f"{hits}/{len(vals)} ({hits / len(vals) * 100:.0f}%)"


def render_grade(result: dict) -> str:
    lines: list[str] = []
    stats = result["stats"]
    consensus = result.get("consensus", {})
    split = result.get("split", {})

    sites = sorted({s for (s, m) in stats})
    markets = ["1x2", "over_under", "btts", "correct_score"]

    lines.append("Accuracy per site/market (hits / total):")
    lines.append(f"  {'market':<14} " + " ".join(f"{s:<14}" for s in sites))
    for market in markets:
        cells = []
        for site in sites:
            vals = stats.get((site, market), [])
            cells.append(_fmt_rate(vals).ljust(14) if vals else f"{'-':<14}")
        lines.append(f"  {market:<14} " + " ".join(cells))

    total = [(s, m, v) for (s, m), v in stats.items()]
    n_all = sum(len(v) for (_, _, v) in total)
    hits_all = sum(sum(v) for (_, _, v) in total)
    if n_all:
        lines.append(f"  {'ALL':<14} overall {hits_all}/{n_all} ({hits_all/n_all*100:.0f}%)")

    agree = consensus.get("agree", {})
    majority = consensus.get("majority", {})
    if agree or majority:
        lines.append("")
        lines.append("Consensus accuracy (when 2+ sites cover the market):")
        lines.append(f"  {'market':<14} {'agree':<18} {'majority':<18}")
        for market in markets:
            lines.append(
                f"  {market:<14} {_fmt_rate(agree.get(market, [])):<18} "
                f"{_fmt_rate(majority.get(market, [])):<18}"
            )

    if split:
        lines.append("")
        lines.append("Split accuracy (sites only when 2+ sites disagreed):")
        lines.append(f"  {'market':<14} " + " ".join(f"{s:<14}" for s in sites))
        for market in markets:
            cells = []
            for site in sites:
                vals = split.get((site, market), [])
                cells.append(_fmt_rate(vals).ljust(14) if vals else f"{'-':<14}")
            lines.append(f"  {market:<14} " + " ".join(cells))

    return "\n".join(lines)


def render_fixture_results(result: dict) -> str:
    lines: list[str] = []
    for fid in sorted(result["per_fixture"]):
        entries = result["per_fixture"][fid]
        e0 = entries[0]
        lines.append(
            f"{e0['home']} {e0['home_goals']}-{e0['away_goals']} {e0['away']}  [{fid}]"
        )
        for e in entries:
            mark = "hit" if e["result"] else "miss"
            lines.append(f"    {e['site']:<12} {e['market']:<14} pick={e['pick']:<8} {mark}")
    return "\n".join(lines)


def save_results(rows: list[dict]) -> None:
    write_csv(RESULTS_DIR / "whoscored.csv", rows, RESULT_COLUMNS)


def load_results() -> list[dict]:
    from .config import RESULTS_DIR

    return read_csv(RESULTS_DIR / "whoscored.csv")

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from html import unescape
from zoneinfo import ZoneInfo

from .config import CONSENSUS_DIR, FLASHSCORE_MOBI, RESULTS_DIR
from .http import fetch, slugify, utcnow
from .report import MARKETS, MARKET_LABELS, agreement_tag, majority_pick, picks_by_site
from .storage import read_csv, write_csv

RESULT_COLUMNS = [
    "site", "source_id", "league", "date", "kickoff",
    "home_team", "away_team", "home_goals", "away_goals", "scraped_at",
]

_MOBI_LEAGUES = frozenset(FLASHSCORE_MOBI["leagues"])

# <h4>League</h4> or <span>HH:MM</span>Home[<img card>] - Away <a ... class="fin">H-A</a>
_MOBI_TOKEN = re.compile(
    r"<h4>(.*?)</h4>"
    r"|<span>(\d{1,2}:\d{2})(?:<span[^>]*>[^<]*</span>)?</span>"
    r'(.*?)<a href="/match/([A-Za-z0-9]+)/[^"]*" class="fin">([^<]*)</a>',
    re.S,
)


def _strip_tags(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_finished(html: str, date: str) -> list[dict]:
    """Parse flashscore.mobi's score-data section -> finished top-league matches."""
    m = re.search(r'id="score-data">(.*)$', html, re.S)
    if not m:
        return []
    chunk = re.sub(r"<script\b.*?</script>", "", m.group(1), flags=re.S)

    out: list[dict] = []
    league = ""
    for t in _MOBI_TOKEN.finditer(chunk):
        if t.group(1) is not None:
            league = _strip_tags(t.group(1)).replace(" Standings", "").strip()
            continue
        if league not in _MOBI_LEAGUES:
            continue
        score = _strip_tags(t.group(5))
        sm = re.fullmatch(r"(\d+)\s*-\s*(\d+)", score)
        if not sm:
            continue  # walkover / postponed show "- - -"
        teams = _strip_tags(t.group(3))
        teams = re.sub(r"\bWO\b", "", teams).strip()
        if " - " not in teams:
            continue
        home, away = teams.split(" - ", 1)
        kickoff = t.group(2)
        out.append({
            "source_id": t.group(4),
            "league": league.split(":", 1)[-1].strip() if ":" in league else league,
            "date": date,
            "kickoff": f"{date} {kickoff}",
            "home_team": home.strip(),
            "away_team": away.strip(),
            "home_goals": sm.group(1),
            "away_goals": sm.group(2),
        })
    return out


def scrape_results(days: int = 1) -> list[dict]:
    """Fetch yesterday's finished scores from flashscore.mobi (plain HTML, curl-safe).

    `days` fetches each of the last N calendar days (site-local, Europe/Prague).
    """
    base = FLASHSCORE_MOBI["base"]
    now = utcnow()
    today = datetime.now(ZoneInfo("Europe/Prague")).date()
    rows: list[dict] = []
    seen: set[str] = set()

    for back in range(days, 0, -1):
        d = (today - timedelta(days=back)).strftime("%Y-%m-%d")
        html = fetch(f"{base}/?d={-back}&s=3", retries=3, delay=1.5)
        for m in parse_finished(html, d):
            if m["source_id"] in seen:
                continue
            seen.add(m["source_id"])
            rows.append({"site": "flashscore", "scraped_at": now, **m})
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
        site = r.get("site") or "flashscore"
        home_id = aliases.get((site, r["home_team"])) or slugify(r["home_team"])
        away_id = aliases.get((site, r["away_team"])) or slugify(r["away_team"])
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
    if market == "double_chance":
        actual = "1" if hg > ag else ("X" if hg == ag else "2")
        return actual in pick
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
    markets = ["1x2", "over_under", "btts", "correct_score", "double_chance"]

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
    write_csv(RESULTS_DIR / "flashscore.csv", rows, RESULT_COLUMNS)


def load_results() -> list[dict]:
    return read_csv(RESULTS_DIR / "flashscore.csv")

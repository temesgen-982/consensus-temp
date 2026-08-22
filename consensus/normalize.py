from __future__ import annotations

from pathlib import Path

from .config import CANONICAL_DIR, CONSENSUS_DIR, RAW_DIR, SITES
from .http import slugify
from .storage import read_csv, write_csv

TEAMS_COLUMNS = ["site", "team_name", "canonical_id"]
FIXTURES_COLUMNS = ["fixture_id", "league", "date", "kickoff", "home_id", "away_id"]
CONSENSUS_COLUMNS = [
    "fixture_id", "league", "date", "kickoff", "home", "away",
    "site", "market", "pick", "pick_norm", "p1", "p2", "p3", "note", "scraped_at",
]


def normalize_pick(site: str, market: str, pick: str, home: str, away: str) -> str:
    """Map a site's raw pick text onto a shared vocabulary where possible."""
    pick = (pick or "").strip()
    if not pick:
        return ""
    if market == "1x2":
        if site in ("forebet", "flashscore"):
            return pick if pick in ("1", "X", "2") else ""
        # eaglepredict: "{Team} Win"
        if pick.endswith("Win"):
            team = pick[: -len("Win")].strip().lower()
            home_l = (home or "").lower()
            away_l = (away or "").lower()

            def same(x: str, y: str) -> bool:
                # tolerate naming drift, e.g. "Betis" vs "Real Betis"
                return bool(x) and bool(y) and (x == y or x in y or y in x)

            team_home = same(team, home_l)
            team_away = same(team, away_l)
            if team_home and not team_away:
                return "1"
            if team_away and not team_home:
                return "2"
        if pick.lower() == "draw":
            return "X"
        return pick
    if market == "over_under":
        low = pick.lower()
        if low.startswith("over"):
            return "Over"
        if low.startswith("under"):
            return "Under"
        return pick
    if market == "btts":
        low = pick.lower()
        if low in ("yes", "btts - yes"):
            return "Yes"
        if low in ("no", "btts - no"):
            return "No"
        return pick
    return pick


def _load_aliases() -> dict[tuple[str, str], str]:
    """Manual team-name -> canonical-id overrides, maintained by the user."""
    rows = read_csv(CANONICAL_DIR / "aliases.csv")
    return {(r["site"], r["team_name"]): r["canonical_id"] for r in rows}


def _fixture_id(date: str, home_id: str, away_id: str) -> str:
    return f"{date}|{home_id}|vs|{away_id}"


def _completeness(row: dict) -> int:
    """Score how complete a raw row is; used to prefer the fuller copy of a
    match when a history file has duplicates (e.g. one snapshot missing away_team)."""
    score = sum(
        1 for k in ("date", "kickoff", "home_team", "market", "pick")
        if str(row.get(k) or "").strip()
    )
    if str(row.get("away_team") or "").strip():
        score += 5
    return score


def _load_site_rows(site: str) -> list[dict]:
    """Latest live rows plus any daily history snapshots, deduped by
    (source_id, market) keeping the most complete copy (live data wins ties).
    Keeps past predictions available for grading even after a site's live CSV
    rolls forward to the current window."""
    merged: dict[tuple, dict] = {}
    sources = [(r, True) for r in read_csv(RAW_DIR / f"{site}.csv")]
    history_dir = RAW_DIR / "history"
    if history_dir.is_dir():
        for path in sorted(history_dir.glob(f"{site}-*.csv")):
            sources += [(r, False) for r in read_csv(path)]
    for row, is_live in sources:
        key = (row.get("source_id"), row.get("market"))
        if not key or not key[0]:
            continue
        cur = merged.get(key)
        if cur is None:
            merged[key] = dict(row, _live=is_live)
            continue
        cur_score = _completeness(cur) + (10 if cur.get("_live") else 0)
        new_score = _completeness(row) + (10 if is_live else 0)
        if new_score > cur_score:
            merged[key] = row
    for row in merged.values():
        row.pop("_live", None)
    return list(merged.values())


def normalize() -> dict:
    aliases = _load_aliases()
    teams: dict[tuple[str, str], str] = dict(aliases)
    fixtures: dict[str, dict] = {}
    consensus: list[dict] = []
    site_counts: dict[str, int] = {}

    for site in SITES:
        raw = _load_site_rows(site)
        site_counts[site] = len(raw)

        # group raw market rows by source match
        matches: dict[str, list[dict]] = {}
        for row in raw:
            matches.setdefault(row["source_id"], []).append(row)

        for src_id, rows in matches.items():
            first = rows[0]
            home_id = teams.get((site, first["home_team"])) or slugify(first["home_team"])
            away_id = teams.get((site, first["away_team"])) or slugify(first["away_team"])
            teams[(site, first["home_team"])] = home_id
            teams[(site, first["away_team"])] = away_id

            key = _fixture_id(first["date"], home_id, away_id)
            if key not in fixtures:
                fixtures[key] = {
                    "fixture_id": key,
                    "league": first["league"],
                    "date": first["date"],
                    "kickoff": first["kickoff"],
                    "home_id": home_id,
                    "away_id": away_id,
                }

            for row in rows:
                consensus.append({
                    "fixture_id": key,
                    "league": first["league"],
                    "date": first["date"],
                    "kickoff": first["kickoff"],
                    "home": first["home_team"],
                    "away": first["away_team"],
                    "site": site,
                    "market": row["market"],
                    "pick": row["pick"],
                    "pick_norm": normalize_pick(site, row["market"], row["pick"], first["home_team"], first["away_team"]),
                    "p1": row["p1"],
                    "p2": row["p2"],
                    "p3": row["p3"],
                    "note": row["note"],
                    "scraped_at": row["scraped_at"],
                })

    write_csv(CANONICAL_DIR / "teams.csv",
              [{"site": s, "team_name": n, "canonical_id": c} for (s, n), c in sorted(teams.items()) if n],
              TEAMS_COLUMNS)

    write_csv(CANONICAL_DIR / "fixtures.csv", list(fixtures.values()), FIXTURES_COLUMNS)
    write_csv(CONSENSUS_DIR / "consensus.csv", consensus, CONSENSUS_COLUMNS)

    # report single-site fixtures (candidates for manual alias additions)
    multi_site = set()
    for row in consensus:
        multi_site.add(row["fixture_id"])
    fixture_sites: dict[str, set] = {}
    for row in consensus:
        fixture_sites.setdefault(row["fixture_id"], set()).add(row["site"])
    single = [f for fid, f in fixtures.items() if fixture_sites.get(fid, {""}) and len(fixture_sites[fid]) < 2]
    write_csv(CANONICAL_DIR / "review_aliases.csv",
              [{"fixture_id": f["fixture_id"], "date": f["date"], "home_id": f["home_id"],
                "away_id": f["away_id"], "sites": ",".join(sorted(fixture_sites[f["fixture_id"]]))}
               for f in single],
              ["fixture_id", "date", "home_id", "away_id", "sites"])

    return {
        "fixtures": len(fixtures),
        "consensus_rows": len(consensus),
        "teams": len([t for t in teams if t[1]]),
        "aliases": len(aliases),
        "single_site_fixtures": len(single),
        "raw_rows": site_counts,
    }
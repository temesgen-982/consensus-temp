"""EV flagging: estimated consensus probability vs bookmaker implied probability.

P_est = average of (a) accuracy-weighted site votes and (b) Forebet's published
probability vector where available. Implied = vig-stripped book price when every
outcome is priced (1x2, O/U, double chance), raw 1/odds when only the consensus
pick's own price exists (conservative: the vig inflates implied). A pick is
flagged VALUE only when 3+ sites agree unanimously and edge >= EDGE_MIN.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .config import CONSENSUS_DIR
from .odds import load_odds
from .report import agreement_tag, majority_pick, picks_by_site
from .results import grade, load_results
from .storage import read_csv

EDGE_MIN = 0.08
MIN_AGREE_SITES = 3
NOTE_ODDS_SITES = ("whoscored", "eaglepredict")
# When Forebet publishes no probability vector, unanimity among sites is
# smoothed with a uniform prior so 3 agreeing sites never reads as P=1.0.
_UNANIMITY_PRIOR = 4.0

EV_MARKETS = ("1x2", "over_under", "double_chance", "btts")
_OUTCOMES = {
    "1x2": ("1", "X", "2"),
    "over_under": ("Over", "Under"),
    "btts": ("Yes", "No"),
    "double_chance": ("1X", "X2", "12"),
}
_SHORT = {"1x2": "1x2", "over_under": "O/U", "btts": "BTTS", "double_chance": "DC",
          "correct_score": "CS"}


def implied_probs(odds: dict[str, float]) -> dict[str, float]:
    """Normalize 1/odds across outcomes to remove the bookmaker overround."""
    inv = {k: 1.0 / v for k, v in odds.items() if v and v > 1.0}
    total = sum(inv.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in inv.items()}


def note_odds(note: str | None) -> float | None:
    """Numeric price embedded in a site's note field (whoscored/eagle)."""
    note = (note or "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", note):
        return None
    value = float(note)
    return value if 1.01 <= value <= 200.0 else None


def source_weights(results: list[dict]) -> dict[tuple[str, str], float]:
    """Per-site, per-market reliability in (0, 1): smoothed hit rate."""
    stats = grade(results)["stats"]
    return {(site, market): (sum(vals) + 2) / (len(vals) + 4)
            for (site, market), vals in stats.items()}


def _forebet_vector(sites: dict, market: str) -> dict[str, float] | None:
    rows = sites.get("forebet", {}).get(market)
    if not rows:
        return None
    try:
        p1 = float(rows[0].get("p1") or "")
        p2 = float(rows[0].get("p2") or "")
        p3 = float(rows[0].get("p3") or 0)
    except (TypeError, ValueError):
        return None
    if p1 <= 0:
        return None
    scale = 100.0 if max(p1, p2, p3) > 1.5 else 1.0
    if market == "1x2":
        if p3 <= 0:
            return None
        vec = {"1": p1 / scale, "X": p2 / scale, "2": p3 / scale}
    elif market in ("over_under", "btts"):
        a, b = _OUTCOMES[market]
        vec = {a: p1 / scale, b: p2 / scale}
    else:
        return None
    total = sum(vec.values())
    if total <= 0:
        return None
    return {k: v / total for k, v in vec.items()}


def consensus_prob(sites: dict, market: str,
                   weights: dict[tuple[str, str], float]) -> tuple[dict[str, float], int, str]:
    """Estimated outcome distribution for a fixture/market.

    Returns (probabilities by outcome, number of covering sites, agreement tag).
    """
    by_site = picks_by_site(sites, market)
    n = len(by_site)
    tag = agreement_tag(sites, market)

    shares: dict[str, float] = defaultdict(float)
    total = 0.0
    for site, pick in by_site.items():
        w = weights.get((site, market), 0.5)
        shares[pick] += w
        total += w
    vote = {k: v / total for k, v in shares.items()} if total else {}
    vec = _forebet_vector(sites, market)

    outcomes = _OUTCOMES.get(market) or tuple(set(vote) | set(vec or ()))
    if vec and vote:
        dist = {o: 0.5 * vec.get(o, 0.0) + 0.5 * vote.get(o, 0.0) for o in outcomes}
    elif vec:
        dist = {o: vec.get(o, 0.0) for o in outcomes}
    else:
        uniform = 1.0 / len(outcomes) if outcomes else 0.0
        dist = {o: (total * vote.get(o, 0.0) + _UNANIMITY_PRIOR * uniform)
                / (total + _UNANIMITY_PRIOR) for o in outcomes}
    norm = sum(dist.values())
    if norm > 0:
        dist = {k: v / norm for k, v in dist.items()}
    return dist, n, tag


def _latest_odds(rows: list[dict]) -> list[dict]:
    """One row per (event, provider, market, outcome, line), keeping the newest
    scrape so accumulated CLV history doesn't double-price the same bet."""
    best: dict = {}
    for r in rows:
        event = r.get("fixture_id") or f'{r.get("date")}|{r.get("home")}|{r.get("away")}'
        key = (event, r.get("provider"), r.get("market"), r.get("outcome"), r.get("line"))
        prev = best.get(key)
        if prev is None or (r.get("scraped_at") or "") > (prev.get("scraped_at") or ""):
            best[key] = r
    return list(best.values())


def _best_prices(odds_rows: list[dict], consensus_rows: list[dict]) -> dict:
    """fixture_id -> market -> outcome -> best price across providers.

    Falls back to numeric prices in site notes (whoscored/eagle price their own
    pick) so markets ESPN doesn't cover -- notably BTTS -- still get a number.
    """
    best: dict = defaultdict(lambda: defaultdict(dict))

    def put(fid: str, market: str, outcome: str, odds: float, provider: str,
            line: str = "", opened: float | None = None) -> None:
        if not fid or not market or not outcome or odds <= 1.0:
            return
        cur = best[fid][market].get(outcome)
        if cur is None or odds > cur["odds"]:
            best[fid][market][outcome] = {
                "odds": odds, "provider": provider, "line": line, "opened": opened,
            }

    for r in odds_rows:
        try:
            odds = float(r.get("odds") or "")
        except (TypeError, ValueError):
            continue
        opened = None
        try:
            if r.get("opened"):
                opened = float(r["opened"])
        except (TypeError, ValueError):
            pass
        put(r.get("fixture_id") or "", r.get("market") or "", r.get("outcome") or "",
            odds, r.get("provider") or "", r.get("line") or "", opened)

    for r in consensus_rows:
        if r.get("site") not in NOTE_ODDS_SITES:
            continue
        odds = note_odds(r.get("note"))
        if not odds:
            continue
        put(r["fixture_id"], r.get("market") or "", (r.get("pick_norm") or "").strip(),
            odds, r.get("site") or "")
    return best


def build_ev(date: str | None = None, *, consensus_rows: list[dict] | None = None,
             odds_rows: list[dict] | None = None,
             weights: dict[tuple[str, str], float] | None = None,
             edge_min: float = EDGE_MIN, min_sites: int = MIN_AGREE_SITES,
             min_date: str | None = None) -> list[dict]:
    """One row per priced fixture/market, sorted VALUE-first then by edge.

    min_date drops finished fixtures (their note prices are stale history);
    pass min_date=None to price the full graded history (backtesting).
    """
    if consensus_rows is None:
        consensus_rows = read_csv(CONSENSUS_DIR / "consensus.csv")
    if odds_rows is None:
        odds_rows = _latest_odds(load_odds(date))
    if weights is None:
        results = load_results()
        weights = source_weights(results) if results else {}

    sites_by_fid: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    meta: dict[str, dict] = {}
    for row in consensus_rows:
        fid = row["fixture_id"]
        sites_by_fid[fid][row["site"]][row["market"]].append(row)
        meta.setdefault(fid, {
            "date": row.get("date", ""), "home": row.get("home", ""),
            "away": row.get("away", ""), "league": row.get("league", ""),
        })

    best = _best_prices(odds_rows, consensus_rows)
    # live/final events carry an in-play line, which no longer matches the
    # pre-match consensus the picks were made against - exclude them
    states: dict[str, str] = {}
    for r in odds_rows:
        fid = r.get("fixture_id") or ""
        if fid and r.get("state"):
            states[fid] = r["state"]
    snapshot = max((r.get("scraped_at") or "")[:10] for r in odds_rows) if odds_rows else ""

    out: list[dict] = []
    for fid, sites in sites_by_fid.items():
        if fid not in best:
            continue
        if states.get(fid, "pre") != "pre":
            continue
        m = meta[fid]
        if min_date and m["date"] < min_date:
            continue
        for market in EV_MARKETS:
            prices = best[fid].get(market) or {}
            if not prices:
                continue
            if market == "over_under" and any(
                p["line"] and p["line"] != "2.5" for p in prices.values()
            ):
                continue  # picks assume the 2.5 line
            pick = majority_pick(sites, market)
            if not pick:
                continue
            dist, n, tag = consensus_prob(sites, market, weights)
            if n < 2:
                continue  # one site is not a consensus
            outcomes = _OUTCOMES[market]
            have = {o: p for o, p in prices.items() if o in outcomes}
            if pick not in have:
                continue
            if set(have) == set(outcomes):
                implied = implied_probs({o: p["odds"] for o, p in have.items()})
                vig = "norm"
            else:
                implied = {pick: 1.0 / have[pick]["odds"]}
                vig = "raw"
            p_pick = dist.get(pick, 0.0)
            odds_pick = have[pick]["odds"]
            edge = p_pick - implied.get(pick, 0.0)
            ev = p_pick * odds_pick - 1.0
            flag = ("VALUE" if tag == "agree" and n >= min_sites
                    and edge >= edge_min else "")
            out.append({
                "fixture_id": fid, "snapshot": snapshot, **m,
                "market": market, "pick": pick, "tag": tag, "n_sites": n,
                "p_est": p_pick, "odds": odds_pick,
                "provider": have[pick]["provider"], "opened": have[pick]["opened"],
                "implied": implied.get(pick, 0.0), "edge": edge, "ev": ev,
                "vig": vig, "flag": flag,
            })
    out.sort(key=lambda r: (r["flag"] != "VALUE", -r["edge"]))
    return out


def group_by_fixture(rows: list[dict]) -> dict[str, list[dict]]:
    """fixture_id -> EV rows, sorted VALUE-first then by edge (as build_ev)."""
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["fixture_id"]].append(r)
    return out


def price_lookup(rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    """(fixture_id, market, outcome) -> {odds, provider} for the best price."""
    out: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        key = (r["fixture_id"], r["market"], r["pick"])
        cur = out.get(key)
        if cur is None or r["odds"] > cur["odds"]:
            out[key] = {"odds": r["odds"], "provider": r["provider"]}
    return out


def render_ev(rows: list[dict], limit: int | None = 30) -> str:
    if not rows:
        return ("no priced consensus picks found - run 'consensus scrape-odds' first")
    value = sum(1 for r in rows if r["flag"] == "VALUE")
    snap = rows[0]["snapshot"] or "?"
    lines = [
        f"EV board - odds snapshot {snap} (DraftKings/Bet365/notes) - "
        f"{len(rows)} priced picks, {value} VALUE",
        f"  {'fixture':<28} {'mkt':<5} {'pick':<4} {'sites':<5} {'P_est':>5} "
        f"{'odds':>5} {'impl':>5} {'edge':>6} {'EV':>6}  {'book':<11} flag",
    ]
    shown = rows if limit is None else rows[:limit]
    for r in shown:
        fixture = f"{r['home']} v {r['away']}"
        if len(fixture) > 28:
            fixture = fixture[:27] + "…"
        lines.append(
            f"  {fixture:<28} {_SHORT.get(r['market'], r['market']):<5} {r['pick']:<4} "
            f"{r['n_sites']:<5} {r['p_est']:>5.2f} {r['odds']:>5.2f} "
            f"{r['implied']:>5.2f} {r['edge']:>+6.2f} {r['ev']:>+6.2f}  "
            f"{r['provider']:<11} {r['flag']}"
        )
    if limit is not None and len(rows) > limit:
        lines.append(f"  ... {len(rows) - limit} more (use --all)")
    return "\n".join(lines)

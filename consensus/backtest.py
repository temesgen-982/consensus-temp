"""Backtest the EV value flags against graded results.

Historical odds snapshots don't exist yet (only today's forward board), so this
is not a closing-line-value study. What it can honestly measure: over the graded
history, does the EV algorithm's estimated edge actually sort winners from
losers? We compare realized hit rate and flat-stake ROI across edge buckets and
against the naive baseline (every priced consensus pick).

Prices here are the sites' own note prices (whoscored/eagle), so implied is
mostly raw 1/odds (vig not stripped, which is conservative).
"""

from __future__ import annotations

from collections import defaultdict

from .ev import FLAG_MIN_SITES, build_ev
from .odds import rebind
from .results import attach_results, evaluate_pick, load_results


def graded_rows() -> list[dict]:
    """EV rows over full history that also have a graded result, with hit/return."""
    rebind()
    attached = attach_results(load_results())
    rows = build_ev(min_date=None)
    out: list[dict] = []
    for r in rows:
        results = attached.get(r["fixture_id"])
        if not results:
            continue
        res = results[0]
        try:
            hg, ag = int(res["home_goals"]), int(res["away_goals"])
        except (TypeError, ValueError):
            continue
        hit = evaluate_pick(r["market"], r["pick"], hg, ag)
        if hit is None:
            continue
        r = dict(r)
        r["hit"] = hit
        r["return"] = r["odds"] if hit else 0.0  # flat 1u stake
        out.append(r)
    return out


def _bucketize(rows: list[dict], key) -> list[tuple[str, list[dict]]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    return sorted(groups.items())


def _stats(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    hits = sum(1 for r in rows if r["hit"])
    staked = n  # 1u flat
    ret = sum(r["return"] for r in rows)
    return {
        "n": n,
        "hits": hits,
        "hit_rate": hits / n,
        "roi": (ret - staked) / staked,
        "profit": ret - staked,
    }


def verdict(rows: list[dict]) -> dict:
    """Does beating the price on paper translate to beating it in reality?

    The EV model only earns its keep if its high-edge (VALUE) picks actually win
    more, and profit, than the picks it did NOT flag - so VALUE is compared to
    its no-flag complement, not the all-in baseline. {} when no VALUE sample.
    """
    value_rows = [r for r in rows if r["flag"] == "VALUE"]
    value = _stats(value_rows)
    if not value["n"]:
        return {}
    rest = _stats([r for r in rows if r["flag"] != "VALUE"])
    return {
        "baseline": _stats(rows),
        "rest": rest,
        "value": value,
        "holds": bool(rest["n"]) and value["roi"] > rest["roi"]
        and value["hit_rate"] > rest["hit_rate"],
    }


def render_backtest(rows: list[dict]) -> str:
    if not rows:
        return "no graded priced rows - run scrape + normalize + grade first"

    base = _stats(rows)
    lines = [
        f"EV backtest over graded history ({base['n']} priced picks with results)",
        "",
        f"  baseline (all picks):      n={base['n']:<4} hit={base['hit_rate']*100:5.1f}%  "
        f"ROI={base['roi']:+.3f}  profit={base['profit']:+.1f}u",
        "",
        "  -- by VALUE flag --",
    ]
    for flag, group in _bucketize(rows, lambda r: "VALUE" if r["flag"] == "VALUE" else "no-flag"):
        s = _stats(group)
        lines.append(
            f"  {flag:<10} n={s['n']:<4} hit={s['hit_rate']*100:5.1f}%  "
            f"ROI={s['roi']:+.3f}  profit={s['profit']:+.1f}u"
        )

    lines.append("")
    lines.append("  -- by edge bucket --")
    def edge_band(r):
        e = r["edge"]
        if e < 0:
            return "edge < 0"
        if e < 0.08:
            return "0 <= edge < 0.08"
        if e < 0.15:
            return "0.08 <= edge < 0.15"
        if e < 0.25:
            return "0.08+..0.25"
        return "edge >= 0.25"
    for band, group in _bucketize(rows, edge_band):
        s = _stats(group)
        lines.append(
            f"  {band:<20} n={s['n']:<4} hit={s['hit_rate']*100:5.1f}%  "
            f"ROI={s['roi']:+.3f}  profit={s['profit']:+.1f}u"
        )

    lines.append("")
    lines.append("  -- by market --")
    for market, group in _bucketize(rows, lambda r: r["market"]):
        s = _stats(group)
        lines.append(
            f"  {market:<12} n={s['n']:<4} hit={s['hit_rate']*100:5.1f}%  "
            f"ROI={s['roi']:+.3f}  profit={s['profit']:+.1f}u"
        )

    lines.append("")
    lines.append("  -- by site agreement (n_sites) --")
    for n_sites, group in _bucketize(rows, lambda r: str(r["n_sites"])):
        s = _stats(group)
        lines.append(
            f"  {n_sites + ' sites':<10} n={s['n']:<4} hit={s['hit_rate']*100:5.1f}%  "
            f"ROI={s['roi']:+.3f}  profit={s['profit']:+.1f}u"
        )

    # Does the algorithm's P_est calibrate? Bucket by predicted probability.
    lines.append("")
    lines.append("  -- calibration: predicted P_est vs realized hit rate --")
    def p_band(r):
        p = r["p_est"]
        lo = int(p * 10) / 10
        return f"{lo:.1f} - {lo + 0.1:.1f}"
    calib = []
    for band, group in _bucketize(rows, p_band):
        s = _stats(group)
        # band midpoint as the predicted probability
        mid = (float(band.split(" ")[0]) + 0.05)
        calib.append((band, s, mid))
        lines.append(
            f"  {band:<14} n={s['n']:<4} P_est~{mid:.2f}  "
            f"realized={s['hit_rate']*100:5.1f}%  gap={s['hit_rate']-mid:+.3f}"
        )
    if len(calib) >= 2:
        # average absolute calibration error, weighted by n
        tot = sum(s["n"] for _, s, _ in calib)
        mae = sum(s["n"] * abs(s["hit_rate"] - mid) for _, s, mid in calib) / tot
        lines.append(f"  mean |calibration error| = {mae:.3f}")

    v = verdict(rows)
    if v:
        value, rest, base = v["value"], v["rest"], v["baseline"]
        lines.append("")
        word = "HOLDS" if v["holds"] else "FAILS"
        lines.append(f"  VERDICT ({FLAG_MIN_SITES}+ sites, BTTS/OU, ev>0): {word}")
        lines.append(
            f"    VALUE        n={value['n']:<4} hit={value['hit_rate']*100:5.1f}%  "
            f"ROI={value['roi']:+.3f}  profit={value['profit']:+.1f}u"
        )
        lines.append(
            f"    no-flag      n={rest['n']:<4} hit={rest['hit_rate']*100:5.1f}%  "
            f"ROI={rest['roi']:+.3f}  profit={rest['profit']:+.1f}u"
        )
        lines.append(
            f"    all picks    n={base['n']:<4} hit={base['hit_rate']*100:5.1f}%  "
            f"ROI={base['roi']:+.3f}  profit={base['profit']:+.1f}u"
        )
    return "\n".join(lines)

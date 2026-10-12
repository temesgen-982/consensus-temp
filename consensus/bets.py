from __future__ import annotations

import re
from collections import defaultdict
from datetime import date as date_cls

from .config import BETS_DIR
from .storage import read_csv, write_csv

BETS_PATH = BETS_DIR / "bets.csv"
LEGS_PATH = BETS_DIR / "bet_legs.csv"

BET_COLUMNS = [
    "bet_id", "placed_date", "kind", "stake", "odds", "source",
    "status", "payout", "settled_date", "note",
]
LEG_COLUMNS = ["bet_id", "fixture_id", "leg", "conditions", "status", "detail"]

_TOTAL = re.compile(r"^([OU])(\d+(?:\.\d+)?)$", re.I)
_TEAM = re.compile(r"^([HA])(\d+(?:\.\d+)?)$", re.I)
_DC = {"1X", "X2", "12"}


def parse_conditions(expr: str) -> list[tuple]:
    """Parse a leg condition expression into evaluable tokens.

    Tokens are joined with '+':
      1 / X / 2        single 1x2 outcome
      1X / X2 / 12     double chance
      O2.5 / U3.5      match total over/under
      BTTS / nBTTS     both teams to score (yes/no)
      H0.5 / A1.5      home/away team goals over
    """
    tokens: list[tuple] = []
    for raw in (expr or "").split("+"):
        tok = raw.strip()
        if not tok:
            continue
        up = tok.upper()
        if up in ("BTTS", "NBTTS"):
            tokens.append(("btts", "Yes" if up == "BTTS" else "No"))
            continue
        if len(tok) == 1 and tok in "1X2":
            tokens.append(("1x2", tok))
            continue
        if up in _DC:
            tokens.append(("dc", up))
            continue
        m = _TOTAL.match(tok)
        if m:
            side = "Over" if m.group(1).upper() == "O" else "Under"
            tokens.append(("ou", side, float(m.group(2))))
            continue
        m = _TEAM.match(tok)
        if m:
            side = "H" if m.group(1).upper() == "H" else "A"
            tokens.append(("team", side, float(m.group(2))))
            continue
        raise ValueError(f"unrecognised leg condition {tok!r} in {expr!r}")
    return tokens


def eval_condition(token: tuple, hg: int, ag: int) -> bool | None:
    """Grade one token against a final score (None = push/void)."""
    kind = token[0]
    if kind == "1x2":
        actual = "1" if hg > ag else ("X" if hg == ag else "2")
        return token[1] == actual
    if kind == "dc":
        actual = "1" if hg > ag else ("X" if hg == ag else "2")
        return actual in token[1]
    if kind == "ou":
        total = hg + ag
        if total == token[2]:
            return None
        return (total > token[2]) if token[1] == "Over" else (total < token[2])
    if kind == "btts":
        yes = hg > 0 and ag > 0
        return yes if token[1] == "Yes" else not yes
    if kind == "team":
        goals = hg if token[1] == "H" else ag
        if goals == token[2]:
            return None
        return goals > token[2]
    return None


def parse_leg(spec: str) -> dict:
    """Turn a CLI leg string into {fixture_id, leg, conditions}.

    Accepted forms (fixture id uses the canonical date|home|vs|away shape):
      date|home|vs|away|COND   fixture + gradeable conditions
      date|home|vs|away        fixture only (settle manually)
      date|home|away           fixture only (vs inserted)
      text                     freeform (settle manually)
    """
    raw = spec.strip()
    parts = [p.strip() for p in raw.split("|")]
    fid = ""
    cond = ""
    if len(parts) >= 5:
        fid = "|".join(parts[:4])
        cond = "|".join(parts[4:])
    elif len(parts) == 4 and parts[2].lower() == "vs":
        fid = "|".join(parts)
    elif len(parts) == 3:
        fid = f"{parts[0]}|{parts[1]}|vs|{parts[2]}"
    if cond:
        parse_conditions(cond)  # validate early, raises ValueError on junk
    return {"fixture_id": fid, "leg": raw, "conditions": cond}


def load_bets() -> list[dict]:
    return read_csv(BETS_PATH)


def load_legs() -> list[dict]:
    return read_csv(LEGS_PATH)


def save_bets(bets: list[dict]) -> None:
    write_csv(BETS_PATH, bets, BET_COLUMNS)


def save_legs(legs: list[dict]) -> None:
    write_csv(LEGS_PATH, legs, LEG_COLUMNS)


def add_bet(
    stake: float,
    odds: float | None,
    leg_specs: list[str],
    *,
    source: str = "own",
    placed_date: str | None = None,
    note: str = "",
    kind: str | None = None,
) -> dict:
    bets = load_bets()
    legs = load_legs()
    next_id = max((int(b["bet_id"]) for b in bets), default=0) + 1
    parsed = [parse_leg(s) for s in leg_specs]
    if not parsed:
        raise ValueError("at least one --leg is required")
    bet = {
        "bet_id": str(next_id),
        "placed_date": placed_date or date_cls.today().isoformat(),
        "kind": kind or ("single" if len(parsed) == 1 else "parlay"),
        "stake": f"{float(stake):.2f}",
        "odds": "" if odds is None else f"{float(odds):.3f}",
        "source": source,
        "status": "pending",
        "payout": "",
        "settled_date": "",
        "note": note,
    }
    bets.append(bet)
    for p in parsed:
        legs.append({
            "bet_id": str(next_id),
            "fixture_id": p["fixture_id"],
            "leg": p["leg"],
            "conditions": p["conditions"],
            "status": "pending",
            "detail": "",
        })
    save_bets(bets)
    save_legs(legs)
    return bet


def evaluate_leg(fixture_id: str, conditions: str, attached: dict) -> tuple[str, str]:
    """Resolve one leg against attached results -> (status, detail).

    status: pending (no result or nothing to grade), won, lost, void.
    """
    if not fixture_id:
        return "pending", ""
    results = attached.get(fixture_id)
    if not results:
        return "pending", ""
    try:
        hg = int(results[0]["home_goals"])
        ag = int(results[0]["away_goals"])
    except (TypeError, ValueError, KeyError):
        return "pending", ""
    detail = f"{hg}-{ag}"
    tokens = parse_conditions(conditions)
    if not tokens:
        return "pending", detail  # fixture known, but no gradeable conditions
    outcomes = [eval_condition(t, hg, ag) for t in tokens]
    if any(o is False for o in outcomes):
        return "lost", detail
    if any(o is None for o in outcomes):
        return "void", detail
    return "won", detail


def _payout(stake: str, odds: str) -> str:
    try:
        return f"{float(stake) * float(odds):.2f}"
    except (TypeError, ValueError):
        return ""


def _result_date(fixture_id: str, attached: dict) -> str | None:
    rs = attached.get(fixture_id)
    return rs[0].get("date") if rs else None


def settle_bets(
    *,
    manual_id: str | int | None = None,
    manual_result: str | None = None,
    attached: dict | None = None,
) -> list[str]:
    """Grade pending bets against results. Returns a change log.

    With manual_id + manual_result, force one bet to won/lost instead of grading.
    """
    if attached is None:
        from .results import attach_results, load_results

        attached = attach_results(load_results())
    bets = load_bets()
    legs = load_legs()
    by_bet: dict[str, list[dict]] = defaultdict(list)
    for lg in legs:
        by_bet[lg["bet_id"]].append(lg)

    log: list[str] = []
    today = date_cls.today().isoformat()

    for bet in bets:
        if manual_id is not None and bet["bet_id"] != str(manual_id):
            continue
        if bet["status"] != "pending":
            if manual_id is not None:
                log.append(f"bet {bet['bet_id']}: already {bet['status']}, unchanged")
            continue

        bl = by_bet[bet["bet_id"]]

        if manual_result:
            bet["status"] = manual_result
            bet["payout"] = _payout(bet["stake"], bet["odds"]) if manual_result == "won" else "0.00"
            dates = [d for d in (_result_date(lg["fixture_id"], attached) for lg in bl) if d]
            bet["settled_date"] = max(dates) if dates else today
            for lg in bl:
                if lg["status"] == "pending":
                    lg["status"] = manual_result
            log.append(f"bet {bet['bet_id']}: manually {manual_result} ({bet['payout']})")
            continue

        for lg in bl:
            if lg["status"] != "pending":
                continue
            status, detail = evaluate_leg(lg["fixture_id"], lg["conditions"], attached)
            if status != "pending":
                lg["status"] = status
                lg["detail"] = detail

        dates = [d for d in (_result_date(lg["fixture_id"], attached) for lg in bl) if d]
        settled_date = max(dates) if dates else today

        if any(lg["status"] == "lost" for lg in bl):
            bet["status"] = "lost"
            bet["payout"] = "0.00"
            bet["settled_date"] = settled_date
            lost = [lg["leg"] for lg in bl if lg["status"] == "lost"]
            log.append(f"bet {bet['bet_id']}: LOST ({len(lost)} leg(s): {', '.join(lost)})")
        elif bl and all(lg["status"] in ("won", "void") for lg in bl):
            bet["status"] = "won"
            bet["payout"] = _payout(bet["stake"], bet["odds"])
            bet["settled_date"] = settled_date
            log.append(f"bet {bet['bet_id']}: WON (payout {bet['payout'] or '?'})")
        else:
            pending = sum(1 for lg in bl if lg["status"] == "pending")
            log.append(f"bet {bet['bet_id']}: pending ({pending} leg(s) unresolved)")

    save_bets(bets)
    save_legs(legs)
    return log


def summarize(bets: list[dict]) -> dict:
    settled = [b for b in bets if b["status"] in ("won", "lost")]
    pending = [b for b in bets if b["status"] == "pending"]
    staked = sum(float(b["stake"]) for b in settled)
    returned = sum(float(b["payout"] or 0) for b in settled)
    wins = sum(1 for b in settled if b["status"] == "won")
    return {
        "bets": len(bets),
        "settled": len(settled),
        "pending": len(pending),
        "wins": wins,
        "losses": len(settled) - wins,
        "staked": staked,
        "returned": returned,
        "net": returned - staked,
        "roi": (returned - staked) / staked if staked else 0.0,
        "win_rate": wins / len(settled) if settled else 0.0,
    }


def render_bets(bets: list[dict], legs: list[dict], *, only_pending: bool = False) -> str:
    by_bet: dict[str, list[dict]] = defaultdict(list)
    for lg in legs:
        by_bet[lg["bet_id"]].append(lg)

    stats = summarize(bets)
    lines = [
        f"Personal bets - {stats['bets']} total, {stats['settled']} settled, "
        f"{stats['pending']} pending",
        f"  staked {stats['staked']:.2f}  returned {stats['returned']:.2f}  "
        f"net {stats['net']:+.2f}  ROI {stats['roi']:+.3f}  "
        f"({stats['wins']}W/{stats['losses']}L = {stats['win_rate'] * 100:.0f}%)",
        "",
    ]

    shown = [b for b in bets if not only_pending or b["status"] == "pending"]
    if not shown:
        lines.append("  (no bets)" if bets else "  (no bets recorded yet - try 'consensus bet add --help')")
        return "\n".join(lines)

    lines.append(
        f"  {'id':<3} {'placed':<11} {'kind':<7} {'stake':>8} {'odds':>7} "
        f"{'status':<8} {'payout':>8} {'source':<9} note"
    )
    for b in shown:
        lines.append(
            f"  {b['bet_id']:<3} {b['placed_date']:<11} {b['kind']:<7} "
            f"{float(b['stake']):>8.2f} "
            f"{(b['odds'] or '-'):>7} {b['status']:<8} "
            f"{(b['payout'] or '-'):>8} {b['source']:<9} {b.get('note', '')}"
        )
        for lg in by_bet[b["bet_id"]]:
            detail = f" [{lg['detail']}]" if lg["detail"] else ""
            name = lg["leg"]
            if len(name) > 60:
                name = name[:59] + "…"
            lines.append(f"        {lg['status']:<7} {name}{detail}")
    return "\n".join(lines)

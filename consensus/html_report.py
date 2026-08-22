from __future__ import annotations

import html as html_mod
import os
import re
from pathlib import Path

from .config import CONSENSUS_DIR
from .report import MARKETS, MARKET_LABELS, agreement_tag, build_report_data, majority_pick, picks_by_site
from .results import attach_results, evaluate_pick, grade, load_results

SITES_ORDER = (
    "forebet",
    "eaglepredict",
    "whoscored",
    "flashscore",
    "sportsgambler",
    "sportytrader",
)
SITE_NAMES = {"forebet": "Forebet", "eaglepredict": "EaglePredict",
              "whoscored": "WhoScored", "flashscore": "Flashscore",
              "sportsgambler": "SportsGambler", "sportytrader": "SportyTrader"}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prediction Consensus</title>
<style>
  :root {{
    --bg: #0f1115; --card: #171b22; --line: #262c36; --txt: #e6e9ef;
    --muted: #8b93a3; --accent: #5b9cff; --ok: #2ecc71; --warn: #f1c40f;
    --bad: #e74c3c; --site-a: #5b9cff; --site-b: #9b7bff;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px; background: var(--bg); color: var(--txt);
    font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }}
  header {{
    display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap;
    max-width: 1080px; margin: 0 auto 16px;
  }}
  h1 {{ font-size: 22px; margin: 0; }}
  .stats {{ color: var(--muted); font-size: 13px; }}
  .stats b {{ color: var(--txt); }}

  .toolbar {{
    position: sticky; top: 0; z-index: 20; background: var(--bg);
    max-width: 1080px; margin: 0 auto 16px; padding: 10px 0;
    border-bottom: 1px solid var(--line);
  }}
  .toolbar .row {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
  #q {{
    background: var(--card); border: 1px solid var(--line); color: var(--txt);
    border-radius: 8px; padding: 8px 12px; font: inherit; width: 240px;
  }}
  .chips {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }}
  .chip {{
    background: var(--card); border: 1px solid var(--line); color: var(--muted);
    border-radius: 20px; padding: 4px 12px; font: inherit; font-size: 12.5px;
    cursor: pointer;
  }}
  .chip.active {{ border-color: var(--accent); color: var(--accent); }}
  .chip b {{ color: var(--txt); }}
  label.toggle {{ color: var(--muted); font-size: 13px; display: flex; gap: 6px; align-items: center; }}

  .panel {{
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 16px; margin-bottom: 14px;
  }}
  .panel h2 {{ font-size: 14px; margin: 0 0 10px; color: var(--accent); }}
  .acc-table th, .acc-table td {{
    padding: 4px 10px; border-top: 1px solid var(--line); text-align: left;
  }}
  .acc-table thead th {{ color: var(--muted); font-size: 11.5px; text-transform: uppercase; }}
  .hit {{ color: var(--ok); font-weight: 700; }}
  .miss {{ color: var(--bad); font-weight: 700; }}
  .rate {{ color: var(--muted); font-size: 12px; }}

  main {{ max-width: 1080px; margin: 0 auto; }}
  .league {{
    margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--line);
    font-size: 15px; font-weight: 700; color: var(--accent);
    display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap;
  }}
  .league .lcount {{ color: var(--muted); font-weight: 400; font-size: 12.5px; }}
  .card {{
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 16px; margin-bottom: 12px;
  }}
  .card-head {{
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 12px; margin-bottom: 10px; flex-wrap: wrap; cursor: pointer;
    user-select: none;
  }}
  .card-head .caret {{ color: var(--muted); font-size: 11px; margin-left: 6px; }}
  .card.closed .card-body {{ display: none; }}
  .teams {{ font-size: 16px; font-weight: 600; }}
  .teams .vs {{ color: var(--muted); font-weight: 400; margin: 0 6px; }}
  .meta {{ color: var(--muted); font-size: 12.5px; }}
  .score {{
    background: color-mix(in srgb, var(--ok) 14%, transparent); color: var(--ok);
    font-weight: 700; font-size: 12.5px; border-radius: 4px; padding: 1px 8px;
  }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 5px 8px; border-top: 1px solid var(--line); }}
  thead th {{ color: var(--muted); font-size: 11.5px; text-transform: uppercase;
    letter-spacing: .05em; border-top: none; }}
  td.market {{ width: 130px; font-weight: 600; }}
  .site {{ padding: 1px 8px; border-radius: 4px; font-size: 11.5px; font-weight: 700;
    margin-right: 6px; }}
  .forebet {{ background: color-mix(in srgb, var(--site-a) 22%, transparent); color: var(--site-a); }}
  .eaglepredict {{ background: color-mix(in srgb, var(--site-b) 22%, transparent); color: var(--site-b); }}
  .whoscored {{ background: color-mix(in srgb, var(--ok) 14%, transparent); color: var(--ok); }}
  .flashscore {{ background: color-mix(in srgb, var(--bad) 20%, transparent); color: var(--bad); }}
  .probs {{ color: var(--muted); font-size: 12px; }}
  .odds {{ color: var(--muted); font-size: 12px; }}
  .best-odds {{ color: var(--ok); font-weight: 700; font-size: 12px; }}
  .tag {{ font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 10px; margin-left: 8px; }}
  .tag.agree {{ background: color-mix(in srgb, var(--ok) 18%, transparent); color: var(--ok); }}
  .tag.split {{ background: color-mix(in srgb, var(--warn) 18%, transparent); color: var(--warn); }}
  .tag.none {{ background: color-mix(in srgb, var(--bad) 14%, transparent); color: var(--bad); }}
  .empty {{ color: var(--muted); }}
  td.consensus {{ width: 90px; font-weight: 700; color: var(--accent); }}
  .pick.hl {{ background: color-mix(in srgb, var(--accent) 18%, transparent);
    border-radius: 4px; padding: 0 4px; }}
  footer {{ max-width: 1080px; margin: 30px auto 0; color: var(--muted);
    font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<header>
  <h1>Prediction Consensus</h1>
  <div class="stats">{stats}</div>
</header>
<div class="toolbar">
  <div class="row">
    <input id="q" type="search" placeholder="Search teams…">
    <label class="toggle"><input type="checkbox" id="hide1" checked> Hide 1-site fixtures</label>
  </div>
  <div class="chips" id="chips">{chips}</div>
</div>
<main>
{accuracy}
{body}
</main>
<footer>Generated {generated} &middot; {count} fixture(s)</footer>
<script>
(function(){{
  var q = document.getElementById('q');
  var hide1 = document.getElementById('hide1');
  var chips = document.querySelectorAll('.chip');
  var cards = document.querySelectorAll('.card');
  var activeLeague = null;

  function apply() {{
    var text = q.value.toLowerCase();
    var hideSingle = hide1.checked;
    var shown = 0;
    cards.forEach(function(card) {{
      var league = card.getAttribute('data-league');
      var sites = parseInt(card.getAttribute('data-sites'), 10);
      var search = (card.getAttribute('data-search') || '').toLowerCase();
      var ok = true;
      if (activeLeague && league !== activeLeague) ok = false;
      if (hideSingle && sites < 2) ok = false;
      if (text && search.indexOf(text) === -1) ok = false;
      card.style.display = ok ? '' : 'none';
      if (ok) shown++;
    }});
  }}

  q.addEventListener('input', apply);
  hide1.addEventListener('change', apply);
  chips.forEach(function(chip) {{
    chip.addEventListener('click', function() {{
      var lg = chip.getAttribute('data-league');
      activeLeague = (activeLeague === lg) ? null : lg;
      chips.forEach(function(c) {{ c.classList.remove('active'); }});
      if (activeLeague) chip.classList.add('active');
      apply();
    }});
  }});

  cards.forEach(function(card) {{
    var head = card.querySelector('.card-head');
    head.addEventListener('click', function() {{
      card.classList.toggle('closed');
    }});
  }});

  apply();
}})();
</script>
</body>
</html>
"""


def _esc(text: str) -> str:
    return html_mod.escape(str(text or ""))


def _odds_value(note: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", note or "")
    return float(m.group(1)) if m else None


def _probs_html(market: str, row: dict) -> str:
    if market == "1x2" and row.get("p1"):
        return f' <span class="probs">({_esc(row["p1"])}/{_esc(row["p2"])}/{_esc(row["p3"])})</span>'
    if market in ("over_under", "btts") and row.get("p1"):
        return f' <span class="probs">({_esc(row["p1"])}/{_esc(row["p2"])})</span>'
    return ""


def _cell(site: str, market: str, rows: list[dict], highlight: bool = False,
          best_odds: bool = False) -> str:
    if not rows:
        return '<span class="empty">-</span>'
    row = rows[0]
    pick = row.get("pick_norm") or row.get("pick") or "-"
    odds = row.get("note") or ""
    odds_cls = "best-odds" if best_odds else "odds"
    pick_html = f'<b>{_esc(pick)}</b>'
    if highlight:
        pick_html = f'<b class="pick hl">{_esc(pick)}</b>'
    parts = [f'<span class="site {site}">{_esc(site[:4])}</span>', pick_html]
    parts.append(_probs_html(market, row))
    if odds:
        if site == "flashscore":
            words = odds.split()
            shown = " ".join(words[:4]) + "…" if len(words) > 4 else odds
            parts.append(f' <span class="odds">{_esc(shown)}</span>')
        else:
            parts.append(f' <span class="{odds_cls}">[{_esc(odds)}]</span>')
    return "".join(parts)


def _fixture_html(item: dict, result: dict | None) -> str:
    fx = item["fixture"]
    sites = item["sites"]
    kickoff = fx["kickoff"] or "--:--"
    search = f"{fx['home_id']} {fx['away_id']} {fx['home_id'].replace('-', ' ')} {fx['away_id'].replace('-', ' ')}"
    site_count = len([s for s in sites if any(sites[s][m] for m in MARKETS)])
    fixture_id = fx["fixture_id"]

    score_badge = ""
    if result:
        r = result
        score_badge = (f' <span class="score">{_esc(r["home_goals"])}-{_esc(r["away_goals"])} FT</span>')

    head = (
        f'<div class="card-head"><div class="teams">{_esc(fx["home_id"])}'
        f'<span class="vs">vs</span>{_esc(fx["away_id"])}'
        f'<span class="caret">[toggle]</span></div>'
        f'<div class="meta">{_esc(fx["date"])} &middot; {_esc(kickoff)}{score_badge}</div></div>'
    )

    rows_html = [
        '<div class="card-body"><table><thead><tr><th>Market</th>'
        + "".join(f"<th>{_esc(SITE_NAMES.get(s, s))}</th>" for s in SITES_ORDER)
        + "<th>Consensus</th><th>Result</th></tr></thead><tbody>"
    ]
    for market in MARKETS:
        rows_by_site = {s: sites[s].get(market, []) for s in sites}
        picks = {r["pick_norm"] for s in rows_by_site for r in rows_by_site[s] if r.get("pick_norm")}
        present = [s for s in rows_by_site if rows_by_site[s]]
        if len(present) >= 2 and len(picks) == 1 and "" not in picks:
            tag = '<span class="tag agree">AGREE</span>'
        elif len(present) >= 2:
            tag = '<span class="tag split">SPLIT</span>'
        else:
            tag = '<span class="tag none">1 SITE</span>'

        majority = majority_pick(sites, market)

        # best odds among present sites
        best_val = None
        for s in present:
            v = _odds_value(rows_by_site[s][0].get("note"))
            if v is not None and (best_val is None or v < best_val):
                best_val = v

        cells = []
        for s in SITES_ORDER:
            rows_s = rows_by_site.get(s, [])
            hl = bool(rows_s) and majority is not None and rows_s[0].get("pick_norm") == majority
            best = bool(rows_s) and best_val is not None and _odds_value(rows_s[0].get("note")) == best_val
            cells.append(_cell(s, market, rows_s, highlight=hl, best_odds=best))

        cons = majority if majority else ""
        cons_html = f'<td class="consensus">{_esc(cons) if cons else ""}</td>'

        # result grading
        res_html = '<td><span class="empty">-</span></td>'
        if result:
            try:
                hg, ag = int(result["home_goals"]), int(result["away_goals"])
            except (TypeError, ValueError):
                hg, ag = None, None
            if hg is not None:
                row_pick = next((r for s in present for r in rows_by_site[s]), None)
                # grade each site's pick for this market
                graded = []
                for s in present:
                    r = rows_by_site[s][0]
                    ok = evaluate_pick(market, r.get("pick_norm"), hg, ag)
                    if ok is not None:
                        graded.append(f'<span class="{"hit" if ok else "miss"}">{_esc(s[:4])}</span>')
                if graded:
                    res_html = f'<td style="width:80px">{" ".join(graded)}</td>'

        rows_html.append(
            f'<tr><td class="market">{_esc(MARKET_LABELS[market])}</td>'
            + "".join(f"<td>{cell}</td>" for cell in cells)
            + f"{cons_html}{res_html}"
            f'<td style="width:70px">{tag}</td></tr>'
        )
    rows_html.append("</tbody></table></div>")
    return (
        f'<div class="card" data-league="{_esc(fx["league"] or "")}" '
        f'data-sites="{site_count}" data-search="{_esc(search)}">'
        f'{head}{"".join(rows_html)}</div>'
    )


def _accuracy_html(grade_result: dict) -> str:
    stats = grade_result.get("stats", {})
    consensus = grade_result.get("consensus", {})
    if not stats and not consensus.get("agree") and not consensus.get("majority"):
        return '<div class="panel"><h2>Recent Results</h2><p class="empty">No results recorded yet.</p></div>'

    sites = sorted({s for (s, m) in stats})
    markets = ["1x2", "over_under", "btts", "correct_score"]
    rows = ['<table class="acc-table"><thead><tr><th>Site</th>']
    for m in markets:
        rows.append(f"<th>{_esc(MARKET_LABELS[m])}</th>")
    rows.append("<th>Overall</th></tr></thead><tbody>")

    for site in sites:
        cells = [f'<td><b>{_esc(SITE_NAMES[site])}</b></td>']
        totals, hits = 0, 0
        for m in markets:
            vals = stats.get((site, m), [])
            if vals:
                n, h = len(vals), sum(vals)
                totals += n
                hits += h
                cells.append(f'<td><span class="{"hit" if h / n >= 0.5 else "miss"}">{h}/{n}</span> '
                             f'<span class="rate">({h / n * 100:.0f}%)</span></td>')
            else:
                cells.append('<td class="empty">-</td>')
        if totals:
            cells.append(f'<td><b>{hits}/{totals} ({hits / totals * 100:.0f}%)</b></td>')
        else:
            cells.append('<td class="empty">-</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    rows.append("</tbody></table>")

    agree = consensus.get("agree", {})
    majority = consensus.get("majority", {})
    consensus_html = ""
    if agree or majority:
        consensus_html = (
            '<h2 style="margin-top:14px">Consensus Accuracy</h2>'
            '<table class="acc-table"><thead><tr>'
            '<th>Market</th><th>Agree (2+ same)</th><th>Majority (split)</th></tr></thead><tbody>'
        )
        for m in markets:
            a_vals = agree.get(m, [])
            m_vals = majority.get(m, [])
            a_cell = "-"
            m_cell = "-"
            if a_vals:
                h, n = sum(a_vals), len(a_vals)
                a_cell = f'<span class="{"hit" if h / n >= 0.5 else "miss"}">{h}/{n}</span> ' \
                         f'<span class="rate">({h / n * 100:.0f}%)</span>'
            if m_vals:
                h, n = sum(m_vals), len(m_vals)
                m_cell = f'<span class="{"hit" if h / n >= 0.5 else "miss"}">{h}/{n}</span> ' \
                         f'<span class="rate">({h / n * 100:.0f}%)</span>'
            consensus_html += (
                f"<tr><td>{_esc(MARKET_LABELS[m])}</td><td>{a_cell}</td><td>{m_cell}</td></tr>"
            )
        consensus_html += "</tbody></table>"

    # recent fixtures with results
    per_fixture = grade_result.get("per_fixture", {})
    recent = sorted(per_fixture, key=lambda f: f.split("|")[0], reverse=True)[:6]
    recent_html = []
    for fid in recent:
        entries = per_fixture[fid]
        e0 = entries[0]
        marks = " ".join(
            f'<span class="{"hit" if e["result"] else "miss"}">'
            f'{"&#10003;" if e["result"] else "&#10007;"} {_esc(e["site"][:4])} '
            f'{_esc(e["market"] or "")} [{_esc(e["pick"] or "")}]</span>'
            for e in entries[:8]
        )
        recent_html.append(
            f'<div style="margin-top:6px"><b>{_esc(e0["home"])} {_esc(e0["home_goals"])}-'
            f'{_esc(e0["away_goals"])} {_esc(e0["away"])}</b> {marks}</div>'
        )

    return (
        '<div class="panel"><h2>Accuracy by Site &amp; Market</h2>'
        + "".join(rows)
        + consensus_html
        + '<h2 style="margin-top:14px">Most Recent Graded Fixtures</h2>'
        + "".join(recent_html)
        + "</div>"
    )


def build_html(upcoming_only: bool = True) -> str:
    import datetime as dt

    data = build_report_data()
    today = dt.date.today().isoformat()

    # attach results
    results = load_results()
    grade_result = grade(results) if results else {"stats": {}, "per_fixture": {}}
    attached = attach_results(results) if results else {}

    fixtures = 0
    agreements = 0
    splits = 0
    by_league: dict[str, list[dict]] = {}
    for item in data:
        fx = item["fixture"]
        if upcoming_only and fx["date"] < today:
            continue
        fixtures += 1
        by_league.setdefault(fx["league"] or "Unknown", []).append(item)

        for market in MARKETS:
            present = [s for s in item["sites"] if item["sites"][s].get(market)]
            if len(present) < 2:
                continue
            picks = {r["pick_norm"] for s in present for r in item["sites"][s][market] if r.get("pick_norm")}
            if len(picks) == 1 and "" not in picks:
                agreements += 1
            elif len(picks) > 1:
                splits += 1

    sections = []
    league_counts = {}
    for league in sorted(by_league):
        cards = []
        agree_l = split_l = 0
        for item in by_league[league]:
            fid = item["fixture"]["fixture_id"]
            result = attached.get(fid, [None])[0] if attached.get(fid) else None
            cards.append(_fixture_html(item, result))
            for market in MARKETS:
                present = [s for s in item["sites"] if item["sites"][s].get(market)]
                if len(present) < 2:
                    continue
                picks = {r["pick_norm"] for s in present for r in item["sites"][s][market] if r.get("pick_norm")}
                if len(picks) == 1 and "" not in picks:
                    agree_l += 1
                elif len(picks) > 1:
                    split_l += 1
        league_counts[league] = len(cards)
        sections.append(
            f'<div class="league">{_esc(league)} '
            f'<span class="lcount">{len(cards)} fixture(s) &middot; {agree_l} agree &middot; {split_l} split</span></div>'
            + "".join(cards)
        )

    chips = ['<button class="chip active" data-league="">All</button>']
    for league in sorted(league_counts):
        chips.append(
            f'<button class="chip" data-league="{_esc(league)}">{_esc(league)} <b>({league_counts[league]})</b></button>'
        )

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stats = (
        f"<b>{fixtures}</b> fixture(s) &middot; <b>{agreements}</b> market agreement(s) "
        f"&middot; <b>{splits}</b> split(s)"
    )
    return PAGE.format(
        stats=stats,
        chips="".join(chips),
        accuracy=_accuracy_html(grade_result),
        body="".join(sections),
        generated=now,
        count=fixtures,
    )


def write_html(path: str | os.PathLike | None = None) -> Path:
    if path is None:
        path = CONSENSUS_DIR / "consensus.html"
    out = Path(path)
    out.write_text(build_html(upcoming_only=True), encoding="utf-8")
    return out
from __future__ import annotations

import datetime as dt
import html as html_mod
import os
import re
from pathlib import Path
from string import Template

from .config import CANONICAL_DIR, CONSENSUS_DIR
from .ev import build_ev, group_by_fixture
from .report import (
    MARKETS,
    MARKET_LABELS,
    agreement_tag,
    build_report_data,
    majority_pick,
    picks_by_site,
)
from .odds import rebind
from .results import attach_results, evaluate_pick, grade, load_results
from .storage import read_csv

SITES_ORDER = (
    "forebet",
    "eaglepredict",
    "whoscored",
    "flashscore",
    "sportsgambler",
    "sportytrader",
)
SITE_NAMES = {
    "forebet": "Forebet",
    "eaglepredict": "EaglePredict",
    "whoscored": "WhoScored",
    "flashscore": "Flashscore",
    "sportsgambler": "SportsGambler",
    "sportytrader": "SportyTrader",
}
SITE_TAGS = {
    "forebet": "fore",
    "eaglepredict": "eagl",
    "whoscored": "whos",
    "flashscore": "fscr",
    "sportsgambler": "sgam",
    "sportytrader": "strd",
}
MARKET_SHORT = {
    "1x2": "1X2",
    "over_under": "O/U",
    "btts": "BTTS",
    "correct_score": "CS",
    "double_chance": "DC",
}
LEAGUE_ALIASES = {"laliga": "La Liga"}
DAYS_BACK_DEFAULT = 2

# Only these sites record a real price for the row's own pick. Everywhere else
# `note` is something else: forebet duplicates one fixture-level average across
# markets, sportsgambler/sportytrader quote their own (different) tip, and
# flashscore carries prose.
ODDS_SITES = ("whoscored", "eaglepredict")

PAGE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Prediction Consensus</title>
<style>
  :root {
    --bg: #0b0e14; --panel: #11151d; --card: #151a24; --card2: #1a2030;
    --line: #242b3a; --line2: #2e3648;
    --txt: #e6e9ef; --muted: #8b93a3; --dim: #5f6775;
    --accent: #5b9cff; --ok: #2ecc71; --warn: #f1c40f; --bad: #e74c3c;
    --stick: 0px;
    color-scheme: dark;
  }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  body {
    margin: 0; background: var(--bg); color: var(--txt); padding: 0 16px 40px;
    font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    -webkit-text-size-adjust: 100%;
  }
  button { font: inherit; }

  .wrap { max-width: 1180px; margin: 0 auto; }

  header.top {
    display: flex; flex-wrap: wrap; gap: 18px 24px; align-items: flex-end;
    justify-content: space-between; padding: 26px 0 18px;
  }
  h1 { font-size: 24px; margin: 0; letter-spacing: -.02em; }
  .sub { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
  .kpis { display: grid; grid-template-columns: repeat(4, minmax(96px, 1fr)); gap: 8px; }
  .kpi {
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 9px 12px; min-width: 96px;
  }
  .kpi-v { display: block; font-size: 20px; font-weight: 700; letter-spacing: -.02em; }
  .kpi-l { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase;
    letter-spacing: .06em; margin-top: 1px; }
  .kpi.ok .kpi-v { color: var(--ok); }
  .kpi.acc .kpi-v { color: var(--accent); }

  .toolbar {
    position: sticky; top: 0; z-index: 30; background: rgba(11,14,20,.94);
    backdrop-filter: blur(8px); border-bottom: 1px solid var(--line);
    margin: 0 -16px; padding: 10px 16px 8px;
  }
  .trow { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  #q {
    background: var(--card); border: 1px solid var(--line2); color: var(--txt);
    border-radius: 8px; padding: 7px 11px; font: inherit; width: 210px; min-width: 0;
  }
  #q::placeholder { color: var(--dim); }
  #q:focus { outline: none; border-color: var(--accent); }
  .spacer { flex: 1 1 auto; }

  .tabs { display: flex; gap: 4px; background: var(--card); border: 1px solid var(--line);
    border-radius: 9px; padding: 3px; }
  .tab {
    background: none; border: 0; color: var(--muted); padding: 5px 10px;
    border-radius: 6px; cursor: pointer; font-size: 12.5px; white-space: nowrap;
  }
  .tab:hover { color: var(--txt); }
  .tab[aria-pressed="true"] { background: var(--accent); color: #07101f; font-weight: 600; }
  .tab b { font-weight: 700; opacity: .75; }
  .tab.zero:not([aria-pressed="true"]),
  .chip.zero:not([aria-pressed="true"]) { opacity: .38; }

  .chk { display: flex; gap: 6px; align-items: center; color: var(--muted);
    font-size: 12.5px; cursor: pointer; user-select: none; white-space: nowrap; }
  .chk input { accent-color: var(--accent); }
  .btn {
    background: var(--card); border: 1px solid var(--line2); color: var(--muted);
    border-radius: 8px; padding: 6px 11px; cursor: pointer; font-size: 12.5px;
  }
  .btn:hover { color: var(--txt); border-color: var(--accent); }
  .count { color: var(--dim); font-size: 12.5px; font-variant-numeric: tabular-nums;
    white-space: nowrap; }

  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
  .chip {
    background: var(--card); border: 1px solid var(--line2); color: var(--muted);
    border-radius: 20px; padding: 4px 11px; font-size: 12.5px; cursor: pointer;
    white-space: nowrap;
  }
  .chip:hover { color: var(--txt); }
  .chip[aria-pressed="true"] { border-color: var(--accent); color: var(--accent);
    background: rgba(91,156,255,.12); }
  .chip b { color: inherit; opacity: .7; font-weight: 600; }

  main { padding-top: 6px; }
  details.panel {
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    margin: 14px 0;
  }
  details.panel > summary {
    cursor: pointer; padding: 12px 16px; font-weight: 600; font-size: 13.5px;
    color: var(--accent); list-style: none; display: flex; align-items: center; gap: 8px;
  }
  details.panel > summary::-webkit-details-marker { display: none; }
  details.panel > summary::before { content: "\\25B8"; color: var(--muted); font-size: 11px;
    transition: transform .15s; }
  details.panel[open] > summary::before { transform: rotate(90deg); }
  details.panel > summary .hint { color: var(--dim); font-weight: 400; font-size: 12px; }
  .panel-body { padding: 4px 16px 16px; }
  .panel-body .tbl-wrap { overflow-x: auto; }
  .panel h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .07em;
    color: var(--muted); margin: 16px 0 8px; }

  .acc-table th, .acc-table td { padding: 5px 10px; border-top: 1px solid var(--line);
    text-align: left; }
  .acc-table thead th { color: var(--muted); font-size: 11px; text-transform: uppercase;
    letter-spacing: .05em; border-top: none; }
  /* keep the row label visible while the accuracy table scrolls sideways */
  .acc-table th:first-child, .acc-table td:first-child {
    position: sticky; left: 0; background: var(--panel); }
  .acc-table thead th:first-child { z-index: 2; }
  .hit { color: var(--ok); font-weight: 700; }
  .miss { color: var(--bad, #e74c3c); font-weight: 700; }
  .rate { color: var(--dim); font-size: 12px; }
  .recent { display: flex; flex-direction: column; gap: 8px; }
  .recent-row { font-size: 13px; }
  .recent-row b { font-weight: 600; display: block; margin-bottom: 3px; }
  .recent-row .marks { display: flex; flex-wrap: wrap; gap: 4px 8px; }
  .recent-row .marks span { white-space: nowrap; font-size: 12px; }

  section.day { margin-top: 22px; }
  .day-head {
    position: sticky; top: var(--stick, 62px); z-index: 10;
    background: var(--bg); display: flex; gap: 10px; align-items: baseline;
    flex-wrap: wrap; margin: 0 -4px; padding: 8px 4px 7px;
    border-bottom: 2px solid var(--line2); font-size: 15px; font-weight: 700;
  }
  .day-head .dh-tag {
    font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em;
    color: #07101f; background: var(--accent); border-radius: 4px; padding: 1px 6px;
  }
  .day-head .dh-tag.finished { background: var(--dim); color: var(--bg); }
  .day-head .dh-count { color: var(--muted); font-weight: 400; font-size: 12.5px; }
  .lg-div {
    color: var(--muted); font-size: 11.5px; text-transform: uppercase;
    letter-spacing: .08em; margin: 14px 0 7px; display: flex; align-items: center; gap: 8px;
  }
  .lg-div::after { content: ""; flex: 1; height: 1px; background: var(--line); }

  .card {
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    margin-bottom: 8px; overflow: hidden;
  }
  .card.open { border-color: var(--line2); }
  .card-head {
    display: flex; gap: 10px 14px; align-items: center; width: 100%; text-align: left;
    background: none; border: 0; color: inherit; padding: 11px 14px; cursor: pointer;
  }
  .card-head:hover { background: var(--card2); }
  .card-head:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .caret { color: var(--dim); font-size: 10px; width: 10px; flex: none;
    transition: transform .15s; }
  .card.open .caret { transform: rotate(90deg); color: var(--accent); }
  .teams { font-size: 15px; font-weight: 600; flex: 1 1 240px; min-width: 0; }
  .teams .vs { color: var(--dim); font-weight: 400; font-size: 12px; margin: 0 6px; }
  .hmeta { display: flex; gap: 8px; align-items: center; flex: none; }
  .time { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 13px; }
  .score {
    background: rgba(46,204,113,.16); color: var(--ok); font-weight: 700; font-size: 12.5px;
    border-radius: 5px; padding: 1px 8px; white-space: nowrap;
  }
  .lg-name { color: var(--dim); font-size: 12px; white-space: nowrap; }
  .pills { display: flex; gap: 5px; flex-wrap: wrap; justify-content: flex-end; flex: 2 1 auto; }
  .pill {
    display: inline-flex; gap: 5px; align-items: baseline; font-size: 11.5px;
    background: var(--bg); border: 1px solid var(--line2); border-radius: 20px;
    padding: 2px 9px; white-space: nowrap;
  }
  .pill i { font-style: normal; color: var(--dim); font-size: 10px; font-weight: 700;
    letter-spacing: .04em; }
  .pill b { font-weight: 700; color: var(--txt); }
  .pill em { font-style: normal; color: var(--muted); font-variant-numeric: tabular-nums; }
  .pill.agree { border-color: rgba(46,204,113,.45); }
  .pill.agree b { color: var(--ok); }
  .pill.split { border-color: rgba(241,196,15,.45); }
  .pill.split b { color: var(--warn); }
  .pill.single { border-color: var(--line2); }
  .pill.single b { color: var(--muted); }
  .pill .g { font-weight: 700; }
  .pill .g.hit { color: var(--ok); }
  .pill .g.miss { color: #e74c3c; }

  .card-body { border-top: 1px solid var(--line); padding: 2px 0 6px; }
  .tbl-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  .tbl-wrap table { min-width: 560px; }
  th, td { text-align: left; padding: 6px 7px; border-bottom: 1px solid var(--line);
    vertical-align: top; }
  tbody tr:last-child th, tbody tr:last-child td { border-bottom: 0; }
  thead th {
    color: var(--muted); font-size: 10px; text-transform: uppercase;
    letter-spacing: .05em; font-weight: 600; border-bottom: 1px solid var(--line2);
  }
  th.market, td.market {
    position: sticky; left: 0; background: var(--card); z-index: 1;
    width: 104px; min-width: 104px; font-weight: 600; font-size: 12.5px;
    border-right: 1px solid var(--line);
  }
  thead th.market { background: var(--card); }
  td.pick-cell { min-width: 92px; max-width: 150px; }
  .pick { font-weight: 700; }
  .pick.hl { color: var(--accent); background: rgba(91,156,255,.14); border-radius: 4px;
    padding: 0 5px; }
  .probs { color: var(--dim); font-size: 11.5px; margin-left: 4px;
    font-variant-numeric: tabular-nums; }
  .odds { display: inline-block; margin-top: 3px; color: var(--muted); font-size: 11.5px;
    font-variant-numeric: tabular-nums; }
  .odds.best { color: var(--ok); font-weight: 700; }
  .odds.best::before { content: "\\25B2"; font-size: 8px; margin-right: 3px; }
  .avg { display: inline-block; margin-top: 3px; color: var(--dim); font-size: 11.5px;
    font-variant-numeric: tabular-nums; cursor: help; }
  .tip { display: inline-block; margin-top: 3px; color: var(--dim); font-size: 11.5px;
    max-width: 148px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    cursor: help; border-bottom: 1px dotted var(--line2); }
  td.cons { min-width: 78px; max-width: 116px; }
  td.cons .cval { font-weight: 700; color: var(--accent); font-size: 14px;
    overflow-wrap: anywhere; }
  td.cons .cval.tie { color: var(--warn); font-size: 13px; }
  td.cons .str { display: block; color: var(--muted); font-size: 11px;
    font-variant-numeric: tabular-nums; margin-top: 1px; }
  .meter { display: block; height: 3px; width: 74px; max-width: 100%;
    background: var(--line); border-radius: 2px; margin-top: 4px; overflow: hidden; }
  .meter i { display: block; height: 100%; background: var(--accent); }
  .meter.full i { background: var(--ok); }
  td.result { min-width: 88px; }
  .cres { display: inline-block; font-weight: 700; font-size: 13px; margin-right: 5px; }
  .cres.hit { color: var(--ok); }
  .cres.miss { color: #e74c3c; }
  .sres {
    display: inline-block; font-size: 10px; font-weight: 700; border-radius: 4px;
    padding: 1px 5px; margin: 2px 3px 0 0; letter-spacing: .03em;
  }
  .sres.hit { color: var(--ok); background: rgba(46,204,113,.14); }
  .sres.miss { color: #e74c3c; background: rgba(231,76,60,.14); }
  .tag {
    display: inline-block; font-size: 10.5px; font-weight: 700; letter-spacing: .05em;
    text-transform: uppercase; border-radius: 4px; padding: 2px 7px; white-space: nowrap;
  }
  .tag.agree { color: var(--ok); background: rgba(46,204,113,.14); }
  .tag.split { color: var(--warn); background: rgba(241,196,15,.14); }
  .tag.single { color: var(--muted); background: rgba(139,147,163,.12); }
  .na { color: var(--dim); }
  .no-picks { color: var(--muted); font-size: 13px; padding: 12px 14px; }

  /* value / EV */
  .vpill {
    display: inline-flex; gap: 4px; align-items: baseline; font-size: 11px;
    font-weight: 700; border-radius: 4px; padding: 1px 7px; white-space: nowrap;
    background: rgba(46,204,113,.14); color: var(--ok); letter-spacing: .03em;
  }
  .vpill.edge { background: rgba(91,156,255,.12); color: var(--accent); }
  .vpill em { font-style: normal; color: var(--muted); font-weight: 600; }
  .val-table td, .val-table th { padding: 5px 9px; }
  .val-table td.num { font-variant-numeric: tabular-nums; text-align: right; }
  .val-table .edge-pos { color: var(--ok); font-weight: 700; }
  .val-table .edge-neg { color: var(--bad); font-weight: 700; }
  .val-table .mkt { font-weight: 700; font-size: 12px; white-space: nowrap; }
  .val-table .pickv { font-weight: 700; }
  .val-table .prov { color: var(--dim); font-size: 11px; }

  .empty-state {
    text-align: center; padding: 60px 16px; color: var(--muted);
    border: 1px dashed var(--line2); border-radius: 12px; margin-top: 18px;
  }
  .empty-state b { display: block; color: var(--txt); font-size: 15px; margin-bottom: 4px; }

  footer {
    max-width: 1180px; margin: 34px auto 0; padding-top: 14px;
    border-top: 1px solid var(--line); color: var(--dim); font-size: 12px;
    display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  }
  kbd {
    background: var(--card); border: 1px solid var(--line2); border-bottom-width: 2px;
    border-radius: 4px; padding: 0 5px; font: 11px ui-monospace, monospace;
  }

  @media (max-width: 900px) {
    header.top { align-items: flex-start; }
    .kpis { grid-template-columns: repeat(2, minmax(96px, 1fr)); width: 100%; }
    .pills { justify-content: flex-start; flex-basis: 100%; }
    .card-head { flex-wrap: wrap; }
  }
  @media (max-width: 720px) {
    body { padding: 0 10px 32px; }
    .toolbar { margin: 0 -10px; padding: 8px 10px; }
    .trow { gap: 6px; }
    #q { width: 100%; order: -1; }
    .spacer { display: none; }
    .tabs { overflow-x: auto; max-width: 100%; }
    .chips { flex-wrap: nowrap; overflow-x: auto; padding-bottom: 4px;
      scrollbar-width: thin; margin-left: -10px; margin-right: -10px;
      padding-left: 10px; padding-right: 10px; }
    /* keep the caret on the team-name row; 10px caret + 14px column gap */
    .teams { flex: 1 1 calc(100% - 24px); font-size: 14.5px; }
    h1 { font-size: 20px; }
    .day-head { font-size: 14px; }
  }
  @media print {
    .toolbar, .caret { display: none; }
    .card { break-inside: avoid; }
    .card-body { display: block !important; }
  }
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div>
    <h1>Prediction Consensus</h1>
    <p class="sub">$sub</p>
  </div>
  <div class="kpis">$kpis</div>
</header>
</div>

<div class="toolbar" id="toolbar">
<div class="wrap">
  <div class="trow">
    <input id="q" type="search" placeholder="Search teams…" autocomplete="off"
           aria-label="Search fixtures by team or league">
    <div class="tabs" role="group" aria-label="Filter by date" id="tabs">$tabs</div>
    <span class="spacer"></span>
    <label class="chk"><input type="checkbox" id="hide1" checked> Hide 1-site</label>
    <button class="btn" type="button" id="expandAll">Expand</button>
    <button class="btn" type="button" id="collapseAll">Collapse</button>
    <span class="count" id="count">$count</span>
  </div>
  <div class="chips" id="chips" role="group" aria-label="Filter by league">$chips</div>
</div>
</div>

<div class="wrap">
<main>
$value
$accuracy
$body
<div class="empty-state" id="empty" hidden>
  <b>No fixtures match</b>
  Clear the search or pick another date or league.
</div>
</main>
<footer>
  <span>Generated $generated &middot; static HTML, no network needed</span>
  <span>Press <kbd>/</kbd> to search &middot; <kbd>Esc</kbd> to clear</span>
</footer>
</div>

<script>
(function(){
  var q = document.getElementById('q');
  var hide1 = document.getElementById('hide1');
  var countEl = document.getElementById('count');
  var empty = document.getElementById('empty');
  var toolbar = document.getElementById('toolbar');
  var cards = [].slice.call(document.querySelectorAll('.card'));
  var days = [].slice.call(document.querySelectorAll('section.day'));
  var chips = [].slice.call(document.querySelectorAll('.chip'));
  var tabs = [].slice.call(document.querySelectorAll('.tab'));
  var when = 'all';
  var league = '';
  var total = cards.length;
  var autoOpened = [];

  function countMatching(text, hideSingle) {
    return cards.filter(function(c) {
      return matches(c, text, hideSingle, true, true);
    }).length;
  }

  function setOpen(card, open) {
    card.classList.toggle('open', open);
    var head = card.querySelector('.card-head');
    var body = card.querySelector('.card-body');
    if (head) head.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (body) body.hidden = !open;
  }

  function matches(c, text, hideSingle, useWhen, useLeague) {
    if (useWhen && when !== 'all' && c.getAttribute('data-when') !== when) return false;
    if (useLeague && league && c.getAttribute('data-league') !== league) return false;
    if (hideSingle && parseInt(c.getAttribute('data-sites'), 10) < 2) return false;
    if (text) {
      if ((c.getAttribute('data-search') || '').indexOf(text) === -1) return false;
    }
    return true;
  }

  function setCount(el, n) {
    var b = el.querySelector('b');
    if (b) b.textContent = n;
    el.classList.toggle('zero', n === 0);
  }

  function apply() {
    var text = (q.value || '').trim().toLowerCase();
    var hideSingle = hide1.checked;
    var shown = 0;

    cards.forEach(function(c) {
      var ok = matches(c, text, hideSingle, true, true);
      c.hidden = !ok;
      if (ok) shown++;

      // Searching is an inspection gesture: reveal the detail for matches and
      // put back only the cards this search opened, so a manual expand survives.
      var opened = autoOpened.indexOf(c) !== -1;
      if (text && ok && !c.classList.contains('open')) {
        autoOpened.push(c);
        setOpen(c, true);
      } else if (!text && opened) {
        autoOpened.splice(autoOpened.indexOf(c), 1);
        setOpen(c, false);
      } else if (text && !ok && opened) {
        autoOpened.splice(autoOpened.indexOf(c), 1);
        setOpen(c, false);
      }
    });

    // facet counts ignore their own filter so the numbers stay truthful
    tabs.forEach(function(t) {
      var saved = when;
      when = t.getAttribute('data-when') || 'all';
      setCount(t, countMatching(text, hideSingle));
      when = saved;
    });
    chips.forEach(function(ch) {
      var saved = league;
      league = ch.getAttribute('data-league') || '';
      setCount(ch, countMatching(text, hideSingle));
      league = saved;
    });

    days.forEach(function(d) {
      var any = [].slice.call(d.querySelectorAll('.card')).some(function(c) {
        return !c.hidden;
      });
      d.hidden = !any;
    });
    countEl.textContent = shown + ' of ' + total + ' fixtures';
    empty.hidden = shown > 0;
    syncStick();
  }

  function syncStick() {
    if (toolbar && document.documentElement.style) {
      document.documentElement.style.setProperty('--stick', toolbar.offsetHeight + 'px');
    }
  }

  q.addEventListener('input', apply);
  hide1.addEventListener('change', apply);

  chips.forEach(function(chip) {
    chip.addEventListener('click', function() {
      league = chip.getAttribute('data-league') || '';
      chips.forEach(function(c) {
        c.setAttribute('aria-pressed', c === chip ? 'true' : 'false');
      });
      apply();
    });
  });

  tabs.forEach(function(tab) {
    tab.addEventListener('click', function() {
      when = tab.getAttribute('data-when') || 'all';
      tabs.forEach(function(t) {
        t.setAttribute('aria-pressed', t === tab ? 'true' : 'false');
      });
      apply();
    });
  });

  document.getElementById('expandAll').addEventListener('click', function() {
    cards.forEach(function(c) { if (!c.hidden) setOpen(c, true); });
  });
  document.getElementById('collapseAll').addEventListener('click', function() {
    cards.forEach(function(c) { setOpen(c, false); });
  });

  cards.forEach(function(card) {
    card.querySelector('.card-head').addEventListener('click', function() {
      setOpen(card, !card.classList.contains('open'));
    });
  });

  document.addEventListener('keydown', function(e) {
    var t = (e.target && e.target.tagName) || '';
    if (e.key === '/' && t !== 'INPUT' && t !== 'TEXTAREA') {
      e.preventDefault();
      q.focus();
      q.select();
    } else if (e.key === 'Escape' && document.activeElement === q) {
      q.value = '';
      apply();
      q.blur();
    }
  });

  window.addEventListener('resize', syncStick);
  syncStick();
  apply();
})();
</script>
</body>
</html>
""")


def _esc(text: str) -> str:
    return html_mod.escape(str(text or ""))


def _league_label(raw: str) -> str:
    raw = (raw or "").strip()
    return LEAGUE_ALIASES.get(raw.lower(), raw) or "Unknown"


def _kickoff_time(kickoff: str) -> str:
    m = re.search(r"\b(\d{1,2}:\d{2})\b", kickoff or "")
    if not m:
        return "--:--"
    h, mi = m.group(1).split(":")
    return f"{int(h):02d}:{mi}"


def _parse_odds(site: str, note: str) -> float | None:
    if site not in ODDS_SITES:
        return None
    note = (note or "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", note):
        return None
    return float(note)


def _team_display_names() -> dict[str, str]:
    best: dict[str, tuple[tuple[bool, int], str]] = {}
    for row in read_csv(CANONICAL_DIR / "teams.csv"):
        cid = (row.get("canonical_id") or "").strip()
        name = (row.get("team_name") or "").strip()
        if not cid or not name:
            continue
        key = (any(ord(ch) > 127 for ch in name), len(name))
        if cid not in best or key > best[cid][0]:
            best[cid] = (key, name)
    return {cid: val[1] for cid, val in best.items()}


def _pretty(slug: str, names: dict[str, str]) -> str:
    if slug in names:
        return names[slug]
    return slug.replace("-", " ").title()


def _probs_html(market: str, row: dict) -> str:
    if market == "1x2" and row.get("p1"):
        return (
            f'<span class="probs" title="Home / Draw / Away">'
            f'{_esc(row["p1"])}/{_esc(row["p2"])}/{_esc(row["p3"])}</span>'
        )
    if market in ("over_under", "btts") and row.get("p1"):
        label = "Over / Under" if market == "over_under" else "Yes / No"
        return f'<span class="probs" title="{label}">{_esc(row["p1"])}/{_esc(row["p2"])}</span>'
    return ""


def _odds_html(site: str, note: str, best: bool) -> str:
    note = (note or "").strip()
    if not note:
        return ""
    odds = _parse_odds(site, note)
    if odds is not None:
        cls = "odds best" if best else "odds"
        shown = note if len(note) <= 14 else f"{odds:g}"
        return f'<span class="{cls}" title="{_esc(note)}">{_esc(shown)}</span>'
    if note.startswith("avg="):
        shown = note.replace("avg=", "avg ")
        return (
            f'<span class="avg" title="Forebet average odds for this fixture, '
            f'not a price on this pick">{_esc(shown)}</span>'
        )
    words = note.split()
    shown = " ".join(words[:5]) + ("…" if len(words) > 5 else "")
    return f'<span class="tip" title="{_esc(note)}">{_esc(shown)}</span>'


def _site_cell(site: str, market: str, rows: list[dict], highlight: bool, best: bool) -> str:
    if not rows:
        return '<span class="na">&ndash;</span>'
    row = rows[0]
    pick = row.get("pick_norm") or row.get("pick") or "-"
    pick_cls = "pick hl" if highlight else "pick"
    parts = [f'<span class="{pick_cls}">{_esc(pick)}</span>', _probs_html(market, row)]
    odds = _odds_html(site, row.get("note"), best)
    if odds:
        parts.append(odds)
    return "".join(parts)


def _pills_html(sites: dict, hg: int | None, ag: int | None) -> str:
    pills = []
    for market in MARKETS:
        votes = picks_by_site(sites, market)
        if not votes:
            continue
        tag = agreement_tag(sites, market)
        majority = majority_pick(sites, market)
        n = len(votes)
        if majority:
            agree_n = sum(1 for v in votes.values() if v == majority)
            label, strength, cls = majority, f"{agree_n}/{n}", tag
        else:
            label = "/".join(sorted(set(votes.values())))
            strength, cls = f"{n} tied", tag
        grade_html = ""
        if hg is not None and majority:
            ok = evaluate_pick(market, majority, hg, ag)
            if ok is not None:
                grade_html = f'<span class="g {"hit" if ok else "miss"}">{"&#10003;" if ok else "&#10007;"}</span>'
        pills.append(
            f'<span class="pill {cls}"><i>{_esc(MARKET_SHORT[market])}</i>'
            f"<b>{_esc(label)}</b><em>{_esc(strength)}</em>{grade_html}</span>"
        )
    return "".join(pills)


def _fixture_html(item: dict, *, result: dict | None, names: dict[str, str],
                  index: int, league: str) -> str:
    fx = item["fixture"]
    sites = item["sites"]
    kickoff = _kickoff_time(fx["kickoff"])
    date_label = dt.date.fromisoformat(fx["date"]).strftime("%a %d %b")
    home = _pretty(fx["home_id"], names)
    away = _pretty(fx["away_id"], names)
    when = _when(fx["date"])

    present = [
        s for s in SITES_ORDER
        if any(sites.get(s, {}).get(m) for m in MARKETS)
    ]
    search = " ".join([
        home, away, fx["home_id"], fx["away_id"], league, fx["date"], kickoff,
    ]).lower()

    hg = ag = None
    if result:
        try:
            hg, ag = int(result["home_goals"]), int(result["away_goals"])
        except (TypeError, ValueError):
            hg = ag = None
    score_html = (
        f'<span class="score">{_esc(hg)}&ndash;{_esc(ag)} FT</span>'
        if hg is not None else ""
    )

    head = (
        '<button class="card-head" type="button" aria-expanded="false" '
        f'aria-controls="fx-body-{index}">'
        f'<span class="caret" aria-hidden="true">&#9654;</span>'
        f'<span class="teams">{_esc(home)}<span class="vs">vs</span>{_esc(away)}</span>'
        f'<span class="hmeta"><span class="time">{_esc(kickoff)}</span>{score_html}'
        f'<span class="lg-name">{_esc(league)}</span></span>'
        f'<span class="pills">{_pills_html(sites, hg, ag)}</span>'
        "</button>"
    )

    if not present:
        body = '<div class="card-body" hidden><p class="no-picks">No predictions yet.</p></div>'
        return (
            f'<article class="card" data-league="{_esc(league)}" data-when="{when}" '
            f'data-sites="0" data-search="{_esc(search)}">'
            f"{head}{body}</article>"
        )

    has_result = hg is not None
    headers = (
        '<th class="market">Market</th>'
        + "".join(f"<th>{_esc(SITE_NAMES[s])}</th>" for s in present)
        + "<th>Consensus</th>"
        + ("<th>Result</th>" if has_result else "")
        + "<th>Agree</th>"
    )

    rows = []
    for market in MARKETS:
        rows_by_site = {s: sites.get(s, {}).get(market, []) for s in present}
        if not any(rows_by_site.values()):
            continue
        tag = agreement_tag(sites, market)
        majority = majority_pick(sites, market)
        votes = picks_by_site(sites, market)

        best_val = None
        if majority:
            same = [
                _parse_odds(s, rows_by_site[s][0].get("note"))
                for s in present
                if rows_by_site[s]
                and rows_by_site[s][0].get("pick_norm") == majority
            ]
            same = [v for v in same if v is not None]
            if len(same) >= 2:
                best_val = max(same)

        cells = []
        for s in present:
            r = rows_by_site[s]
            hl = bool(r) and majority is not None and r[0].get("pick_norm") == majority
            best = (
                bool(r) and best_val is not None
                and _parse_odds(s, r[0].get("note")) == best_val
            )
            cells.append(f'<td class="pick-cell">{_site_cell(s, market, r, hl, best)}</td>')

        if majority:
            agree_n = sum(1 for v in votes.values() if v == majority)
            pct = round(agree_n * 100 / len(votes)) if votes else 0
            cons = (
                f'<td class="cons"><span class="cval">{_esc(majority)}</span>'
                f'<span class="str">{agree_n}/{len(votes)} sites</span>'
                f'<span class="meter{" full" if pct == 100 else ""}"><i style="width:{pct}%"></i></span></td>'
            )
        elif votes:
            tied = "/".join(sorted(set(votes.values())))
            cons = (
                f'<td class="cons"><span class="cval tie">{_esc(tied)}</span>'
                f'<span class="str">split</span></td>'
            )
        else:
            cons = '<td class="cons"><span class="na">&ndash;</span></td>'

        res = ""
        if has_result:
            marks = []
            if majority:
                ok = evaluate_pick(market, majority, hg, ag)
                if ok is not None:
                    marks.append(
                        f'<span class="cres {"hit" if ok else "miss"}" '
                        f'title="Consensus {_esc(majority)} at {_esc(hg)}-{_esc(ag)}">'
                        f'{"&#10003;" if ok else "&#10007;"}</span>'
                    )
            for s in present:
                r = rows_by_site[s]
                if not r:
                    continue
                pick = r[0].get("pick_norm") or r[0].get("pick") or ""
                ok = evaluate_pick(market, pick, hg, ag)
                if ok is None:
                    continue
                marks.append(
                    f'<span class="sres {"hit" if ok else "miss"}" '
                    f'title="{_esc(SITE_NAMES[s])}: {_esc(pick)}">'
                    f'{_esc(SITE_TAGS[s])}</span>'
                )
            res = '<td class="result">' + ("".join(marks) or '<span class="na">&ndash;</span>') + "</td>"

        rows.append(
            f'<tr><td class="market">{_esc(MARKET_LABELS[market])}</td>'
            + "".join(cells)
            + cons + res
            + f'<td><span class="tag {tag}">{_esc(tag)}</span></td></tr>'
        )

    body = (
        f'<div class="card-body" id="fx-body-{index}" hidden><div class="tbl-wrap">'
        f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        "</div></div>"
    )
    return (
        f'<article class="card" data-league="{_esc(league)}" data-when="{when}" '
        f'data-sites="{len(present)}" data-search="{_esc(search)}">'
        f"{head}{body}</article>"
    )


def _when(date_iso: str) -> str:
    today = dt.date.today()
    d = dt.date.fromisoformat(date_iso)
    if d < today:
        return "finished"
    if d == today:
        return "today"
    if d == today + dt.timedelta(days=1):
        return "tomorrow"
    return "later"


def _accuracy_html(grade_result: dict) -> str:
    stats = grade_result.get("stats", {})
    consensus = grade_result.get("consensus", {})
    if not stats and not consensus.get("agree") and not consensus.get("majority"):
        return (
            '<details class="panel"><summary>Accuracy'
            '<span class="hint">no results recorded yet</span></summary></details>'
        )

    sites = sorted({s for (s, m) in stats})
    markets = ["1x2", "over_under", "btts", "correct_score", "double_chance"]
    table = ['<table class="acc-table"><thead><tr><th>Site</th>']
    for m in markets:
        table.append(f"<th>{_esc(MARKET_LABELS[m])}</th>")
    table.append("<th>Overall</th></tr></thead><tbody>")

    for site in sites:
        cells = [f"<td><b>{_esc(SITE_NAMES.get(site, site))}</b></td>"]
        totals = hits = 0
        for m in markets:
            vals = stats.get((site, m), [])
            if vals:
                n, h = len(vals), sum(vals)
                totals += n
                hits += h
                cls = "hit" if h / n >= 0.5 else "miss"
                cells.append(
                    f'<td><span class="{cls}">{h}/{n}</span> '
                    f'<span class="rate">({h / n * 100:.0f}%)</span></td>'
                )
            else:
                cells.append('<td class="na">&ndash;</td>')
        if totals:
            cells.append(f"<td><b>{hits}/{totals} ({hits / totals * 100:.0f}%)</b></td>")
        else:
            cells.append('<td class="na">&ndash;</td>')
        table.append("<tr>" + "".join(cells) + "</tr>")
    table.append("</tbody></table>")

    agree = consensus.get("agree", {})
    majority = consensus.get("majority", {})
    consensus_html = ""
    if agree or majority:
        consensus_html = (
            "<h3>Consensus accuracy</h3>"
            '<div class="tbl-wrap">'
            '<table class="acc-table"><thead><tr><th>Market</th>'
            "<th>Agree (2+ same)</th><th>Majority (split)</th></tr></thead><tbody>"
        )
        for m in markets:
            cells = [f"<td>{_esc(MARKET_LABELS[m])}</td>"]
            for source in (agree, majority):
                vals = source.get(m, [])
                if vals:
                    h, n = sum(vals), len(vals)
                    cls = "hit" if h / n >= 0.5 else "miss"
                    cells.append(
                        f'<td><span class="{cls}">{h}/{n}</span> '
                        f'<span class="rate">({h / n * 100:.0f}%)</span></td>'
                    )
                else:
                    cells.append('<td class="na">&ndash;</td>')
            consensus_html += "<tr>" + "".join(cells) + "</tr>"
        consensus_html += "</tbody></table></div>"

    per_fixture = grade_result.get("per_fixture", {})
    recent = sorted(per_fixture, key=lambda f: f.split("|")[0], reverse=True)[:6]
    recent_html = []
    for fid in recent:
        entries = per_fixture[fid]
        e0 = entries[0]
        marks = "".join(
            f'<span class="{"hit" if e["result"] else "miss"}">'
            f'{"&#10003;" if e["result"] else "&#10007;"} {_esc(SITE_TAGS.get(e["site"], e["site"][:4]))} '
            f'{_esc(MARKET_LABELS.get(e["market"], e["market"]))} '
            f'[{_esc(e["pick"])}]</span>'
            for e in entries[:10]
        )
        recent_html.append(
            f'<div class="recent-row"><b>{_esc(e0["home"])} {_esc(e0["home_goals"])}-'
            f'{_esc(e0["away_goals"])} {_esc(e0["away"])}</b>'
            f'<span class="marks">{marks}</span></div>'
        )

    total_hits = sum(sum(v) for v in stats.values())
    total_n = sum(len(v) for v in stats.values())
    hint = f"{total_hits}/{total_n} picks correct" if total_n else ""

    return (
        '<details class="panel"><summary>Accuracy'
        f'<span class="hint">{_esc(hint)}</span></summary><div class="panel-body">'
        "<h3>By site &amp; market</h3>"
        f'<div class="tbl-wrap">{"".join(table)}</div>'
        + consensus_html
        + "<h3>Most recent graded fixtures</h3>"
        + f'<div class="recent">{"".join(recent_html)}</div>'
        + "</div></details>"
    )


def _kpis_html(fixtures: int, agreements: int, splits: int, grade_result: dict,
               value_count: int = 0) -> str:
    stats = grade_result.get("stats", {})
    total_hits = sum(sum(v) for v in stats.values())
    total_n = sum(len(v) for v in stats.values())
    hit_rate = f"{total_hits / total_n * 100:.0f}%" if total_n else "&ndash;"
    kpis = (
        f'<div class="kpi"><span class="kpi-v">{fixtures}</span>'
        '<span class="kpi-l">Fixtures</span></div>'
        f'<div class="kpi ok"><span class="kpi-v">{agreements}</span>'
        '<span class="kpi-l">Agreements</span></div>'
        f'<div class="kpi"><span class="kpi-v">{splits}</span>'
        '<span class="kpi-l">Splits</span></div>'
        f'<div class="kpi acc"><span class="kpi-v">{hit_rate}</span>'
        '<span class="kpi-l">Hit rate</span></div>'
    )
    if value_count:
        kpis += (
            f'<div class="kpi ok"><span class="kpi-v">{value_count}</span>'
            '<span class="kpi-l">Value</span></div>'
        )
    return kpis


def _ev_rows_html(rows: list[dict], names: dict[str, str], cutoff: str) -> str:
    """Rows for the Value panel: VALUE-flagged first, then by edge descending,
    keeping only the current window (note-priced history is stale)."""
    in_window = [r for r in rows if r["date"] >= cutoff]
    if not in_window:
        return ""
    in_window.sort(key=lambda r: (r["flag"] != "VALUE", -r["edge"]))
    out = []
    for r in in_window:
        home = _pretty(r["home"], names)
        away = _pretty(r["away"], names)
        edge = r["edge"]
        edge_cls = "edge-pos" if edge >= 0 else "edge-neg"
        flag_html = (
            '<span class="vpill">VALUE</span>' if r["flag"] == "VALUE"
            else f'<span class="vpill edge">edge {edge:+.2f}</span>'
        )
        out.append(
            "<tr>"
            f'<td>{_esc(home)} <span class="na">vs</span> {_esc(away)}</td>'
            f'<td class="mkt">{_esc(MARKET_LABELS.get(r["market"], r["market"]))}</td>'
            f'<td class="pickv">{_esc(r["pick"])}</td>'
            f'<td class="num">{r["p_est"]:.2f}</td>'
            f'<td class="num">{r["odds"]:.2f}</td>'
            f'<td class="num">{r["implied"]:.2f}</td>'
            f'<td class="num {edge_cls}">{edge:+.2f}</td>'
            f'<td class="num">{r["ev"]:+.2f}</td>'
            f'<td><span class="prov">{_esc(r["provider"])}</span></td>'
            f"<td>{flag_html}</td>"
            "</tr>"
        )
    return "".join(out)


def _ev_html(rows: list[dict], names: dict[str, str], cutoff: str) -> str:
    total = len(rows)
    if not total:
        return (
            '<details class="panel"><summary>Value (EV)'
            '<span class="hint">run consensus scrape-odds to populate bookmaker prices</span>'
            "</summary></details>"
        )
    body = _ev_rows_html(rows, names, cutoff)
    if not body:
        return (
            '<details class="panel"><summary>Value (EV)'
            f'<span class="hint">{total} priced, none in window</span></summary></details>'
        )
    n_value = sum(1 for r in rows if r["flag"] == "VALUE")
    shown = body.count("<tr>")
    hint = f"{n_value} VALUE &middot; {shown} priced in window"
    table = (
        '<table class="val-table"><thead><tr>'
        "<th>Fixture</th><th>Market</th><th>Pick</th>"
        '<th class="num">P_est</th><th class="num">Odds</th><th class="num">Implied</th>'
        '<th class="num">Edge</th><th class="num">EV</th><th>Book</th><th>Flag</th>'
        "</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )
    return (
        '<details class="panel"><summary>Value (EV)'
        f'<span class="hint">{hint}</span></summary><div class="panel-body">'
        "<h3>Consensus probability vs bookmaker implied</h3>"
        f'<div class="tbl-wrap">{table}</div>'
        "</div></details>"
    )


def build_html(days_back: int = DAYS_BACK_DEFAULT) -> str:
    data = build_report_data()
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=days_back)

    results = load_results()
    grade_result = (
        grade(results)
        if results
        else {"stats": {}, "per_fixture": {}, "consensus": {}}
    )
    attached = attach_results(results) if results else {}
    names = _team_display_names()

    rebind()
    ev_rows = build_ev(min_date=cutoff.isoformat())
    value_html = _ev_html(ev_rows, names, cutoff.isoformat())

    items = [it for it in data if it["fixture"]["date"] >= cutoff.isoformat()]

    fixtures = agreements = splits = 0
    by_date: dict[str, list[dict]] = {}
    league_counts: dict[str, int] = {}
    when_counts: dict[str, int] = {"finished": 0, "today": 0, "tomorrow": 0, "later": 0}

    for item in items:
        fx = item["fixture"]
        fixtures += 1
        league = _league_label(fx["league"])
        item["_league"] = league
        by_date.setdefault(fx["date"], []).append(item)
        league_counts[league] = league_counts.get(league, 0) + 1
        when_counts[_when(fx["date"])] += 1

        for market in MARKETS:
            present = [s for s in item["sites"] if item["sites"][s].get(market)]
            if len(present) < 2:
                continue
            votes = {
                r["pick_norm"]
                for s in present
                for r in item["sites"][s][market]
                if r.get("pick_norm")
            }
            if len(votes) == 1:
                agreements += 1
            elif len(votes) > 1:
                splits += 1

    sections = []
    index = 0
    for date_iso in sorted(by_date):
        day_items = sorted(
            by_date[date_iso],
            key=lambda it: (
                it["_league"],
                _kickoff_time(it["fixture"]["kickoff"]),
                it["fixture"]["home_id"],
            ),
        )
        day_leagues = {it["_league"] for it in day_items}
        day_agree = day_split = 0
        for it in day_items:
            for market in MARKETS:
                present = [s for s in it["sites"] if it["sites"][s].get(market)]
                if len(present) < 2:
                    continue
                votes = {
                    r["pick_norm"]
                    for s in present
                    for r in it["sites"][s][market]
                    if r.get("pick_norm")
                }
                if len(votes) == 1:
                    day_agree += 1
                elif len(votes) > 1:
                    day_split += 1

        when = _when(date_iso)
        d = dt.date.fromisoformat(date_iso)
        tag_html = ""
        if when in ("today", "tomorrow"):
            tag_html = f'<span class="dh-tag">{when.title()}</span>'
        elif when == "finished":
            tag_html = '<span class="dh-tag finished">Finished</span>'

        cards = []
        last_league = None
        for it in day_items:
            league = it["_league"]
            if league != last_league:
                cards.append(f'<div class="lg-div">{_esc(league)}</div>')
                last_league = league
            fid = it["fixture"]["fixture_id"]
            result = attached.get(fid, [None])[0] if attached.get(fid) else None
            cards.append(
                _fixture_html(it, result=result, names=names, index=index, league=league)
            )
            index += 1

        sections.append(
            f'<section class="day" data-date="{_esc(date_iso)}">'
            f'<h2 class="day-head">{_esc(d.strftime("%a %d %b"))}{tag_html}'
            f'<span class="dh-count">{len(day_items)} fixtures &middot; {day_agree} agree'
            f' &middot; {day_split} split</span></h2>'
            + "".join(cards)
            + "</section>"
        )

    tabs = ['<button class="tab" type="button" data-when="all" aria-pressed="true">All '
            f"<b>{fixtures}</b></button>"]
    for key, label in (
        ("finished", "Finished"),
        ("today", "Today"),
        ("tomorrow", "Tomorrow"),
        ("later", "Later"),
    ):
        tabs.append(
            f'<button class="tab" type="button" data-when="{key}" aria-pressed="false">'
            f"{label} <b>{when_counts[key]}</b></button>"
        )

    chips = ['<button class="chip" type="button" data-league="" aria-pressed="true">All '
             f"<b>{fixtures}</b></button>"]
    for league in sorted(league_counts):
        chips.append(
            f'<button class="chip" type="button" data-league="{_esc(league)}" '
            f'aria-pressed="false">{_esc(league)} <b>{league_counts[league]}</b></button>'
        )

    dates = sorted(by_date)
    if dates:
        lo = dt.date.fromisoformat(dates[0]).strftime("%d %b")
        hi = dt.date.fromisoformat(dates[-1]).strftime("%d %b %Y")
        window = f"{lo} &ndash; {hi}" if dates[0] != dates[-1] else lo
    else:
        window = "empty window"
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sub = (
        f"Window: {window} &middot; last {days_back} day(s) plus upcoming"
        f" &middot; updated {now}"
    )

    return PAGE.substitute(
        sub=sub,
        kpis=_kpis_html(fixtures, agreements, splits, grade_result,
                         sum(1 for r in ev_rows if r["flag"] == "VALUE")),
        tabs="".join(tabs),
        chips="".join(chips),
        count=f"{fixtures} of {fixtures} fixtures",
        value=value_html,
        accuracy=_accuracy_html(grade_result),
        body="".join(sections),
        generated=now,
    )


def write_html(path: str | os.PathLike | None = None, days_back: int = DAYS_BACK_DEFAULT) -> Path:
    if path is None:
        path = CONSENSUS_DIR / "consensus.html"
    out = Path(path)
    out.write_text(build_html(days_back=days_back), encoding="utf-8")
    return out

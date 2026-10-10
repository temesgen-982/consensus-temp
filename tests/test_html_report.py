import datetime as dt
import re

from consensus.html_report import (
    _kickoff_time,
    _league_label,
    _odds_html,
    _parse_odds,
    _pretty,
    _when,
    build_html,
)


def test_kickoff_time_accepts_every_source_format():
    assert _kickoff_time("10/10/2026 16:30") == "16:30"
    assert _kickoff_time("17:15 - Sat 10 Oct") == "17:15"
    assert _kickoff_time("19:00") == "19:00"
    assert _kickoff_time("2026-10-11 13:30") == "13:30"
    assert _kickoff_time("") == "--:--"
    assert _kickoff_time("no time here") == "--:--"


def test_league_label_dedupes_laliga():
    assert _league_label("LaLiga") == "La Liga"
    assert _league_label("La Liga") == "La Liga"
    assert _league_label("Premier League") == "Premier League"
    assert _league_label("") == "Unknown"


def test_when_buckets():
    today = dt.date.today()
    assert _when(today.isoformat()) == "today"
    assert _when((today + dt.timedelta(days=1)).isoformat()) == "tomorrow"
    assert _when((today + dt.timedelta(days=5)).isoformat()) == "later"
    assert _when((today - dt.timedelta(days=1)).isoformat()) == "finished"


def test_parse_odds_only_trusts_per_pick_price_sites():
    assert _parse_odds("whoscored", "1.64") == 1.64
    assert _parse_odds("eaglepredict", "6.00") == 6.0
    assert _parse_odds("whoscored", "") is None
    assert _parse_odds("whoscored", "not a number") is None


def test_fixture_level_and_editorial_notes_are_not_odds():
    # forebet repeats one fixture-level average on every market of the fixture
    assert _parse_odds("forebet", "avg=2.87") is None
    # these quote a different bet than the row they sit on
    assert _parse_odds("sportsgambler", "Draw @ 4.5") is None
    assert _parse_odds("sportytrader", "BTTS @ 1.75") is None
    assert _parse_odds("flashscore", "A Brighton win seems priced up attractively.") is None


def test_odds_html_marks_none_of_them_as_best():
    assert 'class="odds best"' not in _odds_html("forebet", "avg=2.87", False)
    assert 'class="odds best"' not in _odds_html(
        "sportsgambler", "Coventry Asian Hcp +2.25 @ 1.90", False
    )
    assert 'class="avg"' in _odds_html("forebet", "avg=2.87", False)
    assert 'class="tip"' in _odds_html(
        "flashscore", "Backing a draw could be the most logical approach here.", False
    )
    assert 'class="odds best"' in _odds_html("whoscored", "2.40", True)


def test_odds_html_escapes_editorial_note():
    out = _odds_html("flashscore", "Back <script> " * 40, False)
    assert "<script>" not in out


def test_pretty_prefers_display_name_from_teams_csv():
    out = _pretty("bayern-munich", {"bayern-munich": "Bayern Munich"})
    assert out == "Bayern Munich"
    assert _pretty("unknown-slug", {}) == "Unknown Slug"


def test_build_html_reports_only_the_window():
    html = build_html(days_back=2)
    today = dt.date.today()
    dates = {d for d in re.findall(r'data-date="([\d-]+)"', html)}
    assert dates, "expected at least one day section"
    assert min(dates) >= (today - dt.timedelta(days=2)).isoformat()
    # upcoming fixtures beyond the window stay in
    assert 'id="empty"' in html


def test_every_fixture_table_has_matching_header_and_cell_counts():
    html = build_html(days_back=7)
    tables = re.findall(r"<table>(.*?)</table>", html, re.S)
    assert len(tables) > 10
    checked = 0
    for table in tables:
        head = re.search(r"<thead><tr>(.*?)</tr></thead>", table, re.S)
        n_th = len(re.findall(r"<th[ >]", head.group(1)))
        body = re.search(r"<tbody>(.*?)</tbody>", table, re.S).group(1)
        rows = re.findall(r"<tr>(.*?)</tr>", body, re.S)
        assert rows, "table with a header but no rows"
        for row in rows:
            assert n_th == len(re.findall(r"<td[ >]", row)), f"th={n_th} row={row[:120]}"
            checked += 1
    assert checked > 150


def test_result_column_only_appears_for_finished_fixtures():
    html = build_html(days_back=30)
    finished = re.findall(
        r'<article class="card"[^>]*data-when="finished".*?</article>', html, re.S
    )
    assert finished, "expected finished fixtures with days_back=30"
    assert 'class="score"' in html
    assert 'class="result"' in html

    upcoming = re.findall(
        r'<article class="card"[^>]*data-when="today".*?</article>', html, re.S
    )
    for card in upcoming:
        assert 'class="result"' not in card
        assert "<th>Result</th>" not in card


def test_cards_collapse_by_default_and_are_keyboard_operable():
    html = build_html(days_back=2)
    assert '<button class="card-head" type="button" aria-expanded="false"' in html
    assert html.count('aria-expanded="false"') == html.count('class="card-body"')
    assert 'id="fx-body-' in html
    # no leftover placeholder caret text
    assert "[toggle]" not in html


def test_site_badges_are_unique_and_styled():
    html = build_html(days_back=7)
    tags = re.findall(r'class="sres (?:hit|miss)" title="[^"]*: [^"]*">(\w+)</span>', html)
    assert tags, "expected graded site badges"
    assert set(tags) <= {"fore", "eagl", "whos", "fscr", "sgam", "strd"}
    css = html.split("</style>")[0]
    assert ".sres.hit" in css and ".sres.miss" in css


def test_search_index_includes_pretty_names_and_league():
    html = build_html(days_back=7)
    m = re.search(r'data-search="([^"]*)"', html)
    assert m and len(m.group(1)) > 10


def test_empty_market_rows_are_dropped():
    html = build_html(days_back=7)
    labels = set(re.findall(r'<td class="market">([^<]+)</td>', html))
    assert labels <= {"1X2", "Over/Under 2.5", "Both To Score", "Correct Score",
                      "Double Chance"}
    # a row is rendered only when at least one site covers that market, so no
    # row can be nothing but dashes
    for row in re.findall(r"<tr><td class=\"market\">.*?</tr>", html, re.S):
        cells = re.findall(r"<td class=\"pick-cell\">(.*?)</td>", row, re.S)
        assert cells and any('class="na"' not in c for c in cells), row[:160]


def test_cards_carry_the_attributes_the_filter_js_reads():
    """The toolbar only works if every card exposes these data hooks."""
    html = build_html(days_back=7)
    cards = re.findall(r'<article class="card"[^>]*>', html)
    assert len(cards) > 50
    for tag in cards:
        for attr in ("data-when", "data-league", "data-sites", "data-search"):
            assert f'{attr}="' in tag, f"missing {attr}: {tag[:160]}"
    whens = {re.search(r'data-when="([^"]*)"', t).group(1) for t in cards}
    assert whens <= {"finished", "today", "tomorrow", "later"}
    # hide-1-site filters on data-sites, so it must be a real number
    sites = {int(re.search(r'data-sites="(\d+)"', t).group(1)) for t in cards}
    assert min(sites) >= 1


def test_facet_buttons_expose_a_count_element():
    html = build_html(days_back=7)
    tabs = re.findall(r'<button class="tab"[^>]*>.*?</button>', html, re.S)
    chips = re.findall(r'<button class="chip"[^>]*>.*?</button>', html, re.S)
    assert len(tabs) == 5 and len(chips) >= 4
    for btn in tabs + chips:
        assert re.search(r"<b>\d+</b>", btn), f"no count in {btn[:120]}"
        assert "data-" in btn
        assert 'aria-pressed="' in btn


def test_recent_marks_wrap_instead_of_widening_the_page():
    """Adjacent nowrap spans gave the browser no break opportunity and pushed
    the document wider than the viewport."""
    css = build_html(days_back=7).split("</style>")[0]
    assert re.search(
        r"\.recent-row \.marks \{[^}]*flex-wrap: wrap", css
    ), ".marks must be a wrapping flex container"


def test_accuracy_tables_sit_in_a_scroll_wrapper():
    """table { min-width } must not apply outside a scrollable wrapper."""
    html = build_html(days_back=7)
    assert "<details class=\"panel\">" in html
    for tbl in re.findall(r'<table class="acc-table">.*?</table>', html, re.S):
        before = html[: html.index(tbl)]
        assert before.rsplit("<div", 1)[-1].startswith(' class="tbl-wrap"'), (
            "accuracy table is not inside .tbl-wrap"
        )

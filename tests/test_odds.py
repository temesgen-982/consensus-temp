from consensus.odds import (
    american_to_decimal,
    fraction_to_decimal,
    load_odds,
    match_fixture,
    parse_bet365,
    parse_draftkings,
    save_odds,
)


def test_american_to_decimal():
    assert american_to_decimal(115) == 2.15
    assert american_to_decimal(-165) == 100 / 165 + 1
    assert round(american_to_decimal(270), 3) == 3.7


def test_fraction_to_decimal():
    assert round(fraction_to_decimal("23/20"), 3) == 2.15
    assert fraction_to_decimal("4/6") == 4 / 6 + 1
    assert fraction_to_decimal("3.5") == 3.5


def test_parse_draftkings_full_price_set():
    item = {
        "provider": {"name": "DraftKings"},
        "overUnder": 2.5,
        "overOdds": -165.0,
        "underOdds": 130.0,
        "homeTeamOdds": {
            "current": {"moneyLine": {"decimal": 3.25}},
            "open": {"moneyLine": {"decimal": 2.75}},
        },
        "awayTeamOdds": {"current": {"moneyLine": {"decimal": 2.15}}},
        "drawOdds": {"moneyLine": 270.0},
    }
    rows = parse_draftkings(item)
    by = {(r["market"], r["outcome"]): r for r in rows}
    assert by[("1x2", "1")]["odds"] == "3.250"
    assert by[("1x2", "1")]["opened"] == "2.750"
    assert by[("1x2", "X")]["odds"] == "3.700"
    assert by[("1x2", "2")]["odds"] == "2.150"
    assert by[("over_under", "Over")]["line"] == "2.5"
    assert float(by[("over_under", "Over")]["odds"]) == round(100 / 165 + 1, 3)
    assert float(by[("over_under", "Under")]["odds"]) == 2.3


def test_parse_bet365_moneyline_and_double_chance():
    item = {
        "provider": {"name": "Bet 365"},
        "bettingOdds": {"teamOdds": {
            "preMatchFullTimeResultHome": {"value": "23/10"},
            "preMatchFullTimeResultDraw": {"value": "13/5"},
            "preMatchFullTimeResultAway": {"value": "23/20"},
            "preMatchDoubleChanceHomeOrDraw": {"value": "4/6"},
            "preMatchDoubleChanceDrawOrAway": {"value": "1/3"},
            "preMatchDoubleChanceHomeOrAway": {"value": "2/7"},
        }},
    }
    rows = parse_bet365(item)
    by = {(r["market"], r["outcome"]): r for r in rows}
    assert float(by[("1x2", "1")]["odds"]) == 3.3
    assert float(by[("1x2", "X")]["odds"]) == 3.6
    assert float(by[("1x2", "2")]["odds"]) == 2.15
    assert float(by[("double_chance", "1X")]["odds"]) == round(4 / 6 + 1, 3)
    assert float(by[("double_chance", "X2")]["odds"]) == round(1 / 3 + 1, 3)
    assert float(by[("double_chance", "12")]["odds"]) == round(2 / 7 + 1, 3)


def test_parse_unknown_provider_is_empty():
    from consensus.odds import parse_provider
    assert parse_provider({"provider": {"name": "Live Odds"}}) == []
    assert parse_provider({"provider": {"name": "DraftKings"}}) == []


def test_match_fixture_exact_and_offset_date():
    fixtures = {"2026-10-11|arsenal|vs|leeds-united", "2026-10-11|hull|vs|everton"}
    assert match_fixture("Arsenal", "Leeds United", "2026-10-11", fixtures, {}) == \
        "2026-10-11|arsenal|vs|leeds-united"
    # UTC date one day off (late kickoff) still matches the canonical date
    assert match_fixture("Arsenal", "Leeds United", "2026-10-12", fixtures, {}) == \
        "2026-10-11|arsenal|vs|leeds-united"
    # ESPN's fuller name needs an alias to reach the canonical short id
    aliases = {("espn", "Hull City"): "hull"}
    assert match_fixture("Hull City", "Everton", "2026-10-11", fixtures, aliases) == \
        "2026-10-11|hull|vs|everton"


def test_match_fixture_uses_espn_aliases():
    fixtures = {"2026-10-11|vit-ria|vs|benfica"}
    aliases = {("espn", "Vitoria Guimaraes"): "vit-ria"}
    assert match_fixture("Vitoria Guimaraes", "Benfica", "2026-10-11",
                         fixtures, aliases) == "2026-10-11|vit-ria|vs|benfica"


def test_match_fixture_no_match():
    assert match_fixture("Wolves", "Brentford", "2026-10-11", set(), {}) is None


def _row(fid: str, scraped: str, provider="DraftKings") -> dict:
    return {
        "fixture_id": fid, "date": "2026-10-11", "home": "Hull", "away": "Everton",
        "league": "eng.1", "provider": provider, "market": "1x2", "outcome": "X",
        "odds": "3.700", "line": "", "opened": "", "scraped_at": scraped,
    }


def test_save_and_load_odds_snapshots(tmp_path):
    path = tmp_path / "odds.csv"
    save_odds([_row("f1", "2026-10-11T10:00:00Z")], path=path)
    save_odds([_row("f2", "2026-10-12T10:00:00Z")], path=path)
    # same-day re-run replaces that day's rows, older days survive
    save_odds([_row("f3", "2026-10-12T18:00:00Z")], path=path)

    assert {r["fixture_id"] for r in load_odds(path=path)} == {"f1", "f3"}
    assert [r["fixture_id"] for r in load_odds(date="2026-10-11", path=path)] == ["f1"]
    assert len(load_odds(date="2026-10-12", path=path)) == 1


def test_load_odds_missing_file(tmp_path):
    assert load_odds(path=tmp_path / "nope.csv") == []

import pytest

from consensus import bets


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(bets, "BETS_PATH", tmp_path / "bets.csv")
    monkeypatch.setattr(bets, "LEGS_PATH", tmp_path / "bet_legs.csv")
    return tmp_path


def test_parse_conditions_tokens():
    assert bets.parse_conditions("1") == [("1x2", "1")]
    assert bets.parse_conditions("1X+H0.5") == [("dc", "1X"), ("team", "H", 0.5)]
    assert bets.parse_conditions("BTTS+O2.5") == [("btts", "Yes"), ("ou", "Over", 2.5)]
    assert bets.parse_conditions("U3.5") == [("ou", "Under", 3.5)]
    assert bets.parse_conditions("nBTTS") == [("btts", "No")]
    assert bets.parse_conditions("") == []


def test_parse_conditions_rejects_junk():
    with pytest.raises(ValueError):
        bets.parse_conditions("win")


def test_eval_condition_all_kinds():
    assert bets.eval_condition(("1x2", "1"), 2, 1) is True
    assert bets.eval_condition(("1x2", "X"), 2, 1) is False
    assert bets.eval_condition(("dc", "1X"), 1, 1) is True
    assert bets.eval_condition(("ou", "Over", 2.5), 2, 1) is True
    assert bets.eval_condition(("ou", "Under", 3.5), 3, 2) is False
    assert bets.eval_condition(("ou", "Over", 3.0), 2, 1) is None
    assert bets.eval_condition(("btts", "Yes"), 2, 1) is True
    assert bets.eval_condition(("btts", "No"), 2, 0) is True
    assert bets.eval_condition(("team", "H", 0.5), 1, 0) is True
    assert bets.eval_condition(("team", "A", 0.5), 1, 0) is False


def test_parse_leg_forms():
    assert bets.parse_leg("2026-10-11|fc-koln|vs|b-monchengladbach|1X+H0.5") == {
        "fixture_id": "2026-10-11|fc-koln|vs|b-monchengladbach",
        "leg": "2026-10-11|fc-koln|vs|b-monchengladbach|1X+H0.5",
        "conditions": "1X+H0.5",
    }
    assert bets.parse_leg("2026-10-11|fc-koln|b-monchengladbach")["fixture_id"] == \
        "2026-10-11|fc-koln|vs|b-monchengladbach"
    assert bets.parse_leg("2026-10-11|fc-koln|vs|b-monchengladbach")["conditions"] == ""
    assert bets.parse_leg("my own read")["fixture_id"] == ""


def test_evaluate_leg():
    attached = {
        "2026-10-11|como|vs|roma": [{"home_goals": "0", "away_goals": "0", "date": "2026-10-11"}],
        "2026-10-11|fc-koln|vs|b-monchengladbach": [
            {"home_goals": "2", "away_goals": "1", "date": "2026-10-11"}
        ],
    }
    assert bets.evaluate_leg("2026-10-11|como|vs|roma", "BTTS+O2.5", attached) == ("lost", "0-0")
    assert bets.evaluate_leg(
        "2026-10-11|fc-koln|vs|b-monchengladbach", "1X+H0.5", attached
    ) == ("won", "2-1")
    assert bets.evaluate_leg("2026-10-11|missing|vs|team", "1", attached) == ("pending", "")
    assert bets.evaluate_leg("2026-10-11|como|vs|roma", "", attached) == ("pending", "0-0")


def test_add_and_settle_parlay_lost(store):
    attached = {
        "2026-10-11|como|vs|roma": [{"home_goals": "0", "away_goals": "0", "date": "2026-10-11"}],
        "2026-10-11|freiburg|vs|schalke-04": [
            {"home_goals": "2", "away_goals": "1", "date": "2026-10-11"}
        ],
    }
    bet = bets.add_bet(50, 4.986, [
        "2026-10-11|como|vs|roma|BTTS+O2.5",
        "2026-10-11|freiburg|vs|schalke-04|1",
    ], placed_date="2026-10-11")
    assert bet["kind"] == "parlay"
    log = bets.settle_bets(attached=attached)
    assert any("LOST" in line for line in log)
    saved = bets.load_bets()[0]
    assert saved["status"] == "lost"
    assert saved["payout"] == "0.00"


def test_settle_win_payout_and_summary(store):
    attached = {
        "2026-10-11|freiburg|vs|schalke-04": [
            {"home_goals": "2", "away_goals": "1", "date": "2026-10-11"}
        ],
        "2026-10-11|racing-santander|vs|valencia": [
            {"home_goals": "2", "away_goals": "2", "date": "2026-10-11"}
        ],
    }
    bets.add_bet(50, 4.986, [
        "2026-10-11|freiburg|vs|schalke-04|1",
        "2026-10-11|racing-santander|vs|valencia|1X+H0.5",
    ], placed_date="2026-10-11")
    bets.settle_bets(attached=attached)
    saved = bets.load_bets()[0]
    assert saved["status"] == "won"
    assert saved["payout"] == "249.30"
    stats = bets.summarize(bets.load_bets())
    assert stats["returned"] == 249.30
    assert abs(stats["net"] - 199.30) < 1e-9


def test_pending_until_result(store):
    bets.add_bet(10, 2.0, ["2026-10-12|hull|vs|everton|X"], placed_date="2026-10-12")
    log = bets.settle_bets(attached={})
    assert any("pending" in line for line in log)
    assert bets.load_bets()[0]["status"] == "pending"


def test_manual_settle(store):
    bet = bets.add_bet(20, 3.0, ["my own read"], placed_date="2026-10-12")
    log = bets.settle_bets(manual_id=bet["bet_id"], manual_result="won", attached={})
    assert any("manually won" in line for line in log)
    saved = bets.load_bets()[0]
    assert saved["status"] == "won"
    assert saved["payout"] == "60.00"

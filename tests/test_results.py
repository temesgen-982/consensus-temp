from consensus.results import attach_results, evaluate_pick, grade


def test_evaluate_pick_1x2():
    assert evaluate_pick("1x2", "1", 3, 0) is True
    assert evaluate_pick("1x2", "X", 1, 1) is True
    assert evaluate_pick("1x2", "2", 1, 2) is True
    assert evaluate_pick("1x2", "2", 3, 0) is False


def test_evaluate_pick_over_under():
    assert evaluate_pick("over_under", "Over", 2, 1) is True
    assert evaluate_pick("over_under", "Under", 2, 0) is True
    assert evaluate_pick("over_under", "Under", 2, 1) is False


def test_evaluate_pick_btts():
    assert evaluate_pick("btts", "Yes", 1, 1) is True
    assert evaluate_pick("btts", "No", 3, 0) is True
    assert evaluate_pick("btts", "No", 1, 1) is False


def test_evaluate_pick_correct_score():
    assert evaluate_pick("correct_score", "2 - 1", 2, 1) is True
    assert evaluate_pick("correct_score", "1 - 1", 2, 1) is False


def test_evaluate_pick_blank_or_bad():
    assert evaluate_pick("1x2", "", 1, 0) is None
    assert evaluate_pick("1x2", "1", "-", "-") is None


def test_attach_results():
    results = [
        {
            "site": "whoscored", "source_id": "1", "date": "2026-08-15",
            "home_team": "Deportivo Alaves", "away_team": "Getafe",
            "home_goals": "3", "away_goals": "0",
        },
    ]
    attached = attach_results(results)
    assert "2026-08-15|deportivo-alav-s|vs|getafe" in attached


def test_render_grade_includes_consensus():
    from consensus.results import render_grade

    text = render_grade({
        "stats": {("forebet", "1x2"): [True, False]},
        "consensus": {"agree": {"1x2": [True]}, "majority": {"1x2": [False]}},
        "split": {},
        "per_fixture": {},
    })
    assert "Consensus accuracy" in text
    assert "agree" in text.lower()


def test_grade_no_results():
    out = grade([])
    assert out["stats"] == {}
from consensus.markets import derive_from_score


def test_home_win_clean_sheet():
    assert derive_from_score(2, 0) == {
        "1x2": "1", "btts": "No", "over_under": "Under",
    }


def test_away_win_over():
    assert derive_from_score(1, 2) == {
        "1x2": "2", "btts": "Yes", "over_under": "Over",
    }


def test_draws():
    assert derive_from_score(0, 0)["1x2"] == "X"
    assert derive_from_score(0, 0)["btts"] == "No"
    assert derive_from_score(0, 0)["over_under"] == "Under"
    assert derive_from_score(1, 1)["1x2"] == "X"
    assert derive_from_score(3, 3)["over_under"] == "Over"


def test_two_point_five_line_boundary():
    # exactly 2 goals -> Under; 3 goals -> Over
    assert derive_from_score(2, 0)["over_under"] == "Under"
    assert derive_from_score(1, 1)["over_under"] == "Under"
    assert derive_from_score(2, 1)["over_under"] == "Over"

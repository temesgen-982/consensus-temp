from consensus.config import is_top_league
from consensus.normalize import normalize_pick


def test_is_top_league_forebet_names():
    assert is_top_league("forebet", "Premier League")
    assert is_top_league("forebet", "La Liga")
    assert is_top_league("forebet", "Bundesliga")
    assert is_top_league("forebet", "Serie A")
    assert is_top_league("forebet", "Ligue 1")
    assert is_top_league("forebet", "Eredivisie")
    assert is_top_league("forebet", "Liga Portugal")


def test_is_top_league_eagle_names():
    assert is_top_league("eaglepredict", "England Premier League")
    assert is_top_league("eaglepredict", "La Liga")
    assert is_top_league("eaglepredict", "Germany Bundesliga")
    assert is_top_league("eaglepredict", "Italy Serie A")
    assert is_top_league("eaglepredict", "France Ligue 1")
    assert is_top_league("eaglepredict", "Eredivisie")
    assert is_top_league("eaglepredict", "Primeira Liga")


def test_is_top_league_rejects_similar():
    assert not is_top_league("eaglepredict", "England Championship")
    assert not is_top_league("eaglepredict", "England Community Shield")
    assert not is_top_league("eaglepredict", "Germany 2. Bundesliga")
    assert not is_top_league("eaglepredict", "Germany 3. Liga")
    assert not is_top_league("eaglepredict", "Italy Coppa Italia")
    assert not is_top_league("eaglepredict", "France Trophee des Champions - Super Cup")
    assert not is_top_league("eaglepredict", "Portugal LigaPro")
    assert not is_top_league("eaglepredict", "Netherlands Eerste Divisie")
    assert not is_top_league("forebet", "English Championship")


def test_normalize_pick_forebet_1x2():
    assert normalize_pick("forebet", "1x2", "1", "Arsenal", "Chelsea") == "1"
    assert normalize_pick("forebet", "1x2", "X", "Arsenal", "Chelsea") == "X"
    assert normalize_pick("forebet", "1x2", "2", "Arsenal", "Chelsea") == "2"


def test_normalize_pick_eagle_1x2():
    assert normalize_pick("eaglepredict", "1x2", "Arsenal Win", "Arsenal", "Chelsea") == "1"
    assert normalize_pick("eaglepredict", "1x2", "Chelsea Win", "Arsenal", "Chelsea") == "2"
    assert normalize_pick("eaglepredict", "1x2", "Draw", "Arsenal", "Chelsea") == "X"


def test_normalize_pick_over_under():
    assert normalize_pick("eaglepredict", "over_under", "Over  2.5 Goals", "", "") == "Over"
    assert normalize_pick("eaglepredict", "over_under", "Under 2.5 Goals", "", "") == "Under"


def test_normalize_pick_btts():
    assert normalize_pick("eaglepredict", "btts", "BTTS - Yes", "", "") == "Yes"
    assert normalize_pick("eaglepredict", "btts", "BTTS - No", "", "") == "No"
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


def test_evaluate_pick_double_chance():
    assert evaluate_pick("double_chance", "1X", 3, 0) is True
    assert evaluate_pick("double_chance", "1X", 1, 1) is True
    assert evaluate_pick("double_chance", "1X", 0, 2) is False
    assert evaluate_pick("double_chance", "X2", 1, 2) is True
    assert evaluate_pick("double_chance", "12", 3, 0) is True
    assert evaluate_pick("double_chance", "12", 1, 1) is False


def test_evaluate_pick_blank_or_bad():
    assert evaluate_pick("1x2", "", 1, 0) is None
    assert evaluate_pick("1x2", "1", "-", "-") is None


def test_attach_results():
    results = [
        {
            "site": "flashscore", "source_id": "1", "date": "2026-08-15",
            "home_team": "Dortmund", "away_team": "Mainz",
            "home_goals": "3", "away_goals": "0",
        },
    ]
    attached = attach_results(results)
    assert "2026-08-15|borussia-dortmund|vs|mainz-05" in attached


def test_parse_finished_top_leagues_only():
    from consensus.results import parse_finished

    html = """<div id="score-data">
<h4>FRANCE: Ligue 1 <a href="/standings/x/y/" class="web-link-internal">Standings</a></h4>
<span>20:45</span>Lens<img src="blank.gif" alt="" class="rcard-1"> - Lyon <a href="/match/MFDuQNS6/?s=3&d=-1" class="fin">2-1</a><br />
<h4>GERMANY: Bundesliga <a href="/standings/x/y/" class="web-link-internal">Standings</a></h4>
<span>20:30</span>Dortmund - Werder Bremen <a href="/match/plkwWY3D/?s=3&d=-1" class="fin">2-2</a><br />
<h4>ALGERIA: Ligue 1 <a href="/standings/x/y/" class="web-link-internal">Standings</a></h4>
<span>18:45</span>Kabylie - ASO Chlef <a href="/match/0tm9Ggl3/?s=3&d=-1" class="fin">1-0</a><br />
<h4>AFRICA: Something</h4>
<span>16:00</span>Congo W - Morocco W WO <a href="/match/G2S5UTFi/?s=3&d=-1" class="fin">&nbsp;-&nbsp;</a><br />
</div>"""
    rows = parse_finished(html, "2026-10-09")
    assert len(rows) == 2
    assert rows[0]["home_team"] == "Lens"
    assert rows[0]["away_team"] == "Lyon"
    assert rows[0]["home_goals"] == "2"
    assert rows[0]["away_goals"] == "1"
    assert rows[0]["league"] == "Ligue 1"
    assert rows[0]["source_id"] == "MFDuQNS6"
    assert rows[1]["home_team"] == "Dortmund"
    assert rows[1]["league"] == "Bundesliga"


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
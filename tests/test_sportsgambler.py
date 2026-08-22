from consensus.scrapers.sportsgambler import parse_league, parse_match

LEAGUE_HTML = """
<div class="betlist-container grid">
    <div class="betlist_con span_6">
        <a href="/betting-tips/football/hull-vs-manchester-united-prediction-lineups-odds-2026-08-22/" class="betlist-item">
            <span class="betlist-date">
                <span class="timedate"><i class="sporticon-football"></i> 14:30 - Sat 22 Aug</span>
                <span class="betlist-league">Premier League <img src="flag.png" alt="England Flag"></span>
            </span>
            <span class="betlist-teams">
                <span><img src="a.png" alt="Hull logo">Hull</span>
                <span><img src="b.png" alt="Manchester United logo">Manchester United</span>
            </span>
            <span class="betlist-btn">Predictions</span>
        </a>
    </div>
    <div class="betlist_con span_6">
        <a href="/betting-tips/football/old-game-prediction-lineups-odds-2026-01-01/" class="betlist-item">
            <span class="betlist-date"><span class="timedate">12:00 - Thu 1 Jan</span></span>
            <span class="betlist-teams"><span>Alpha</span><span>Beta</span></span>
        </a>
    </div>
</div>
"""

MATCH_HTML = """
<html><body>
<div class="fs-500 fw-700">Can Tigers Cover the Line?</div>
<h2 id="match-prediction">Main Match Prediction</h2>
<a href="/betting-sites/go/stake/sport?utm_campaign=sgc" rel="nofollow" class="tpbot_tip">
    <span>Hull Asian Hcp +1.5 @ 1.82</span>
</a>
<div id="correct-score-prediction"></div>
<div class="correct-score">
    <div class="correct-score-header flex">
        <div class="cs-board flex align-center">
            <span class="cs-teams inline-flex align-right justify-end">
                <span>Hull</span><img src="a.png" alt="Hull logo">
            </span>
            <span class="cs-score inline-flex align-center justify-center">
                <span class="cs-score-box inline-flex">1</span>
                <span class="cs-score-box split">-</span>
                <span class="cs-score-box inline-flex">2</span>
            </span>
            <span class="cs-teams away inline-flex justify-start">
                <img src="b.png" alt="Man United logo"><span>Man United</span>
            </span>
        </div>
    </div>
</div>
</body></html>
"""


def test_parse_league():
    out = parse_league(LEAGUE_HTML)
    assert len(out) == 2
    fx = out[0]
    assert fx["source_id"] == "hull-vs-manchester-united"
    assert fx["date"] == "2026-08-22"
    assert fx["home_team"] == "Hull"
    assert fx["away_team"] == "Manchester United"
    assert "14:30" in fx["kickoff"]


def test_parse_match():
    pred = parse_match(MATCH_HTML)
    assert pred["home_goals"] == "1"
    assert pred["away_goals"] == "2"
    assert pred["main_tip"] == "Hull Asian Hcp +1.5 @ 1.82"


def test_parse_match_missing_scoreboard():
    pred = parse_match("<html><body><p>no board yet</p></body></html>")
    assert pred["home_goals"] == ""
    assert pred["away_goals"] == ""

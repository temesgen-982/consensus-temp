from consensus.scrapers.flashscore import (
    extract_prediction,
    match_url,
    parse_fixtures_feed,
    parse_match,
)

FEED = (
    "SA÷1¬~ZA÷SPAIN: LaLiga¬ZEE÷QVmLl54o¬ZB÷176¬ZY÷Spain¬ZC÷dWdJXP6U¬ZD÷t¬ZE÷QeI1Oeyi"
    "¬~AA÷4ve9lHOQ¬AD÷1786892400¬AB÷1¬AC÷1¬CX÷Racing Santander¬ER÷Round 1¬AF÷Villarreal"
    "¬PX÷nVpEwOrl¬PY÷lUatW5jE¬WU÷racing-santander¬WV÷villarreal¬"
    "~AA÷dEi1jwfE¬AD÷1786899600¬CX÷Espanyol¬AF÷Levante¬PX÷QFfPdh1J¬PY÷G8FL0ShI¬WU÷espanyol¬WV÷levante¬"
)

MATCH_HTML = """
<script>
window.environment = {
  "event_id_c": "4ve9lHOQ",
  "eventStageStartTime": 1786892400,
  "header": {"tournament": {"tournament": "LaLiga - Round 1"}},
  "participantsData": {
    "home": [{"name": "Racing Santander", "id": "nVpEwOrl"}],
    "away": [{"name": "Villarreal", "id": "lUatW5jE"}]
  },
  "eventPreview": {"contentParsed": "[p][h2]Betting Analysis[\\/h2][p]backing [b][a href=\\"\\/match\\/odds\\/\\"]Villarreal to win[\\/a][\\/b] could land perfectly.[\\/p][p][i]Author: X[\\/i][\\/p]"}
};
</script>
"""


def test_parse_fixtures_feed():
    out = parse_fixtures_feed(FEED)
    assert len(out) == 2
    m = out[0]
    assert m["AA"] == "4ve9lHOQ"
    assert m["CX"] == "Racing Santander"
    assert m["AF"] == "Villarreal"
    assert m["WU"] == "racing-santander"
    assert m["WV"] == "villarreal"


def test_match_url():
    m = {"WU": "racing-santander", "PX": "nVpEwOrl", "WV": "villarreal", "PY": "lUatW5jE"}
    assert match_url(m) == (
        "https://www.flashscore.com/match/football/"
        "racing-santander-nVpEwOrl/villarreal-lUatW5jE/"
    )


def test_parse_match():
    m = parse_match(MATCH_HTML)
    assert m["source_id"] == "4ve9lHOQ"
    assert m["league"] == "LaLiga"
    assert m["date"] == "2026-08-16"
    assert m["home_team"] == "Racing Santander"
    assert m["away_team"] == "Villarreal"
    assert "Betting Analysis" in m["preview"]


def test_extract_prediction_home_win():
    content = "[h2]Betting Analysis[/h2][p]backing [b]Racing Santander to win[/b] is a solid shout.[/p]"
    pick, sentence = extract_prediction(content, "Racing Santander", "Villarreal")
    assert pick == "1"
    assert "to win" in sentence


def test_extract_prediction_away_win():
    content = "[h2]Betting Analysis[/h2][p]backing [b]Villarreal to win[/b] could land perfectly.[/p]"
    pick, sentence = extract_prediction(content, "Racing Santander", "Villarreal")
    assert pick == "2"


def test_extract_prediction_draw():
    content = "[h2]Betting Analysis[/h2][p]a draw looks likely here.[/p]"
    pick, _ = extract_prediction(content, "Racing Santander", "Villarreal")
    assert pick == "X"


def test_extract_prediction_backing_draw():
    content = ("[h2]Betting Analysis[/h2][p]backing the draw in what could be "
               "a tentative season opener could prove shrewd.[/p]")
    pick, _ = extract_prediction(content, "Espanyol", "Levante")
    assert pick == "X"


def test_extract_prediction_over_goals_ignored():
    content = "[h2]Betting Analysis[/h2][p]backing over 3.5 goals could pay off.[/p]"
    pick, _ = extract_prediction(content, "Dep. A Coruna", "Elche")
    assert pick == ""


def test_extract_prediction_unknown():
    content = "[h2]Betting Analysis[/h2][p]both teams are evenly matched.[/p]"
    pick, _ = extract_prediction(content, "Racing Santander", "Villarreal")
    assert pick == ""


def test_extract_prediction_case_insensitive():
    content = "[h2]Betting Analysis[/h2][p]Backing Villarreal to win looks good.[/p]"
    pick, _ = extract_prediction(content, "Racing Santander", "Villarreal")
    assert pick == "2"


def test_extract_prediction_for_the_win():
    content = "[h2]Betting Analysis[/h2][p]We like Espanyol for the win here.[/p]"
    pick, _ = extract_prediction(content, "Espanyol", "Levante")
    assert pick == "1"


def test_extract_prediction_team_mention_fallback():
    content = "[h2]Betting Analysis[/h2][p]Our tip is Villarreal in this fixture.[/p]"
    pick, _ = extract_prediction(content, "Racing Santander", "Villarreal")
    assert pick == "2"


def test_extract_prediction_stalemate_draw():
    content = "[h2]Betting Analysis[/h2][p]A stalemate looks the most likely outcome.[/p]"
    pick, _ = extract_prediction(content, "Espanyol", "Levante")
    assert pick == "X"
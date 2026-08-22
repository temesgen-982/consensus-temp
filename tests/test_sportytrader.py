from consensus.scrapers.sportytrader import parse_card, parse_pick

CARD_HTML = """
<div data-controller="navigation"
     data-navigation-url-value="/en/betting-tips/everton-crystal-palace-367097/"
     class="card h-full border-gray-200 border-2 card-ribbon">
    <div class="card__container bg-white text-primary-blue">
        <div class="pt-4 px-3">
            <div>
                <div class="grid grid-cols-7 items-center text-sm">
                    <div class="col-span-7 flex flex-col justify-center items-center">
                        <p class="dark:text-white font-bold">22 Aug 2026, 17:00</p>
                        <p class="dark:text-white text-sm">England
                            - Premier League</p>
                    </div>
                </div>
                <a href="/en/betting-tips/everton-crystal-palace-367097/">
                    <span class="font-semibold text-center flex pr-1 break-words">Everton</span>
                    <span class="font-semibold text-center flex pl-1 break-words">Crystal Palace</span>
                </a>
                <div class="bg-gray-100 my-2 p-2 rounded-md ">
                    <div class="grid grid-cols-12 space-x-2">
                        <div class=" col-span-9 text-left   leading-5">
                            <p class="  text-left   font-semibold ">BTTS</p>
                        </div>
                        <div class=" col-span-3   flex flex-col justify-center items-center bg-white p-0.5 rounded-md ">
                            <span class="text-sm">Odds</span>
                            <span class="font-bold tabular-nums tracking-tight">1.75</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""


def _card():
    from bs4 import BeautifulSoup

    return BeautifulSoup(CARD_HTML, "html.parser").select_one("div.card")


def test_parse_card():
    p = parse_card(_card())
    assert p["source_id"] == "everton-crystal-palace-367097"
    assert p["league"] == "Premier League"
    assert p["date"] == "2026-08-22"
    assert p["kickoff"] == "17:00"
    assert p["home_team"] == "Everton"
    assert p["away_team"] == "Crystal Palace"
    assert p["tip"] == "BTTS"
    assert p["odds"] == "1.75"


def test_parse_pick_simple():
    assert parse_pick("BTTS", "Everton", "Crystal Palace") == [("btts", "Yes")]
    assert parse_pick("BTTS: No", "Everton", "Crystal Palace") == [("btts", "No")]
    assert parse_pick("Over 2.5 goals", "A", "B") == [("over_under", "Over")]
    assert parse_pick("Under 3.5 goals", "A", "B") == [("over_under", "Under")]
    assert parse_pick("Draw", "A", "B") == [("1x2", "X")]


def test_parse_pick_team_win():
    assert parse_pick("Southampton wins", "Southampton", "Stoke") == [("1x2", "1")]
    assert parse_pick("Cardiff wins", "Derby County", "Cardiff") == [("1x2", "2")]
    # containment tolerance: short nickname vs full team name
    assert parse_pick("Basel to win", "FC Zurich", "FC Basel 1893") == [("1x2", "2")]
    assert parse_pick("Leicester City wins and over 1.5 goals", "Leicester", "Burton Albion") == [
        ("1x2", "1"),
        ("over_under", "Over"),
    ]


def test_parse_pick_compounds_and_skips():
    assert parse_pick("Inter Milan to win and BTTS", "Inter Milan", "Monza") == [
        ("1x2", "1"),
        ("btts", "Yes"),
    ]
    assert parse_pick("Napoli to win & BTTS", "Genoa", "Napoli") == [
        ("1x2", "2"),
        ("btts", "Yes"),
    ]
    assert parse_pick("Draw & under 2.5 goals", "Blackburn", "Middlesbrough") == [
        ("1x2", "X"),
        ("over_under", "Under"),
    ]
    # unmappable tip types -> empty list
    assert parse_pick("Draw or Watford", "Wrexham", "Watford") == []
    assert parse_pick(
        "Half-time/Full-time: Manchester United/Manchester United", "Hull", "Manchester United"
    ) == []
    assert parse_pick("West Ham scores 2+ goals", "West Ham", "Charlton Athletic") == []
    assert parse_pick("Real Madrid wins to nil", "Real Madrid", "Espanyol") == []
    assert parse_pick(
        "Sporting Lisbon wins with\u00a0-1 handicap", "Sporting Lisbon", "Estoril"
    ) == []

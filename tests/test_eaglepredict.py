from consensus.scrapers.eaglepredict import map_pick, parse_league, parse_market

PAGE = """
<div>
  <div class="card">
    <a href="/predictions/league/england-premier-league/" class="mr-auto font-bold">
      <div class="flex items-center gap-2">England Premier League</div>
      <div class="flex items-center gap-2 mt-2 md:mt-3">Sun - 16 Aug 2026</div>
    </a>
  </div>
  <div class="flex flex-col gap-4">
    <div class="card bg-base-300 p-4">
      <a href="/predictions/match/arsenal-vs-chelsea-prediction-premier-league-15-08-2026/"></a>
      <div class="flex justify-between items-center md:hidden mb-2">
        <div class="flex items-center gap-2">16:00</div>
      </div>
      <div class="grid grid-cols-10 items-center gap-2" data-f-id="123456">
        <div class="flex items-center col-span-4 md:col-span-5 gap-2">
          <div class="ml-auto text-right">Arsenal</div>
        </div>
        <div class="text-center">V.S</div>
        <div class="flex items-center gap-2 col-span-4 md:col-span-5">
          <div class="">Chelsea</div>
        </div>
      </div>
      <div class="mt-4">
        <span class="btn-prediction-calendar">Arsenal Win</span>
        <div class="col-span-2 text-center"><a class="btn font-bold text-success">1.94</a></div>
      </div>
    </div>
  </div>
</div>
"""


def _league_page(pick: str, home: str = "Newcastle", away: str = "Bournemouth",
                 fid: str = "9999", header: str = "Premier League Sat - 05 Sep 2026",
                 kickoff: str = "14:30") -> str:
    return f"""
    <div>
      <div class="p-3 md:p-4 flex flex-row items-center gap-2 md:gap-3 bg-primary/30 cursor-pointer card">{header}</div>
      <div class="flex flex-col gap-4">
        <div class="card bg-base-300 p-4">
          <a href="/predictions/match/newcastle-united-vs-afc-bournemouth-prediction-premier-league-05-09-2026/"></a>
          <div class="flex justify-between items-center md:hidden mb-2">
            <div class="flex items-center gap-2">{kickoff}</div>
          </div>
          <div class="grid grid-cols-10 items-center gap-2" data-f-id="{fid}">
            <div class="flex items-center col-span-4 md:col-span-5 gap-2">
              <div class="ml-auto text-right">{home}</div>
            </div>
            <div class="text-center">V.S</div>
            <div class="flex items-center gap-2 col-span-4 md:col-span-5">
              <div class="">{away}</div>
            </div>
          </div>
          <div class="mt-4">
            <span class="btn-prediction-calendar">{pick}</span>
            <div class="col-span-2 text-center"><a class="btn font-bold text-success">1.50</a></div>
          </div>
        </div>
      </div>
    </div>
    """


def test_parse_market_card():
    rows = parse_market(PAGE)
    assert len(rows) == 1
    r = rows[0]
    assert r["league"] == "England Premier League"
    assert r["date"] == "2026-08-16"
    assert r["home_team"] == "Arsenal"
    assert r["away_team"] == "Chelsea"
    assert r["kickoff"] == "16:00"
    assert r["score"] == "V.S"
    assert r["pick"] == "Arsenal Win"
    assert r["odds"] == "1.94"
    assert r["source_id"] == "123456"
    assert "predictions/match/" in r["url"]


def test_parse_market_league_name_excludes_date():
    rows = parse_market(PAGE)
    assert rows[0]["league"] == "England Premier League"  # not "... Sun - 16 Aug 2026"


def test_parse_market_finished_match_score():
    page = PAGE.replace('<div class="text-center">V.S</div>',
                        '<div class="text-center"><span>1</span><span>-</span><span class="font-bold">2</span></div>')
    rows = parse_market(page)
    assert rows[0]["score"] == "1 - 2"
    assert rows[0]["away_team"] == "Chelsea"


def test_parse_league_section():
    rows = parse_league(_league_page("Under  3.5 Goals"))
    assert len(rows) == 1
    r = rows[0]
    assert r["league"] == "Premier League"  # date stripped from header
    assert r["date"] == "2026-09-05"
    assert r["home_team"] == "Newcastle"
    assert r["away_team"] == "Bournemouth"
    assert r["kickoff"] == "14:30"
    assert r["pick"] == "Under  3.5 Goals"
    assert r["odds"] == "1.50"


def test_parse_league_multiple_days():
    page = _league_page(
        "Double Chance: Newcastle or Draw", header="Premier League Sat - 05 Sep 2026"
    ) + _league_page(
        "Under  2.5 Goals", fid="7777", header="Premier League Sun - 06 Sep 2026"
    )
    rows = parse_league(page)
    assert [r["date"] for r in rows] == ["2026-09-05", "2026-09-06"]


def test_parse_league_ignores_bet_sections():
    page = _league_page("BTTS - Yes") + (
        '<div class="py-4 px-5 flex flex-row bg-primary/30 card">1xbet bonus</div>'
        '<div class="grid grid-cols-12 gap-4"></div>'
    )
    assert len(parse_league(page)) == 1


def test_map_pick_variants():
    assert map_pick({"pick": "Arsenal Win"}) == [("1x2", "Arsenal Win")]
    assert map_pick({"pick": "RB Leipzig Win"}) == [("1x2", "RB Leipzig Win")]
    assert map_pick({"pick": "Double Chance: Newcastle or Draw"}) == [("double_chance", "Double Chance: Newcastle or Draw")]
    assert map_pick({"pick": "Under  3.5 Goals"}) == [("over_under", "Under  3.5 Goals")]
    assert map_pick({"pick": "Over 2.5 Goals"}) == [("over_under", "Over 2.5 Goals")]
    assert map_pick({"pick": "BTTS - Yes"}) == [("btts", "BTTS - Yes")]
    assert map_pick({"pick": "BTTS - No"}) == [("btts", "BTTS - No")]
    assert map_pick({"pick": ""}) == []


def test_map_pick_unrecognized():
    assert map_pick({"pick": "Both teams to Score - No"}) == [("btts", "BTTS - No")]
    assert map_pick({"pick": "Corner Kick Magic"}) == []
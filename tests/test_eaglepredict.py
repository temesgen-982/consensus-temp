from consensus.scrapers.eaglepredict import parse_market

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
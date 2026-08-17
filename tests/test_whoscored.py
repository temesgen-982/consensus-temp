from consensus.scrapers.whoscored import fixtures_url, parse_fixtures, parse_prediction, parse_scores

LEAGUE_HTML = """
<a class="x" href="/regions/206/tournaments/4/seasons/11213/stages/25662/fixtures/spain-laliga-2026-2027">Fixtures</a>
"""

FIXTURES_HTML = """
<div>
  <div class="Accordion-module_header__abc"><div><span>Sunday, Aug 16 2026</span></div></div>
  <div class="Accordion-module_childrenOpened__def">
    <div>
      <div class="Match-module_match__ghi">
        <div class="Match-module_row__zwBOn">
          <div class="Match-module_left__hYvbD"><span class="Match-module_startTime__c49c8">16:00</span></div>
          <div class="Match-module_teams__sGVeq">
            <div class="Match-module_teamName__GoJbS">
              <a class="Match-module_teamNameText__Dqv-G">Racing Santander</a>
            </div>
            <div class="Match-module_teamName__GoJbS">
              <a class="Match-module_teamNameText__Dqv-G">Villarreal</a>
            </div>
          </div>
          <div class="Match-module_right__o-ux-">
            <a id="scoresBtn-1993903"></a>
            <a id="previewBtn-1993903" href="/matches/1993903/preview/spain-laliga-2026-2027-racing-santander-villarreal"></a>
          </div>
        </div>
      </div>
      <div class="Match-module_match__ghi">
        <div class="Match-module_row__zwBOn">
          <div class="Match-module_left__hYvbD"><span class="Match-module_startTime__c49c8">20:00</span></div>
          <div class="Match-module_teams__sGVeq">
            <div class="Match-module_teamName__GoJbS"><a class="Match-module_teamNameText__Dqv-G">Sevilla</a></div>
            <div class="Match-module_teamName__GoJbS"><a class="Match-module_teamNameText__Dqv-G">Rayo Vallecano</a></div>
          </div>
          <div class="Match-module_right__o-ux-"><a id="scoresBtn-1993905"></a></div>
        </div>
      </div>
    </div>
  </div>
</div>
"""

PREVIEW_HTML = """
<div id="preview-prediction" class="rc-b rc-r">
  <div class="home"><span class="predicted-score">2</span><div class="team-name"><span>Racing Santander</span></div></div>
  <div class="away"><span class="predicted-score">0</span><div class="team-name"><span>Villarreal</span></div></div>
</div>
<script type="application/json" data-hypernova-key="matchodds"><!--{"bets":[
  {"betName":"Home win","offers":[{"oddsDecimal":"3.4","bettingProvider":"B3"}]},
  {"betName":"Under 2.5 goals","offers":[{"oddsDecimal":"2.08","bettingProvider":"B3"}]},
  {"betName":"2-0","offers":[{"oddsDecimal":"15","bettingProvider":"B3"}]}
],"bookmakers":[]}--></script>
"""

SCORES_HTML = """
<div>
  <div class="Accordion-module_header__abc"><div><span>Saturday, Aug 15 2026</span></div></div>
  <div class="Accordion-module_childrenOpened__def">
    <div>
      <div class="Match-module_match__ghi">
        <div class="Match-module_row__zwBOn">
          <div class="Match-module_left__hYvbD">
            <span class="Match-module_FT__2rmH7">FT</span>
            <span class="Match-module_startTime__c49c8">17:00</span>
          </div>
          <div class="Match-module_teams__sGVeq">
            <div class="Match-module_teamName__GoJbS"><a class="Match-module_teamNameText__Dqv-G">Deportivo Alaves</a></div>
            <div class="Match-module_teamName__GoJbS"><a class="Match-module_teamNameText__Dqv-G">Getafe</a></div>
          </div>
          <div class="Match-module_right__o-ux-">
            <a id="scoresBtn-1993897" class="Match-module_score__5Ghhj" href="/matches/1993897/live/spain-laliga-2026-2027-deportivo-alaves-getafe"><span>3</span><span>0</span></a>
          </div>
        </div>
      </div>
      <div class="Match-module_match__ghi">
        <div class="Match-module_row__zwBOn">
          <div class="Match-module_left__hYvbD">
            <span class="Match-module_startTime__c49c8">16:00</span>
          </div>
          <div class="Match-module_teams__sGVeq">
            <div class="Match-module_teamName__GoJbS"><a class="Match-module_teamNameText__Dqv-G">Racing Santander</a></div>
            <div class="Match-module_teamName__GoJbS"><a class="Match-module_teamNameText__Dqv-G">Villarreal</a></div>
          </div>
          <div class="Match-module_right__o-ux-">
            <a id="scoresBtn-1993903" class="Match-module_score__5Ghhj" href="/matches/1993903/show/spain-laliga-2026-2027-racing-santander-villarreal"><span>-</span><span>-</span></a>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
"""


def test_fixtures_url():
    assert fixtures_url(LEAGUE_HTML) == (
        "/regions/206/tournaments/4/seasons/11213/stages/25662/fixtures/spain-laliga-2026-2027"
    )


def test_parse_fixtures():
    out = parse_fixtures(FIXTURES_HTML)
    assert len(out) == 2
    m = out[0]
    assert m["source_id"] == "1993903"
    assert m["date"] == "2026-08-16"
    assert m["kickoff"] == "16:00"
    assert m["home_team"] == "Racing Santander"
    assert m["away_team"] == "Villarreal"
    assert m["preview"].endswith("/preview/spain-laliga-2026-2027-racing-santander-villarreal")
    assert out[1]["preview"] == ""


def test_parse_prediction():
    d = parse_prediction(PREVIEW_HTML)
    assert d["home_goals"] == "2"
    assert d["away_goals"] == "0"
    assert d["odds"]["Home win"] == "3.4"
    assert d["odds"]["Under 2.5 goals"] == "2.08"
    assert d["odds"]["2-0"] == "15"


def test_parse_scores():
    out = parse_scores(SCORES_HTML)
    assert len(out) == 1
    m = out[0]
    assert m["source_id"] == "1993897"
    assert m["date"] == "2026-08-15"
    assert m["home_team"] == "Deportivo Alaves"
    assert m["away_team"] == "Getafe"
    assert m["home_goals"] == "3"
    assert m["away_goals"] == "0"
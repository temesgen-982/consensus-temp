from consensus.scrapers.forebet import parse_market, parse_predictions

ROW_1X2 = """
<div class="rcnt tr_0">
 <div class="stcn">
  <div class="shortagDiv tghov">
   <img onclick="getstag(this,2511198,'','English Premier League','england/premier-league','123')" />
   <span class="shortTag">EPL</span>
  </div>
  <div class="nofav fav_icon" id="2511198"></div>
 </div>
 <div class="tnms">
  <a class="tnmscn" href="/en/football/matches/arsenal-chelsea-2511198">
    <span class="homeTeam"><span itemprop="name">Arsenal</span></span>
    <span class="awayTeam"><span itemprop="name">Chelsea</span></span>
    <time datetime="2026-08-19"><span class="date_bah">19/08/2026 02:30</span></time>
  </a>
 </div>
 <div class="fprc"><span class="fpr">46</span><span>26</span><span>28</span></div>
 <div class="predict"><span class="forepr"><span>1</span></span></div>
 <div class="ex_sc tabonly">2 - 1</div>
 <div class="avg_sc tabonly">2.65</div>
</div>
"""

ROW_MARKET = """
<div class="rcnt">
 <div class="stcn">
  <div class="nofav fav_icon" id="2511198"></div>
 </div>
 <div class="fprc"><span>47</span><span class="fpr">53</span></div>
 <div class="predict"><span class="forepr forepr-tx"><span>Over</span></span></div>
</div>
"""


def test_parse_predictions():
    out = parse_predictions(ROW_1X2)
    assert "2511198" in out
    d = out["2511198"]
    assert d["home_team"] == "Arsenal"
    assert d["away_team"] == "Chelsea"
    assert d["league"] == "English Premier League"
    assert d["date"] == "2026-08-19"
    assert d["kickoff"] == "19/08/2026 02:30"
    assert d["p1"] == "46" and d["p2"] == "26" and d["p3"] == "28"
    assert d["pick"] == "1"
    assert d["cs"] == "2 - 1"
    assert d["avg"] == "2.65"


def test_parse_predictions_missing_fprc_is_skipped_safely():
    html = ROW_1X2.replace('<div class="fprc"><span class="fpr">46</span><span>26</span><span>28</span></div>', "")
    out = parse_predictions(html)
    assert out["2511198"]["p1"] == ""


def test_parse_market():
    out = parse_market(ROW_MARKET)
    assert out["2511198"]["p1"] == "47"
    assert out["2511198"]["p2"] == "53"
    assert out["2511198"]["pick"] == "Over"


def test_parse_predictions_league_page_format():
    html = ROW_1X2.replace("getstag(this,2511198,'','English Premier League','england/premier-league','123')",
                          "getstag(this,2511198,'England','Premier League','england/premier-league','123')")
    out = parse_predictions(html)
    assert out["2511198"]["league"] == "Premier League"
    assert out["2511198"]["pick"] == "1"


def test_parse_predictions_predict_y_class():
    html = ROW_1X2.replace('<div class="predict"><span class="forepr"><span>1</span></span></div>',
                          '<div class="predict_y"><span class="forepr"><span>2</span></span></div>')
    out = parse_predictions(html)
    assert out["2511198"]["pick"] == "2"
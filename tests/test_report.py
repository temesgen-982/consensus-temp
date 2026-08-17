from consensus.report import agreement_tag, majority_pick, picks_by_site


def _sites(**market_picks):
    """Build {site: {market: [row dict]}} from site -> pick_norm."""
    out = {}
    for site, picks in market_picks.items():
        out[site] = {}
        for market, pick in picks.items():
            out[site][market] = [{"pick_norm": pick}]
    return out


def test_majority_pick_clear_winner():
    sites = _sites(forebet={"1x2": "1"}, eaglepredict={"1x2": "1"}, whoscored={"1x2": "2"})
    assert majority_pick(sites, "1x2") == "1"


def test_majority_pick_tied():
    sites = _sites(forebet={"1x2": "1"}, eaglepredict={"1x2": "2"})
    assert majority_pick(sites, "1x2") is None


def test_agreement_tag():
    agree = _sites(forebet={"1x2": "2"}, flashscore={"1x2": "2"})
    split = _sites(forebet={"1x2": "1"}, flashscore={"1x2": "2"})
    single = _sites(forebet={"1x2": "1"})
    assert agreement_tag(agree, "1x2") == "agree"
    assert agreement_tag(split, "1x2") == "split"
    assert agreement_tag(single, "1x2") == "single"


def test_picks_by_site_skips_blank():
    sites = {"forebet": {"1x2": [{"pick_norm": ""}, {"pick_norm": "X"}]}}
    assert picks_by_site(sites, "1x2") == {"forebet": "X"}

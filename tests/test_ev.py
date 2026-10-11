from consensus.ev import (
    _PRIOR_PSEUDO_N,
    base_rate,
    build_ev,
    consensus_prob,
    implied_probs,
    note_odds,
    render_ev,
)

FID = "2026-10-11|hull|vs|everton"


def _row(site, market, pick, *, p1="", p2="", p3="", note="", fid=FID):
    return {
        "fixture_id": fid, "date": "2026-10-11", "home": "Hull", "away": "Everton",
        "league": "Premier League", "site": site, "market": market,
        "pick": pick, "pick_norm": pick, "p1": p1, "p2": p2, "p3": p3,
        "note": note, "scraped_at": "2026-10-11T00:00:00Z",
    }


def _odds(outcome, odds, market="1x2", provider="DraftKings", line="", fid=FID):
    return {
        "fixture_id": fid, "market": market, "outcome": outcome,
        "odds": f"{odds:.3f}", "provider": provider, "line": line, "opened": "",
        "scraped_at": "2026-10-11T10:00:00Z",
    }


def _sites(**site_picks):
    out = {}
    for site, picks in site_picks.items():
        out[site] = {}
        for market, pick in picks.items():
            out[site][market] = [{"pick_norm": pick}]
    return out


def test_implied_probs_strips_vig():
    implied = implied_probs({"1": 2.0, "X": 3.5, "2": 4.0})
    assert abs(sum(implied.values()) - 1.0) < 1e-9
    assert implied["X"] < implied["1"]  # longer odds -> lower implied


def test_note_odds_parses_only_plain_prices():
    assert note_odds("1.53") == 1.53
    assert note_odds("avg=4.22") is None
    assert note_odds("45/36/19") is None
    assert note_odds("") is None
    assert note_odds("Everton to win") is None


def test_consensus_prob_vote_only():
    sites = _sites(forebet={"1x2": "1"}, whoscored={"1x2": "1"}, eaglepredict={"1x2": "1"})
    dist, n, tag = consensus_prob(sites, "1x2", {})
    assert (n, tag) == (3, "agree")
    # vote mass (1.5 for the unanimous pick) is smoothed toward a uniform prior
    expected = (1.5 * 1.0 + _PRIOR_PSEUDO_N / 3) / (1.5 + _PRIOR_PSEUDO_N)
    assert abs(dist["1"] - expected) < 1e-9
    assert dist["1"] < 1.0  # unanimity is never priced as certainty
    assert abs(dist["1"] + dist["X"] + dist["2"] - 1.0) < 1e-9


def test_consensus_prob_blends_forebet_vector():
    sites = _sites(forebet={"1x2": "1"}, whoscored={"1x2": "1"}, eaglepredict={"1x2": "1"})
    rows = sites["forebet"]["1x2"]
    rows[0].update({"p1": "45", "p2": "36", "p3": "19"})
    dist, _, _ = consensus_prob(sites, "1x2", {})
    assert abs(dist["1"] - 0.725) < 1e-9  # 0.5*vote(1.0) + 0.5*forebet(0.45)
    assert abs(dist["X"] - 0.18) < 1e-9
    assert abs(sum(dist.values()) - 1.0) < 1e-9


def test_consensus_prob_respects_source_weights():
    sites = _sites(forebet={"1x2": "1"}, whoscored={"1x2": "2"})
    weights = {("forebet", "1x2"): 0.9, ("whoscored", "1x2"): 0.1}
    dist, n, tag = consensus_prob(sites, "1x2", weights)
    assert (n, tag) == (2, "split")
    # weighted toward the reliable forebet vote, after prior smoothing
    assert dist["1"] > dist["2"] > dist["X"]


def _ev(consensus_rows, odds_rows, **kw):
    return build_ev(consensus_rows=consensus_rows, odds_rows=odds_rows,
                    weights=kw.pop("weights", {}), **kw)


def test_build_ev_1x2_is_priced_but_never_flagged():
    # Backtest: 1x2 consensus loses to the market (47.2% hit, -0.159 ROI), so it
    # is priced for the board but excluded from VALUE however large the edge.
    consensus = [
        _row("forebet", "1x2", "X", p1="20", p2="55", p3="25"),
        _row("whoscored", "1x2", "X", note="3.5"),
        _row("eaglepredict", "1x2", "X", note="3.4"),
    ]
    odds = [_odds("1", 2.1), _odds("X", 3.5), _odds("2", 3.4)]
    rows = _ev(consensus, odds)
    assert len(rows) == 1
    row = rows[0]
    assert row["flag"] == ""
    assert row["vig"] == "norm"
    assert row["edge"] > 0.08  # priced as a big edge, still not VALUE
    raw = 1 / 2.1 + 1 / 3.5 + 1 / 3.4
    assert abs(row["implied"] - (1 / 3.5) / raw) < 1e-9  # vig stripped
    assert row["ev"] == row["p_est"] * row["odds"] - 1


def test_build_ev_two_sites_agree_is_not_flagged():
    consensus = [
        _row("forebet", "1x2", "X", p1="20", p2="55", p3="25"),
        _row("whoscored", "1x2", "X", note="3.5"),
    ]
    odds = [_odds("1", 2.1), _odds("X", 3.5), _odds("2", 3.4)]
    rows = _ev(consensus, odds)
    assert len(rows) == 1
    assert rows[0]["flag"] == ""
    assert rows[0]["n_sites"] == 2


def test_build_ev_split_majority_is_not_flagged():
    # A 3-site 1x2 split is both excluded (1x2) and below the 4-site bar.
    consensus = [
        _row("forebet", "1x2", "X", p1="30", p2="45", p3="25"),
        _row("whoscored", "1x2", "X", note="2.5"),
        _row("eaglepredict", "1x2", "1", note="2.6"),
    ]
    odds = [_odds("1", 2.6), _odds("X", 2.5), _odds("2", 4.0)]
    rows = _ev(consensus, odds)
    assert len(rows) == 1
    assert rows[0]["tag"] == "split"
    assert rows[0]["flag"] == ""


def test_build_ev_flags_value_when_four_sites_agree_on_btts():
    # The backtested VALUE shape: 4+ sites agreeing in BTTS/OU with positive EV.
    consensus = [
        _row("forebet", "btts", "Yes", p1="20", p2="55"),
        _row("whoscored", "btts", "Yes", note="3.5"),
        _row("eaglepredict", "btts", "Yes", note="3.4"),
        _row("flashscore", "btts", "Yes"),
    ]
    odds = [_odds("Yes", 3.5, market="btts"), _odds("No", 2.9, market="btts")]
    rows = _ev(consensus, odds)
    assert len(rows) == 1
    row = rows[0]
    assert row["flag"] == "VALUE"
    assert row["n_sites"] >= 4
    assert row["market"] in ("over_under", "btts")
    assert row["ev"] > 0.0


def test_build_ev_negative_ev_not_flagged():
    # book has Over so short that even consensus cannot beat the price
    consensus = [
        _row("forebet", "over_under", "Over", p1="40", p2="30"),
        _row("whoscored", "over_under", "Over", note="1.2"),
        _row("eaglepredict", "over_under", "Over", note="1.2"),
        _row("flashscore", "over_under", "Over"),
    ]
    odds = [_odds("Over", 1.2, market="over_under", line="2.5"),
            _odds("Under", 4.5, market="over_under", line="2.5")]
    rows = _ev(consensus, odds)
    assert len(rows) == 1
    row = rows[0]
    assert row["flag"] == ""
    assert row["ev"] <= 0.0


def test_build_ev_skips_non_25_over_under_line():
    consensus = [
        _row("forebet", "over_under", "Over", p1="55", p2="45"),
        _row("whoscored", "over_under", "Over", note="1.8"),
        _row("eaglepredict", "over_under", "Over", note="1.75"),
    ]
    odds = [_odds("Over", 1.8, market="over_under", line="3.0"),
            _odds("Under", 2.1, market="over_under", line="3.0")]
    assert _ev(consensus, odds) == []


def test_build_ev_btts_falls_back_to_note_prices():
    consensus = [
        _row("forebet", "btts", "Yes", p1="55", p2="45"),
        _row("whoscored", "btts", "Yes", note="1.53"),
        _row("eaglepredict", "btts", "Yes", note="1.51"),
    ]
    rows = _ev(consensus, [])
    assert len(rows) == 1
    row = rows[0]
    assert row["vig"] == "raw"
    assert row["implied"] == 1 / 1.53  # best price across the note sites
    # BTTS 3-site base rate is ~0.65, so a 0.71 estimate is only a thin edge
    # and stays under the VALUE cushion - the price is honest, not a mispricing.
    assert row["p_est"] > 0
    assert row["edge"] < 0.08
    assert row["flag"] == ""


def test_build_ev_ignores_unmatched_odds():
    assert _ev([_row("forebet", "1x2", "1")], [_odds("1", 2.0, fid="other")]) == []


def test_build_ev_skips_live_or_finished_lines():
    consensus = [
        _row("forebet", "1x2", "1", p1="60", p2="25", p3="15"),
        _row("whoscored", "1x2", "1", note="1.8"),
        _row("flashscore", "1x2", "1"),
    ]
    odds = [_odds("1", 1.8), _odds("X", 4.0), _odds("2", 5.0)]
    odds[0]["state"] = "in"  # already kicked off - line has moved
    assert _ev(consensus, odds) == []
    odds[0]["state"] = "pre"
    assert len(_ev(consensus, odds)) == 1


def test_build_ev_min_date_drops_finished_fixtures():
    consensus = [_row("forebet", "1x2", "1"), _row("whoscored", "1x2", "1")]
    odds = [_odds("1", 2.0)]
    # fixture date is 2026-10-11; floor of the next day drops it
    assert _ev(consensus, odds, min_date="2026-10-12") == []
    assert len(_ev(consensus, odds, min_date="2026-10-11")) == 1
    assert len(_ev(consensus, odds)) == 1  # no floor by default


def test_build_ev_requires_two_covering_sites():
    consensus = [_row("whoscored", "1x2", "1", note="2.0")]
    odds = [_odds("1", 2.0), _odds("X", 3.5), _odds("2", 4.0)]
    assert _ev(consensus, odds) == []


def test_render_ev_empty_and_populated():
    assert "scrape-odds" in render_ev([])
    consensus = [
        _row("forebet", "1x2", "X", p1="20", p2="55", p3="25"),
        _row("whoscored", "1x2", "X", note="3.5"),
        _row("eaglepredict", "1x2", "X", note="3.4"),
    ]
    odds = [_odds("1", 2.1), _odds("X", 3.5), _odds("2", 3.4)]
    text = render_ev(_ev(consensus, odds))
    assert "VALUE" in text
    assert "Hull v Everton" in text


def test_base_rate_measured_1x2_is_far_below_unanimity():
    # history: 3-site 1x2 majority hits ~39% overall (56% agree / 30% split),
    # 4-site ~53% - nowhere near the certainty the raw blend implied
    assert 0.35 < base_rate("1x2", 3) < 0.45
    assert 0.45 < base_rate("1x2", 4) < 0.6
    assert base_rate("1x2", 4) > base_rate("1x2", 3)  # more sites, better odds
    # btts/over_under are the stronger markets, so they earn a higher base
    assert base_rate("btts", 3) > base_rate("1x2", 3)
    assert base_rate("over_under", 4) > base_rate("1x2", 4)


def test_base_rate_thin_cells_shrink_toward_prior():
    # 2 sites is a thin, weak signal - pulled toward a coin flip
    assert 0.45 < base_rate("1x2", 2) < 0.55
    # an unmeasured market falls back to the prior, not to zero
    assert 0.4 < base_rate("correct_score", 3) < 0.6


def test_base_rate_extra_evidence_shifts_estimate():
    base = base_rate("1x2", 3)
    boosted = base_rate("1x2", 3, extra=(40, 50))  # a strong live streak
    assert boosted > base


def test_consensus_prob_calibrates_toward_base_rate():
    # unanimous 1x2 votes plus a confident forebet vector
    sites = _sites(forebet={"1x2": "1"}, whoscored={"1x2": "1"},
                   eaglepredict={"1x2": "1"}, flashscore={"1x2": "1"})
    sites["forebet"]["1x2"][0].update({"p1": "70", "p2": "20", "p3": "10"})
    raw, _, _ = consensus_prob(sites, "1x2", {})          # no target
    target = base_rate("1x2", 4)
    cal, _, _ = consensus_prob(sites, "1x2", {}, target=target)
    assert cal["1"] < raw["1"]          # calibration pulls confidence down
    assert cal["1"] > target            # but keeps some signal above the base
    assert abs(sum(cal.values()) - 1.0) < 1e-9


def test_consensus_prob_calibration_preserves_shape():
    sites = _sites(forebet={"1x2": "1"}, whoscored={"1x2": "1"},
                   eaglepredict={"1x2": "1"})
    sites["forebet"]["1x2"][0].update({"p1": "60", "p2": "25", "p3": "15"})
    dist, _, _ = consensus_prob(sites, "1x2", {}, target=0.55)
    assert dist["1"] > dist["X"] > dist["2"]  # ordering is preserved

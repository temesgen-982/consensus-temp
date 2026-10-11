from consensus.backtest import _stats, render_backtest, verdict


def _pick(edge, flag="VALUE", odds=2.0, hit=True, market="1x2", p_est=0.6, n_sites=3):
    return {
        "edge": edge, "flag": flag, "odds": odds, "hit": hit, "return": odds if hit else 0.0,
        "market": market, "p_est": p_est, "n_sites": n_sites,
        "pick": "1", "provider": "whoscored", "fixture_id": "f", "implied": 0.5,
    }


def test_stats_hit_rate_and_roi():
    rows = [_pick(0.1, hit=True, odds=2.0), _pick(0.1, hit=False, odds=2.0)]
    s = _stats(rows)
    assert s["n"] == 2
    assert s["hits"] == 1
    assert abs(s["hit_rate"] - 0.5) < 1e-9
    assert abs(s["roi"]) < 1e-9  # 1 win at 2.0 + 1 loss = break even


def test_verdict_fails_when_value_underperforms():
    # VALUE loses every pick while the no-flag complement wins -> must fail
    rows = [_pick(0.1, flag="VALUE", hit=False), _pick(-0.1, flag="", hit=True)]
    v = verdict(rows)
    assert v["holds"] is False
    assert v["value"]["hit_rate"] == 0.0
    assert v["rest"]["hit_rate"] == 1.0


def test_verdict_holds_when_value_beats_no_flag():
    rows = [_pick(0.1, flag="VALUE", hit=True, odds=2.5),
            _pick(-0.1, flag="", hit=False, odds=2.5)]
    v = verdict(rows)
    assert v["holds"] is True
    assert v["value"]["hit_rate"] > v["rest"]["hit_rate"]


def test_verdict_empty_without_value_picks():
    assert verdict([_pick(-0.1, flag="")]) == {}


def test_render_backtest_handles_empty():
    assert "no graded priced rows" in render_backtest([])

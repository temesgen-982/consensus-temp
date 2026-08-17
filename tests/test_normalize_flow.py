from consensus import normalize as normalize_mod
from consensus.config import CONSENSUS_DIR, RAW_DIR, SITES  # noqa: F401  (ensure dirs exist)
from consensus.storage import RAW_COLUMNS, append_csv, read_csv, write_csv

F_COLS = ["site", "source_id", "league", "date", "kickoff", "home_team", "away_team",
          "market", "pick", "p1", "p2", "p3", "note", "scraped_at"]


def _forebet_rows():
    return [
        {"site": "forebet", "source_id": "1001", "league": "English Premier League",
         "date": "2026-08-16", "kickoff": "16:00", "home_team": "Manchester United",
         "away_team": "Liverpool", "market": "1x2", "pick": "1", "p1": "50", "p2": "25",
         "p3": "25", "note": "", "scraped_at": "2026-08-16T10:00:00Z"},
        {"site": "forebet", "source_id": "1001", "league": "English Premier League",
         "date": "2026-08-16", "kickoff": "16:00", "home_team": "Manchester United",
         "away_team": "Liverpool", "market": "correct_score", "pick": "2 - 1",
         "p1": "", "p2": "", "p3": "", "note": "avg=2.5", "scraped_at": "2026-08-16T10:00:00Z"},
    ]


def _eagle_rows(home_name):
    return [
        {"site": "eaglepredict", "source_id": "9001", "league": "England Premier League",
         "date": "2026-08-16", "kickoff": "16:00", "home_team": home_name,
         "away_team": "Liverpool", "market": "1x2", "pick": "Liverpool Win",
         "p1": "", "p2": "", "p3": "", "note": "1.9", "scraped_at": "2026-08-16T10:00:00Z"},
    ]


def _setup(tmp_path):
    raw = tmp_path / "raw"
    canon = tmp_path / "canonical"
    cons = tmp_path / "consensus"
    raw.mkdir()
    canon.mkdir()
    cons.mkdir()
    import consensus.normalize as m
    m.RAW_DIR = raw
    m.CANONICAL_DIR = canon
    m.CONSENSUS_DIR = cons
    return raw, canon, cons


def test_normalize_merges_with_alias(tmp_path):
    raw, canon, _ = _setup(tmp_path)
    write_csv(raw / "forebet.csv", _forebet_rows(), RAW_COLUMNS)
    write_csv(raw / "eaglepredict.csv", _eagle_rows("Man Utd"), RAW_COLUMNS)
    # manual alias: EaglePredict's "Man Utd" == canonical "manchester-united"
    write_csv(canon / "aliases.csv",
              [{"site": "eaglepredict", "team_name": "Man Utd", "canonical_id": "manchester-united"}],
              ["site", "team_name", "canonical_id"])

    result = normalize_mod.normalize()
    assert result["fixtures"] == 1

    consensus = read_csv(canon.parent / "consensus" / "consensus.csv")
    assert len(consensus) == 3  # 2 forebet + 1 eagle, same fixture
    fids = {r["fixture_id"] for r in consensus}
    assert len(fids) == 1
    assert "manchester-united" in fids.pop()
    # eagle away pick normalized to 2
    eagle_row = next(r for r in consensus if r["site"] == "eaglepredict")
    assert eagle_row["pick_norm"] == "2"


def test_normalize_same_name_merges_without_alias(tmp_path):
    raw, canon, cons = _setup(tmp_path)
    write_csv(raw / "forebet.csv", _forebet_rows(), RAW_COLUMNS)
    write_csv(raw / "eaglepredict.csv", _eagle_rows("Manchester United"), RAW_COLUMNS)
    result = normalize_mod.normalize()
    assert result["fixtures"] == 1
    consensus = read_csv(cons / "consensus.csv")
    assert len({r["fixture_id"] for r in consensus}) == 1


def test_normalize_does_not_merge_different_names(tmp_path):
    raw, canon, _ = _setup(tmp_path)
    write_csv(raw / "forebet.csv", _forebet_rows(), RAW_COLUMNS)
    write_csv(raw / "eaglepredict.csv", _eagle_rows("Man Utd"), RAW_COLUMNS)
    result = normalize_mod.normalize()
    assert result["fixtures"] == 2
    assert result["single_site_fixtures"] == 2
    teams = read_csv(canon / "teams.csv")
    assert {t["canonical_id"] for t in teams} == {"manchester-united", "man-utd", "liverpool"}


def test_history_merge_prefers_complete_away(tmp_path):
    raw, canon, _ = _setup(tmp_path)
    # live CSV rolls forward: today's rows only (different match)
    write_csv(raw / "eaglepredict.csv", [], RAW_COLUMNS)
    # yesterday's snapshot duplicated in history, first copy missing away_team
    history = raw / "history"
    history.mkdir()
    empty = [
        {"site": "eaglepredict", "source_id": "9001", "league": "England Premier League",
         "date": "2026-08-16", "kickoff": "16:00", "home_team": "Man Utd",
         "away_team": "", "market": "1x2", "pick": "Liverpool Win",
         "p1": "", "p2": "", "p3": "", "note": "1.9", "scraped_at": "2026-08-16T10:00:00Z"},
    ]
    full = [
        {"site": "eaglepredict", "source_id": "9001", "league": "England Premier League",
         "date": "2026-08-16", "kickoff": "16:00", "home_team": "Man Utd",
         "away_team": "Liverpool", "market": "1x2", "pick": "Liverpool Win",
         "p1": "", "p2": "", "p3": "", "note": "1.9", "scraped_at": "2026-08-16T10:00:00Z"},
    ]
    append_csv(history / "eaglepredict-20260816.csv", empty, RAW_COLUMNS)
    append_csv(history / "eaglepredict-20260816.csv", full, RAW_COLUMNS)

    result = normalize_mod.normalize()
    consensus = read_csv(canon.parent / "consensus" / "consensus.csv")
    assert len(consensus) == 1
    assert consensus[0]["away"] == "Liverpool"
    assert consensus[0]["fixture_id"] == "2026-08-16|man-utd|vs|liverpool"
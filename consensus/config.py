from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CANONICAL_DIR = DATA_DIR / "canonical"
CONSENSUS_DIR = DATA_DIR / "consensus"
RESULTS_DIR = DATA_DIR / "results"

SITES = ("forebet", "eaglepredict", "whoscored", "flashscore")

# Only these leagues are scraped. Each site has its own naming; a league is kept
# if any of its site's patterns is a case-insensitive substring of the league name.
TOP_LEAGUES = {
    "forebet": [
        "Premier League",
        "La Liga",
        "Bundesliga",
        "Serie A",
        "Ligue 1",
        "Eredivisie",
        "Liga Portugal",
    ],
    "eaglepredict": [
        "England Premier League",
        "La Liga",
        "Germany Bundesliga",
        "Italy Serie A",
        "France Ligue 1",
        "Eredivisie",
        "Primeira Liga",
    ],
    "whoscored": [
        "Premier League",
        "LaLiga",
        "Bundesliga",
        "Serie A",
        "Ligue 1",
        "Eredivisie",
        "Liga Portugal",
    ],
    "flashscore": [
        "Premier League",
        "LaLiga",
        "Bundesliga",
        "Serie A",
        "Ligue 1",
        "Eredivisie",
        "Liga Portugal",
    ],
}


def is_top_league(site: str, league: str) -> bool:
    league = (league or "").lower()
    return any(pattern.lower() in league for pattern in TOP_LEAGUES[site])

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

FOREBET = {
    "base": "https://www.forebet.com",
    "leagues": [
        "/en/football-tips-and-predictions-for-england/premier-league",
        "/en/football-tips-and-predictions-for-spain/primera-division",
        "/en/football-tips-and-predictions-for-germany/bundesliga",
        "/en/football-tips-and-predictions-for-italy/serie-a",
        "/en/football-tips-and-predictions-for-france/ligue-1",
        "/en/football-tips-and-predictions-for-netherlands/eredivisie",
        "/en/football-tips-and-predictions-for-portugal/liga-portugal",
    ],
}

EAGLEPREDICT = {
    "base": "https://eaglepredict.com",
    "straight_win": "/predictions/straight-win/",
    "over_under": "/predictions/over-25-goals/",
    "both_to_score": "/predictions/both-teams-to-score/",
}

WHOSCORED = {
    "base": "https://www.whoscored.com",
    "leagues": [
        {"name": "Premier League", "url": "/regions/252/tournaments/2/england-premier-league"},
        {"name": "LaLiga", "url": "/regions/206/tournaments/4/spain-laliga"},
        {"name": "Bundesliga", "url": "/regions/81/tournaments/3/germany-bundesliga"},
        {"name": "Serie A", "url": "/regions/108/tournaments/5/italy-serie-a"},
        {"name": "Ligue 1", "url": "/regions/74/tournaments/22/france-ligue-1"},
        {"name": "Eredivisie", "url": "/regions/155/tournaments/13/netherlands-eredivisie"},
        {"name": "Liga Portugal", "url": "/regions/177/tournaments/21/portugal-liga-portugal"},
    ],
}

FLASHSCORE = {
    "base": "https://www.flashscore.com",
    "leagues": [
        {"name": "Premier League", "url": "/football/england/premier-league/"},
        {"name": "LaLiga", "url": "/football/spain/laliga/"},
        {"name": "Bundesliga", "url": "/football/germany/bundesliga/"},
        {"name": "Serie A", "url": "/football/italy/serie-a/"},
        {"name": "Ligue 1", "url": "/football/france/ligue-1/"},
        {"name": "Eredivisie", "url": "/football/netherlands/eredivisie/"},
        {"name": "Liga Portugal", "url": "/football/portugal/liga-portugal/"},
    ],
}


def ensure_dirs() -> None:
    for d in (RAW_DIR, CANONICAL_DIR, CONSENSUS_DIR, RESULTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
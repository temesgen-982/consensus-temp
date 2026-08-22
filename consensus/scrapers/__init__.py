from . import eaglepredict, flashscore, forebet, sportsgambler, whoscored

SCRAPERS = {
    "forebet": forebet.scrape,
    "eaglepredict": eaglepredict.scrape,
    "whoscored": whoscored.scrape,
    "flashscore": flashscore.scrape,
    "sportsgambler": sportsgambler.scrape,
}

__all__ = [
    "forebet",
    "eaglepredict",
    "whoscored",
    "flashscore",
    "sportsgambler",
    "SCRAPERS",
]

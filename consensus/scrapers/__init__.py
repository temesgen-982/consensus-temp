from . import eaglepredict, flashscore, forebet, sportsgambler, sportytrader, whoscored

SCRAPERS = {
    "forebet": forebet.scrape,
    "eaglepredict": eaglepredict.scrape,
    "whoscored": whoscored.scrape,
    "flashscore": flashscore.scrape,
    "sportsgambler": sportsgambler.scrape,
    "sportytrader": sportytrader.scrape,
}

__all__ = [
    "forebet",
    "eaglepredict",
    "whoscored",
    "flashscore",
    "sportsgambler",
    "sportytrader",
    "SCRAPERS",
]

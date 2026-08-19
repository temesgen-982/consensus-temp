from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

from ..config import FLASHSCORE
from ..http import fetch, utcnow

_REQUEST_DELAY = 2.5


def _sleep() -> None:
    time.sleep(_REQUEST_DELAY)


def _extract_env(html: str) -> dict:
    """Pull the window.environment JSON object from a Flashscore page."""
    i = html.find("window.environment = {")
    if i == -1:
        return {}
    start = html.find("{", i)
    j = start
    depth = 0
    in_str = False
    esc = False
    while j < len(html):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
        j += 1
    try:
        return json.loads(html[start : j + 1])
    except (ValueError, KeyError):
        return {}


def _extract_fixtures_feed(html: str) -> str:
    """Extract the raw `cjs.initialFeeds['fixtures']` backtick payload."""
    m = re.search(r"cjs\.initialFeeds\['fixtures'\]\s*=\s*\{\s*data:\s*`(.*?)`", html, re.S)
    return m.group(1) if m else ""


def parse_fixtures_feed(feed: str) -> list[dict]:
    """Decode Flashscore's ¬/~ separated fixture feed into match records."""
    # '~' starts a new match record; '¬' separates fields within a record.
    records = feed.split("~")
    matches: list[dict] = []
    for rec in records:
        if "AA÷" not in rec:
            continue
        cur: dict[str, str] = {}
        for field in rec.split("¬"):
            if "÷" not in field:
                continue
            k, _, v = field.partition("÷")
            cur[k] = v
        matches.append(cur)
    # dedupe by event id, keep records with both team slugs
    seen: dict[str, dict] = {}
    for m in matches:
        if m.get("WU") and m.get("WV"):
            seen.setdefault(m["AA"], m)
    return list(seen.values())


def match_url(m: dict) -> str:
    return (
        f"{FLASHSCORE['base']}/match/football/"
        f"{m['WU']}-{m['PX']}/{m['WV']}-{m['PY']}/"
    )


def parse_match(html: str) -> dict:
    """Extract match metadata + preview article from a match page."""
    env = _extract_env(html)
    if not env:
        return {}
    parts = env.get("participantsData", {})
    home = (parts.get("home") or [{}])[0]
    away = (parts.get("away") or [{}])[0]
    ep = env.get("eventPreview") or {}
    content = ep.get("contentParsed") or ep.get("content") or ""
    header = env.get("header", {}) or {}
    league = header.get("tournament") or ""
    if isinstance(league, dict):
        league = league.get("tournament") or ""
    league = re.sub(r"\s*-\s*Round\s+\d+.*$", "", league).strip()
    ts = env.get("eventStageStartTime")
    date = ""
    kickoff = ""
    if ts:
        dt = datetime.fromtimestamp(int(ts), timezone.utc)
        date = dt.strftime("%Y-%m-%d")
        kickoff = dt.strftime("%Y-%m-%d %H:%M")
    return {
        "source_id": env.get("event_id_c", ""),
        "league": league,
        "date": date,
        "kickoff": kickoff,
        "home_team": home.get("name", ""),
        "away_team": away.get("name", ""),
        "preview": content,
    }


def _clean_preview_text(content: str) -> str:
    """Strip Flashscore pseudo-tags from preview content."""
    text = re.sub(r"\[/?(?:b|i|p|h2|h3|image)[^\]]*\]", "", content)
    text = re.sub(r'\[a href="[^"]*"\]', "", text)
    text = re.sub(r"\[/a\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _betting_sentence(content: str) -> str:
    text = _clean_preview_text(content)
    m = re.search(r"Betting Analysis\s*(.*?)(?:Author:|$)", text, re.I | re.S)
    return m.group(1).strip() if m else text


def _team_variants(name: str) -> list[str]:
    """Aliases a mention could use to refer to a team, incl. nicknames."""
    n = (name or "").lower().strip()
    out = [n] if n else []
    toks = re.split(r"[\s.-]+", n)
    if "utd" in toks or "united" in toks:
        out.extend(["united", "utd"])
    if "tottenham" in toks:
        out.append("spurs")
    if "internazionale" in toks or "inter" in toks:
        out.append("inter")
    if "manchester" in toks:
        short = " ".join(t for t in toks if t != "manchester")
        if short:
            out.extend(["man " + short, short])
    return [v for v in out if v]


def _team_side(name: str, home_team: str, away_team: str) -> str:
    """Map a team phrase onto 1/2 when it clearly refers to home or away."""
    name = (name or "").strip().lower()
    name = re.sub(r"^(a|an|the)\s+", "", name).strip()
    if not name or name in {"them", "the visitors", "the hosts", "the home side", "the away side"}:
        return ""
    home = (home_team or "").lower()
    away = (away_team or "").lower()
    if not home and not away:
        return ""

    home_hit = any(v and (name == v or name in v or v in name) for v in _team_variants(home))
    away_hit = any(v and (name == v or name in v or v in name) for v in _team_variants(away))
    if home_hit and not away_hit:
        return "1"
    if away_hit and not home_hit:
        return "2"

    # Match on a distinctive word (e.g. "Villarreal", "Espanyol")
    name_words = [w for w in re.split(r"[\s.-]+", name) if len(w) > 3]
    home_words = [w for w in re.split(r"[\s.-]+", home) if len(w) > 3]
    away_words = [w for w in re.split(r"[\s.-]+", away) if len(w) > 3]
    home_overlap = any(w in home_words for w in name_words)
    away_overlap = any(w in away_words for w in name_words)
    if home_overlap and not away_overlap:
        return "1"
    if away_overlap and not home_overlap:
        return "2"
    return ""


def _pick_from_team_mentions(sentence: str, home_team: str, away_team: str) -> str:
    """Infer 1X2 when a team name appears near win/back/tip language."""
    low = sentence.lower()
    win_near = re.compile(
        r"\b(win|wins|winner|victory|victories|backed|backing|back|tip|pick|favour|favor)\b"
    )
    negative_before = re.compile(r"\b(against|facing|despite|struggl|losing|expected to|underdog|hard to beat)\b")

    def mentioned(team: str) -> bool:
        team = (team or "").strip().lower()
        if not team:
            return False
        for m in re.finditer(re.escape(team), low):
            start = max(0, m.start() - 50)
            end = min(len(low), m.end() + 50)
            if not win_near.search(low[start:end]):
                continue
            before = low[max(0, m.start() - 30) : m.start()]
            if negative_before.search(before):
                continue
            return True
        return False

    home_hit = mentioned(home_team)
    away_hit = mentioned(away_team)
    if home_hit and not away_hit:
        return "1"
    if away_hit and not home_hit:
        return "2"
    return ""


def _pick_from_draw_language(sentence: str) -> str:
    low = sentence.lower()
    draw_words = (
        r"\bdraw\b",
        r"\bstalemate\b",
        r"share the spoils",
        r"end level",
        r"finish level",
        r"point apiece",
        r"deadlock",
    )
    draw_hit = any(re.search(p, low) for p in draw_words)
    if not draw_hit:
        return ""
    # Ignore if a team is clearly tipped to win in the same sentence
    if re.search(r"\bto win\b", low) and not re.search(r"\b(the )?draw\b", low):
        return ""
    return "X"


_TIP_PATTERNS = (
    r"back(?:ing)?\s+(?:a|an|the)\s+([A-Za-zÀ-ÿ0-9 .'-]+?)\s+to win\b",
    r"back(?:ing)?\s+([A-Za-zÀ-ÿ0-9 .'-]+?)\s+to win\b",
    r"([A-Za-zÀ-ÿ0-9 .'-]{3,60}?)\s+to win\b",
    r"back(?:ing)?\s+(?:a|an|the)\s+([A-Za-zÀ-ÿ0-9 .'-]+?)\s+win\b",
    r"(?:like|fancy)\s+([A-Za-zÀ-ÿ0-9 .'-]+?)\s+for the win\b",
    r"(?:tip|pick|predict|expect|favour|favor)\s+(?:is\s+)?([A-Za-zÀ-ÿ0-9 .'-]+?)(?:\s+to|\s+for|\s+in|\.|,|$)",
    r"back(?:ing)?\s+([A-Za-zÀ-ÿ0-9 .'-]+?)\s+to score\b",
)


def _extract_1x2(sentence: str, home_team: str, away_team: str) -> str:
    low = sentence.lower()
    for pattern in _TIP_PATTERNS:
        m = re.search(pattern, sentence, re.I)
        if not m:
            continue
        team = m.group(1).strip()
        if team.lower() in {"the draw", "a draw", "draw"}:
            return "X"
        side = _team_side(team, home_team, away_team)
        if side:
            return side

    if _pick_from_draw_language(sentence):
        return "X"

    if re.search(r"\b(home win|hosts to win)\b", low):
        return "1"
    if re.search(r"\b(away win|visitors to win)\b", low):
        return "2"

    if not re.search(r"\b(against|struggl|expected to|losing)\b", low):
        if re.search(r"\b(home|hosts)\b", low) and re.search(r"\bwin\b", low):
            return "1"
        if re.search(r"\b(away|visitors)\b", low) and re.search(r"\bwin\b", low):
            return "2"

    return _pick_from_team_mentions(sentence, home_team, away_team)


def extract_markets(content: str, home_team: str = "", away_team: str = "") -> dict[str, str]:
    """Parse the Betting Analysis section into normalized picks per market.

    Returns {market: pick} for each market the preview tips, e.g.
    {"1x2": "2", "over_under": "Under", "btts": "Yes"}.
    """
    sentence = _betting_sentence(content)
    if not sentence:
        return {}
    low = sentence.lower()

    markets: dict[str, str] = {}
    pick = _extract_1x2(sentence, home_team, away_team)
    if pick:
        markets["1x2"] = pick

    m = re.search(r"\b(over|under)\s+\d+(?:\.\d+)?\s+goals?\b", low)
    if m:
        markets["over_under"] = "Over" if m.group(1).lower() == "over" else "Under"

    if re.search(r"both teams? (?:to score|scoring)", low):
        markets["btts"] = "Yes"
    elif re.search(r"both teams? (?:not to score|won'?t score|without scoring)", low):
        markets["btts"] = "No"

    return markets


def extract_prediction(content: str, home_team: str = "", away_team: str = "") -> tuple[str, str]:
    """Parse the Betting Analysis section into (pick, full sentence).

    Returns the 1X2 pick ('1'/'X'/'2') and the raw Betting Analysis sentence.
    Falls back to ('', sentence) when no pick can be determined.
    """
    sentence = _betting_sentence(content)
    if not sentence:
        return "", ""
    return extract_markets(content, home_team, away_team).get("1x2", ""), sentence


def scrape(leagues_only: bool = True, horizon_days: int = 5) -> list[dict]:
    base = FLASHSCORE["base"]
    now = utcnow()
    rows: list[dict] = []
    seen_fixtures: set[str] = set()
    now_ts = time.time()
    horizon_ts = now_ts + horizon_days * 86400

    for league in FLASHSCORE["leagues"]:
        _sleep()
        try:
            league_html = fetch(base + league["url"])
        except Exception:  # noqa: BLE001
            continue
        feed = _extract_fixtures_feed(league_html)
        fixtures = parse_fixtures_feed(feed) if feed else []
        if not fixtures:
            continue

        for m in fixtures:
            fid = m["AA"]
            if fid in seen_fixtures:
                continue
            seen_fixtures.add(fid)
            try:
                ts = int(m.get("AD") or 0)
            except (TypeError, ValueError):
                continue
            if ts < now_ts - 86400 or ts > horizon_ts:
                continue
            url = match_url(m)
            _sleep()
            try:
                match_html = fetch(url)
            except Exception:  # noqa: BLE001
                continue
            parsed = parse_match(match_html)
            if not parsed or not parsed["preview"]:
                continue

            markets = extract_markets(parsed["preview"], parsed["home_team"], parsed["away_team"])
            if not markets:
                continue
            sentence = _betting_sentence(parsed["preview"])
            for market, pick in markets.items():
                rows.append({
                    "site": "flashscore",
                    "source_id": parsed["source_id"],
                    "league": league["name"],
                    "date": parsed["date"],
                    "kickoff": parsed["kickoff"],
                    "home_team": parsed["home_team"],
                    "away_team": parsed["away_team"],
                    "market": market,
                    "pick": pick,
                    "p1": "",
                    "p2": "",
                    "p3": "",
                    "note": sentence,
                    "scraped_at": now,
                })
    return rows
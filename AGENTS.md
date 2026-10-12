# AGENTS.md

Football prediction consensus tool. Scrapes Forebet, EaglePredict, WhoScored, Flashscore; normalizes team names onto shared fixtures; grades picks against final scores; renders a static HTML report.

## Commands

Everything runs inside the venv. `pip` deps were uninstalled from system Python, so the system interpreter has no bs4/httpx/lxml/pytest.

```bash
.venv/bin/python -m consensus <cmd>     # or: .venv/bin/consensus <cmd>
.venv/bin/python -m pytest tests -q      # full suite (offline)
.venv/bin/python -m pytest tests/test_normalize_flow.py -q   # single file
```

Daily pipeline (order matters):
1. `scrape` — writes `data/raw/<site>.csv` AND snapshots to `data/raw/history/<site>-YYYYMMDD.csv`
2. `normalize` — merges live CSVs + history into `data/consensus/consensus.csv`
3. `scrape-results` — finished scores from flashscore.mobi → `data/results/flashscore.csv` (plain HTML, curl-safe; `--days N` for N past days)
4. `grade` (add `--verbose` for per-fixture detail)
5. `report-html` — writes `data/consensus/consensus.html`

`run` bundles 1+2+5 (add `--with-results` for 3+4, `--skip-scrape` to reuse raw).

Personal bet ledger: `consensus bet add --stake 50 --odds 4.986 --leg 'DATE|HOME|vs|AWAY|COND'` (repeat `--leg` per parlay leg), `consensus bet list [--pending]`, `consensus bet settle` (auto-grades legs against recorded results; add `--id N --result won|lost` to force one), `consensus bet summary`. Leg conditions: `1`/`X`/`2`, `1X`/`X2`/`12`, `O2.5`/`U3.5`, `BTTS`/`nBTTS`, `H0.5`/`A1.5`. A leg with no conditions (or free text) settles manually. Stored in `data/bets/bets.csv` + `data/bets/bet_legs.csv` — **local only, gitignored, never committed or deployed** (it's personal financial data).

## Gotchas

- **`fetch()` shells out to `curl`** (`consensus/http.py`), NOT httpx. httpx's TLS fingerprint gets blocked by Cloudflare (WhoScored 403s), curl passes. `curl` must be installed. Fetch treats bodies containing `Just a moment`/`cf-chl`/`challenge-platform` as Cloudflare challenges and retries.
- **Rate limiting is normal.** WhoScored/Flashscore intermittently challenge even curl. Scrapers use retries=6-10 + delays; a single failed league fetch is expected flakiness, not a bug. Scrapes are slow (minutes) — don't abort early.
- **Predictions for past days live in `data/raw/history/`.** Live CSVs roll forward to the current window; `normalize` merges history so past picks stay gradeable. Never delete history files. `--no-history` on scrape skips the snapshot (only for debugging).
- **History files can accumulate duplicate snapshots** (same date appended twice, sometimes one copy with empty `away_team`). `normalize` dedups by `(source_id, market)` preferring the most complete row.
- **All data is committed to git.** After a sync, commit: `git add -A && git commit`. This is the safety net if raw data is lost.
- **GitHub Pages serves `index.html` at the repo root** (a copy of `data/consensus/consensus.html`). Regenerate with `./scripts/deploy.sh`, then commit + push. Updates are commit/push based — no CI workflow needed (Pages: Deploy from a branch → main → /root).
- **`lost.html` was a one-off recovery file** (reconstructed lost WhoScored rows); do not recreate/keep it — the canonical path is the history snapshots.

## Team-name aliases

Sites spell teams differently; a match appearing as two fixtures means an alias is missing. Edit `data/canonical/aliases.csv` (`site,team_name,canonical_id`), then re-run `normalize`. `data/canonical/review_aliases.csv` lists fixtures matched on only one site — the queue for new aliases.

## Architecture

- `consensus/scrapers/` — one module per site, each exposes a `scrape()` returning raw market rows (markets: `1x2`, `over_under`, `btts`, `correct_score`).
- `consensus/normalize.py` — the merge logic (fixtures + consensus). Team name → canonical id via slugify + aliases.
- `consensus/results.py` — results scrape + grading (`evaluate_pick`, `grade`). Results come from flashscore.mobi (yesterday's finished top-league scores; joins on canonical fixture ids via flashscore aliases).
- `consensus/report.py` / `html_report.py` — terminal and static HTML renderers.
- `consensus/bets.py` — personal bet ledger (`data/bets/`, gitignored/local-only). Legs carry canonical fixture ids plus a small condition string, so `bet settle` auto-grades parlay legs against recorded results.
- `consensus/config.py` — `SITES`, `TOP_LEAGUES`, per-site league URLs, `BASE_HEADERS` (User-Agent matters for Cloudflare).
- Storage is CSV-only via `consensus/storage.py` (`read_csv`/`write_csv`/`append_csv`).
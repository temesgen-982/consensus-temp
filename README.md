# Consensus

A tool to compare football predictions from Forebet, EaglePredict, WhoScored, and Flashscore side by side. See where they agree, where they split, and how accurate each source has been.

Flashscore only publishes a preview for some matches, so there are fewer rows from them.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Daily use

Refresh predictions and open the report:

```bash
consensus run
# open data/consensus/consensus.html
```

After matches finish, grade picks against results:

```bash
consensus run --skip-scrape --with-results
```

Use `--skip-scrape` when raw data is already fresh and you just want to re-normalize and rebuild the report.

## GitHub Pages

The live report is the static file `index.html` at the repo root (a copy of `data/consensus/consensus.html`). To regenerate and deploy:

```bash
./scripts/deploy.sh     # re-runs report-html + copies to index.html
git add -A && git commit -m "Daily sync"
git push                # GitHub Pages serves / (root) on main
```

Requires GitHub Pages set to **Deploy from a branch** → `main` → `/ (root)`.

## Commands

| Command | What it does |
|---------|--------------|
| `consensus run` | Scrape, normalize, write HTML report |
| `consensus scrape` | Fetch predictions into `data/raw/` |
| `consensus normalize` | Join raw data into `data/consensus/consensus.csv` |
| `consensus report` | Print a text comparison |
| `consensus report-html` | Write `data/consensus/consensus.html` |
| `consensus scrape-results` | Fetch finished scores from WhoScored |
| `consensus grade` | Accuracy by site, plus agree/majority stats |
| `consensus status` | Row counts |

## Team names

Sites spell team names differently. When the same match shows up as two fixtures, add a row to `data/canonical/aliases.csv`:

```csv
whoscored,NEC Nijmegen,nijmegen
```

Then run `consensus normalize` again. Check `data/canonical/review_aliases.csv` for fixtures that only matched on one site.

## Data layout

```
data/raw/           scraped predictions (one CSV per site)
data/canonical/     fixtures, team map, aliases
data/consensus/     joined comparison table + HTML report
data/results/       finished match scores
```

## Tests

```bash
pytest
```

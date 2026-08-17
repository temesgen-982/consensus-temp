from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import normalize as normalize_mod
from . import report as report_mod
from .config import CANONICAL_DIR, CONSENSUS_DIR, RAW_DIR, RESULTS_DIR, SITES, ensure_dirs
from .scrapers import SCRAPERS
from .storage import RAW_COLUMNS, append_csv, read_csv, write_csv


def cmd_scrape(args) -> None:
    ensure_dirs()
    sites = list(SITES) if args.site == "all" else [args.site]
    for site in sites:
        rows = SCRAPERS[site](leagues_only=not args.all_leagues)
        write_csv(RAW_DIR / f"{site}.csv", rows, RAW_COLUMNS)
        if rows and not args.no_history:
            stamp = rows[0]["scraped_at"][:10].replace("-", "")
            history = RAW_DIR / "history"
            history.mkdir(parents=True, exist_ok=True)
            append_csv(history / f"{site}-{stamp}.csv", rows, RAW_COLUMNS)
        print(f"{site}: {len(rows)} market rows -> {RAW_DIR / (site + '.csv')}")
        if args.print:
            for r in rows[: args.limit]:
                print(" ", r["league"], "|", r["home_team"], "vs", r["away_team"],
                      "|", r["market"], "=", r["pick"], r["note"] or "")


def cmd_normalize(args) -> None:
    result = normalize_mod.normalize()
    print("fixtures:", result["fixtures"])
    print("consensus rows:", result["consensus_rows"])
    print("teams:", result["teams"], "| manual aliases:", result["aliases"])
    print("single-site fixtures (review for aliases):", result["single_site_fixtures"])


def cmd_report(args) -> None:
    data = report_mod.build_report_data()
    print(report_mod.render_report(
        data,
        date=args.date,
        league=args.league,
        fixture_id=args.fixture_id,
        upcoming_only=args.upcoming,
    ))


def cmd_status(args) -> None:
    for site in SITES:
        rows = read_csv(RAW_DIR / f"{site}.csv")
        print(f"raw {site}: {len(rows)} rows")
    fixtures = read_csv(CANONICAL_DIR / "fixtures.csv")
    consensus = read_csv(CONSENSUS_DIR / "consensus.csv")
    teams = read_csv(CANONICAL_DIR / "teams.csv")
    print(f"fixtures: {len(fixtures)}")
    print(f"consensus rows: {len(consensus)}")
    print(f"teams (aliases): {len(teams)}")


def cmd_report_html(args) -> None:
    from .html_report import write_html

    path = write_html(args.out)
    print(f"wrote {path}")


def cmd_scrape_results(args) -> None:
    from .results import save_results, scrape_results

    rows = scrape_results()
    save_results(rows)
    print(f"whoscored: {len(rows)} finished matches -> {RESULTS_DIR / 'whoscored.csv'}")
    if args.print:
        for r in rows[: args.limit]:
            print(" ", r["league"], "|", r["home_team"], r["home_goals"],
                  "-", r["away_goals"], r["away_team"])


def cmd_grade(args) -> None:
    from .results import load_results, render_fixture_results, render_grade, grade

    results = load_results()
    if not results:
        print("no results yet - run 'consensus scrape-results' first")
        return
    result = grade(results)
    print(render_grade(result))
    if args.verbose:
        print()
        print(render_fixture_results(result))


def cmd_run(args) -> None:
    if not args.skip_scrape:
        cmd_scrape(args)
    cmd_normalize(args)
    cmd_report_html(args)
    if args.with_results:
        cmd_scrape_results(args)
        cmd_grade(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="consensus", description="Centralized football prediction comparison")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape", help="scrape prediction sites into data/raw")
    p_scrape.add_argument("--site", choices=[*SITES, "all"], default="all")
    p_scrape.add_argument("--print", action="store_true", help="print scraped rows")
    p_scrape.add_argument("--limit", type=int, default=20)
    p_scrape.add_argument("--no-history", action="store_true", help="disable daily history snapshot")
    p_scrape.add_argument("--all-leagues", action="store_true", help="scrape all leagues (default: top leagues only)")
    p_scrape.set_defaults(func=cmd_scrape)

    p_norm = sub.add_parser("normalize", help="join raw scrapes into canonical fixtures + consensus CSV")
    p_norm.set_defaults(func=cmd_normalize)

    p_rep = sub.add_parser("report", help="print side-by-side prediction comparison")
    p_rep.add_argument("--date", help="YYYY-MM-DD filter")
    p_rep.add_argument("--league", help="league substring filter")
    p_rep.add_argument("--fixture-id", help="exact fixture id")
    p_rep.add_argument("--upcoming", action="store_true", help="only fixtures on/after today")
    p_rep.set_defaults(func=cmd_report)

    p_status = sub.add_parser("status", help="show dataset counts")
    p_status.set_defaults(func=cmd_status)

    p_html = sub.add_parser("report-html", help="write a static HTML report")
    p_html.add_argument("--out", help="output path (default data/consensus/consensus.html)")
    p_html.set_defaults(func=cmd_report_html)

    p_res = sub.add_parser("scrape-results", help="scrape finished-match results from WhoScored")
    p_res.add_argument("--print", action="store_true", help="print scraped rows")
    p_res.add_argument("--limit", type=int, default=20)
    p_res.set_defaults(func=cmd_scrape_results)

    p_grade = sub.add_parser("grade", help="grade consensus picks against recorded results")
    p_grade.add_argument("--verbose", action="store_true", help="show per-fixture detail")
    p_grade.set_defaults(func=cmd_grade)

    p_run = sub.add_parser("run", help="daily pipeline: scrape, normalize, report-html")
    p_run.add_argument("--site", choices=[*SITES, "all"], default="all")
    p_run.add_argument("--no-history", action="store_true", help="disable daily history snapshot")
    p_run.add_argument("--all-leagues", action="store_true", help="scrape all leagues (default: top only)")
    p_run.add_argument("--skip-scrape", action="store_true", help="reuse existing raw CSVs")
    p_run.add_argument("--with-results", action="store_true", help="also scrape results and print grade")
    p_run.add_argument("--out", help="HTML output path (default data/consensus/consensus.html)")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    ensure_dirs()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
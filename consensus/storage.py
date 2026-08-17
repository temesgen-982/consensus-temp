from __future__ import annotations

import csv
from pathlib import Path

from .config import RAW_DIR

RAW_COLUMNS = [
    "site",
    "source_id",
    "league",
    "date",
    "kickoff",
    "home_team",
    "away_team",
    "market",
    "pick",
    "p1",
    "p2",
    "p3",
    "note",
    "scraped_at",
]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = columns or (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = columns or (list(rows[0].keys()) if rows else [])
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def raw_path(site: str) -> Path:
    return RAW_DIR / f"{site}.csv"
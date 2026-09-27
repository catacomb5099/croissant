"""curate <category>: build one edition of a suggested playlist, write it, log it."""

import argparse
import sys
from datetime import date

from .run import ROOT, categories, run_category


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("category", help="key in categories.yaml")
    p.add_argument("--size", type=int, default=40, help="songs per playlist (default 40)")
    p.add_argument("--seed", type=int, help="fix the random seed (default: fresh, recorded)")
    p.add_argument(
        "--exclude-last", type=int, default=4, help="skip songs featured in the last K editions"
    )
    p.add_argument(
        "--date", type=date.fromisoformat, default=date.today(), help="edition date (YYYY-MM-DD)"
    )
    a = p.parse_args()

    cats = categories(ROOT)
    if a.category not in cats:
        sys.exit(f"unknown category {a.category!r}; known: {', '.join(cats)}")
    r = run_category(
        a.category,
        cats[a.category],
        size=a.size,
        seed=a.seed,
        exclude_last=a.exclude_last,
        date=a.date.isoformat(),
    )
    if r["status"] != "written":
        sys.exit(
            r["message"] + ("; delete it to rerun this edition" if r["status"] == "exists" else "")
        )
    print(r["message"])

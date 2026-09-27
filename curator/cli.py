"""curate <category>: build one edition of a suggested playlist, write it, log it."""

import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

import yaml
from ytmusicapi import YTMusic

from . import discogs, picker, ytmusic

ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("category", help="key in categories.yaml")
    p.add_argument("--size", type=int, default=40, help="songs per playlist (default 40)")
    p.add_argument("--seed", type=int, help="fix the random seed (default: fresh, recorded)")
    p.add_argument(
        "--exclude-last", type=int, default=4, help="skip songs featured in the last K editions"
    )
    p.add_argument("--date", default=date.today().isoformat(), help="edition date (YYYY-MM-DD)")
    a = p.parse_args()

    cats = yaml.safe_load((ROOT / "categories.yaml").read_text())
    if a.category not in cats:
        sys.exit(f"unknown category {a.category!r}; known: {', '.join(cats)}")
    cat = cats[a.category]
    lo, hi = map(int, str(cat["year"]).split("-"))
    filters = {k: v for k, v in cat.items() if k != "title"}

    albums = discogs.top_albums(filters)
    if not albums:
        sys.exit(f"Discogs returned no albums for {filters}; widen the category")
    print(f"Discogs: {len(albums)} albums", file=sys.stderr)

    yt = YTMusic()
    pool = []
    for i, al in enumerate(albums, 1):
        try:
            tracks = ytmusic.album_tracks(yt, al["artist"], al["album"], (lo, hi))
        except Exception as e:  # one bad album must not kill a weekly run
            tracks, note = [], f" ({e!r})"
        else:
            note = ""
        pool += tracks
        print(
            f"  [{i}/{len(albums)}] {al['artist']} - {al['album']}: {len(tracks)}{note}",
            file=sys.stderr,
        )
    print(f"YouTube Music: {len(pool)} tracks in the pool", file=sys.stderr)

    hist_file = ROOT / "history" / f"{a.category}.jsonl"
    history = (
        [json.loads(line) for line in hist_file.read_text().splitlines() if line.strip()]
        if hist_file.exists()
        else []
    )
    recent = history[-a.exclude_last :] if a.exclude_last else []
    exclude = {t["videoId"] for ed in recent for t in ed["tracks"]}
    seed = a.seed if a.seed is not None else random.SystemRandom().randrange(2**31)
    tracks = picker.build_playlist(pool, size=a.size, seed=seed, exclude=exclude)

    edition = {
        "title": cat["title"],
        "category": cat,
        "editionDate": a.date,
        "seed": seed,
        "tracks": tracks,
    }
    out = ROOT / "output" / a.category / f"{a.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(edition, indent=1, ensure_ascii=False) + "\n")
    hist_file.parent.mkdir(exist_ok=True)
    with hist_file.open("a") as f:
        log = {
            "editionDate": a.date,
            "seed": seed,
            "tracks": [{k: t[k] for k in ("videoId", "title", "tier", "reason")} for t in tracks],
        }
        f.write(json.dumps(log, ensure_ascii=False) + "\n")
    print(
        f"wrote {out.relative_to(ROOT)}: {len(tracks)} tracks, seed {seed}, "
        f"{len(exclude)} songs excluded from the last {len(recent)} edition(s)"
    )

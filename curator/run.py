"""Build one edition of one category: the pipeline shared by the CLI and the service."""

import json
import os
import random
import sys
from datetime import date as _date
from pathlib import Path

import yaml
from ytmusicapi import YTMusic

from . import discogs, picker, ytmusic

# categories.yaml, output/, history/ and runs/ live here; CURATOR_ROOT relocates them (Docker).
ROOT = Path(os.environ.get("CURATOR_ROOT") or Path(__file__).resolve().parent.parent)


def categories(root=ROOT):
    return yaml.safe_load((root / "categories.yaml").read_text())


def run_category(key, cat, *, size=40, seed=None, exclude_last=4, date=None, root=ROOT):
    """Return {"key","status","editionDate","trackCount","message"}.

    status: written | exists | no_albums | thin_pool. Unexpected errors raise.
    """
    ed = date or _date.today().isoformat()
    result = {"key": key, "status": None, "editionDate": ed, "trackCount": None, "message": None}
    out = root / "output" / key / f"{ed}.json"
    if out.exists():
        return result | {"status": "exists", "message": f"{out.relative_to(root)} already exists"}
    lo, hi = map(int, str(cat["year"]).split("-"))
    filters = {k: v for k, v in cat.items() if k != "title"}

    albums = discogs.top_albums(filters)
    if not albums:
        return result | {
            "status": "no_albums",
            "message": f"Discogs returned no albums for {filters}",
        }
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

    hist_file = root / "history" / f"{key}.jsonl"
    history = (
        [json.loads(line) for line in hist_file.read_text().splitlines() if line.strip()]
        if hist_file.exists()
        else []
    )
    recent = history[-exclude_last:] if exclude_last else []
    exclude = {t["videoId"] for ed_ in recent for t in ed_["tracks"]}
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)
    tracks = picker.build_playlist(pool, size=size, seed=seed, exclude=exclude)
    if len(tracks) < size:
        return result | {
            "status": "thin_pool",
            "trackCount": len(tracks),
            "message": f"only {len(tracks)} of {size} songs available; not writing an edition",
        }

    edition = {
        "title": cat["title"],
        "category": cat,
        "editionDate": ed,
        "seed": seed,
        "tracks": tracks,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(edition, indent=1, ensure_ascii=False) + "\n")
    hist_file.parent.mkdir(exist_ok=True)
    with hist_file.open("a") as f:
        log = {
            "editionDate": ed,
            "seed": seed,
            "tracks": [{k: t[k] for k in ("videoId", "title", "tier", "reason")} for t in tracks],
        }
        f.write(json.dumps(log, ensure_ascii=False) + "\n")
    return result | {
        "status": "written",
        "trackCount": len(tracks),
        "message": f"wrote {out.relative_to(root)}: {len(tracks)} tracks, seed {seed}, "
        f"{len(exclude)} songs excluded from the last {len(recent)} edition(s)",
    }

"""YouTube Music lookups (anonymous): find an album and read per-track play counts."""

import re

_SUFFIX = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def parse_plays(views):
    """'2.2B plays' -> 2200000000, '12M plays' -> 12000000, '1,234 plays' -> 1234, else None."""
    if not views:
        return None
    m = re.match(r"([\d.,]+)\s*([KMB])?", views.strip())
    if not m:
        return None
    return int(float(m.group(1).replace(",", "")) * _SUFFIX.get(m.group(2), 1))


def album_tracks(yt, artist, album, year_range):
    """Tracks of the best album match with numeric popularity, or [] when not found.

    A match whose year falls outside year_range is treated as the wrong album (a Discogs
    single 'Lullaby' otherwise resolves to a 2001 Greatest Hits).
    """
    hits = yt.search(f"{artist} {album}", filter="albums", limit=3)
    if not hits:
        return []
    detail = yt.get_album(hits[0]["browseId"])
    year = str(detail.get("year", ""))
    year = int(year) if year.isdigit() else None
    lo, hi = year_range
    if year is not None and not lo <= year <= hi:
        return []
    return [
        {
            "videoId": t["videoId"],
            "title": t["title"],
            "artists": [a["name"] for a in t.get("artists") or []],
            "album": detail["title"],
            "albumYear": year,
            "popularity": parse_plays(t.get("views")) or 0,
        }
        for t in detail.get("tracks", [])
        if t.get("videoId")
    ]

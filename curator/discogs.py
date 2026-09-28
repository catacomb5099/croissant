"""Discogs database search: most-collected master albums for a set of filters."""

import os
import re

import requests

API = "https://api.discogs.com/database/search"
HEADERS = {"User-Agent": "croissant/0.1 +https://github.com/catacomb5099/croissant"}
if os.environ.get("DISCOGS_TOKEN"):  # optional: lifts the limit from 25 to 60 requests/minute
    HEADERS["Authorization"] = f"Discogs token={os.environ['DISCOGS_TOKEN']}"


def top_albums(filters, limit=100):
    """filters: Discogs search params such as year="1980-1989", style="Indie Pop", genre="Pop".

    Returns [{artist, album, year, have}] sorted by most collected ("have"), compilations by
    'Various' dropped. One request per 100 results.
    """
    params = {
        **filters,
        "type": "master",
        "format": "Album",
        "sort": "have",
        "sort_order": "desc",
        "per_page": 100,
    }
    out, page = [], 1
    while len(out) < limit:
        r = requests.get(API, params={**params, "page": page}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        body = r.json()
        for item in body["results"]:
            artist, _, album = item["title"].partition(" - ")
            # Discogs disambiguates duplicate names as "M.I.A. (2)" or "MIA*"; strip that.
            artist = re.sub(r"\s*\(\d+\)$", "", artist).rstrip("*")
            if artist == "Various":
                continue
            year = str(item.get("year", ""))
            out.append(
                {
                    "artist": artist,
                    "album": album,
                    "year": int(year) if year.isdigit() else None,
                    "have": item["community"]["have"],
                }
            )
        if page >= body["pagination"]["pages"]:
            break
        page += 1
    return out[:limit]

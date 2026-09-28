"""Pure playlist selection: a pool of tracks in, one playlist out. No I/O, no network."""

import random
from collections import Counter

TIERS = {"top": 0.5, "random": 0.25, "mid": 0.25}


def _album_key(t):
    return t["albumId"]


def _song_key(t):
    return (t["artists"][0].lower() if t["artists"] else "", t["title"].lower())


def build_playlist(pool, *, size, seed, exclude=frozenset(), max_per_artist=5, max_per_album=2):
    """pool: dicts with videoId, title, artists (list[str]), album, albumId, albumYear, popularity.

    Returns `size` tracks (fewer only when the pool runs dry), each with 'tier' and 'reason'
    added. Same pool + same seed + same exclusions -> same playlist.
    """
    rng = random.Random(seed)
    ranked, seen_ids = [], set()
    # An excluded song may exist as another copy (deluxe/reissue) under a different videoId.
    seen_songs = {_song_key(t) for t in pool if t["videoId"] in exclude}
    for t in sorted(pool, key=lambda t: (-t["popularity"], t["videoId"])):
        # Same song on a deluxe/reissue has a different videoId; keep the most played copy.
        if t["videoId"] in exclude or t["videoId"] in seen_ids or _song_key(t) in seen_songs:
            continue
        seen_ids.add(t["videoId"])
        seen_songs.add(_song_key(t))
        ranked.append(t)
    rank = {t["videoId"]: i + 1 for i, t in enumerate(ranked)}
    n_pool = len(ranked)

    n_top = round(size * TIERS["top"])
    n_mid = round(size * TIERS["mid"])
    n_random = size - n_top - n_mid

    picked, artists, albums = [], Counter(), Counter()

    def fits(t):
        return all(artists[a] < max_per_artist for a in t["artists"]) and (
            albums[_album_key(t)] < max_per_album
        )

    def take(t, tier, reason):
        picked.append({**t, "tier": tier, "reason": reason})
        artists.update(t["artists"])
        albums[_album_key(t)] += 1
        ranked.remove(t)

    # Tier 1: straight popularity ranking, playlist-wide caps only.
    for t in list(ranked):
        if len(picked) >= n_top:
            break
        if fits(t):
            take(t, "top", f"#{rank[t['videoId']]} of {n_pool} by plays")

    # Tier 2: the top quarter of what is left (well known, not the hits), one per artist and album.
    band = ranked[: len(ranked) // 4]
    rng.shuffle(band)
    tier_artists, tier_albums = set(), set()
    for t in band:
        if len(picked) >= n_top + n_mid:
            break
        if fits(t) and not (set(t["artists"]) & tier_artists) and _album_key(t) not in tier_albums:
            tier_artists.update(t["artists"])
            tier_albums.add(_album_key(t))
            take(t, "mid", f"#{rank[t['videoId']]} of {n_pool}, middle band, one per artist/album")

    # Tier 3: random from everything left, playlist-wide caps only.
    rest = list(ranked)
    rng.shuffle(rest)
    for t in rest:
        if len(picked) >= n_top + n_mid + n_random:
            break
        if fits(t):
            take(t, "random", f"random pick (seed {seed}) from {len(rest)} remaining")

    # Thin pool: top up by popularity so the edition still has `size` songs when possible.
    for t in list(ranked):
        if len(picked) >= size:
            break
        if fits(t):
            take(t, "top", f"#{rank[t['videoId']]} of {n_pool} by plays (top-up, tiers ran dry)")

    # Final order is fully shuffled so hits, mid-tier and random picks are mixed together, except
    # that the playlist opens with two hits (any two, the shuffle decides which) to start strong.
    rng.shuffle(picked)
    openers = [t for t in picked if t["tier"] == "top"][:2]
    return openers + [t for t in picked if t not in openers]

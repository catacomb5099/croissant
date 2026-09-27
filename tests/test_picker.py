import random
from collections import Counter

from curator.picker import build_playlist


def make_pool(n_albums=100, tracks_per_album=10, n_artists=60, seed=1):
    rng = random.Random(seed)
    pool = []
    for a in range(n_albums):
        for t in range(tracks_per_album):
            pool.append(
                {
                    "videoId": f"v{a}_{t}",
                    "title": f"song {a}-{t}",
                    "artists": [f"artist{a % n_artists}"],
                    "album": f"album{a}",
                    "albumId": f"al{a}",
                    "albumYear": 1980 + a % 10,
                    "popularity": rng.randrange(1_000, 100_000_000),
                }
            )
    return pool


POOL = make_pool()
DUP = [  # the same song on the standard and the deluxe album
    {
        "videoId": "a",
        "title": "Hit",
        "artists": ["X"],
        "album": "LP",
        "albumId": "lp",
        "albumYear": 1,
        "popularity": 10**12,
    },
    {
        "videoId": "b",
        "title": "hit",
        "artists": ["X"],
        "album": "LP (Deluxe)",
        "albumId": "lp-deluxe",
        "albumYear": 1,
        "popularity": 10**11,
    },
]


def test_size_and_no_duplicates():
    for size in (30, 40, 50):
        pl = build_playlist(POOL, size=size, seed=1)
        assert len(pl) == size
        assert len({t["videoId"] for t in pl}) == size


def test_playlist_wide_caps_hold_across_tiers():
    pl = build_playlist(POOL, size=50, seed=2)
    assert max(Counter(a for t in pl for a in t["artists"]).values()) <= 5
    assert max(Counter(t["albumId"] for t in pl).values()) <= 2


def test_album_cap_holds_when_tracks_credit_different_first_artists():
    lp = [
        {
            "videoId": f"lp{i}",
            "title": f"song {i}",
            "artists": arts,
            "album": "LP",
            "albumId": "lp",
            "albumYear": 1,
            "popularity": 10**12 - i,
        }
        for i, arts in enumerate([["A"], ["A", "B"], ["B", "A"], ["C"]])
    ]
    pl = build_playlist(lp + POOL[:200], size=30, seed=1)
    assert sum(t["albumId"] == "lp" for t in pl) == 2


def test_mid_tier_one_per_artist_and_album():
    mid = [t for t in build_playlist(POOL, size=40, seed=3) if t["tier"] == "mid"]
    assert len(mid) == 10
    assert len({t["artists"][0] for t in mid}) == len(mid)
    assert len({t["album"] for t in mid}) == len(mid)


def test_tier_ratios_within_rounding():
    assert Counter(t["tier"] for t in build_playlist(POOL, size=40, seed=4)) == {
        "top": 20,
        "random": 10,
        "mid": 10,
    }
    c = Counter(t["tier"] for t in build_playlist(POOL, size=30, seed=4))
    assert c["top"] == 15 and c["mid"] + c["random"] == 15 and abs(c["mid"] - c["random"]) <= 1


def test_excluded_songs_never_reappear():
    first = build_playlist(POOL, size=40, seed=5)
    excluded = {t["videoId"] for t in first}
    second = build_playlist(POOL, size=40, seed=5, exclude=excluded)
    assert len(second) == 40
    assert not excluded & {t["videoId"] for t in second}


def test_seed_controls_randomness():
    a = [t["videoId"] for t in build_playlist(POOL, size=40, seed=1)]
    b = [t["videoId"] for t in build_playlist(POOL, size=40, seed=2)]
    assert a != b
    assert a == [t["videoId"] for t in build_playlist(POOL, size=40, seed=1)]


def test_top_tier_is_the_most_played_under_caps():
    pl = build_playlist(POOL, size=40, seed=6)
    top = [t["popularity"] for t in pl if t["tier"] == "top"]
    others = [t["popularity"] for t in pl if t["tier"] != "top"]
    assert max(others) <= min(top)


def test_same_song_on_two_editions_kept_once():
    pl = build_playlist(DUP + POOL[:200], size=30, seed=1)
    assert [t["videoId"] for t in pl if t["title"].lower() == "hit"] == ["a"]


def test_excluded_song_does_not_come_back_as_its_deluxe_copy():
    pl = build_playlist(DUP + POOL[:200], size=30, seed=1, exclude={"a"})
    assert not [t for t in pl if t["title"].lower() == "hit"]


def test_thin_pool_returns_what_it_can_without_breaking_caps():
    pl = build_playlist(POOL[:60], size=40, seed=7)  # 6 albums, cap 2 each -> at most 12
    assert len(pl) == 12
    assert max(Counter(t["album"] for t in pl).values()) <= 2

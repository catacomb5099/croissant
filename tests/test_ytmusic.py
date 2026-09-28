import pytest

from curator.ytmusic import album_tracks, parse_plays


@pytest.mark.parametrize(
    "views,plays",
    [
        ("2.2B plays", 2_200_000_000),
        ("12M plays", 12_000_000),
        ("627K plays", 627_000),
        ("1,234 plays", 1234),
        ("", None),
        (None, None),
        ("plays", None),
    ],
)
def test_parse_plays(views, plays):
    assert parse_plays(views) == plays


class FakeYT:
    def __init__(self, year):
        self.album = {
            "title": "LP",
            "year": year,
            "tracks": [
                {"videoId": "v1", "title": "One", "artists": [{"name": "A"}], "views": "12M plays"},
                {"videoId": "v2", "title": "Two", "artists": [], "views": "1K plays"},  # no artist
                {"title": "Three", "artists": [{"name": "A"}]},  # unavailable: no videoId
            ],
        }

    def search(self, query, filter, limit):
        return [{"browseId": "MPREb_lp"}]

    def get_album(self, browse_id):
        return self.album


def test_album_tracks_carries_album_id_and_drops_unusable_tracks():
    assert album_tracks(FakeYT("1986"), "A", "LP", (1980, 1989)) == [
        {
            "videoId": "v1",
            "title": "One",
            "artists": ["A"],
            "album": "LP",
            "albumId": "MPREb_lp",
            "albumYear": 1986,
            "popularity": 12_000_000,
        }
    ]


def test_album_tracks_rejects_a_match_outside_the_year_range():
    assert album_tracks(FakeYT("2001"), "A", "LP", (1980, 1989)) == []

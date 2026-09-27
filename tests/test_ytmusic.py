import pytest

from curator.ytmusic import parse_plays


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

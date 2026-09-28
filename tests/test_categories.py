"""categories.yaml is data the weekly run trusts blindly; catch typos here, not at 3am on Monday."""

from pathlib import Path

import yaml

DISCOGS_FILTERS = {"year", "genre", "style", "country"}


def test_every_category_has_a_title_a_year_range_and_only_discogs_filters():
    cats = yaml.safe_load((Path(__file__).resolve().parents[1] / "categories.yaml").read_text())
    assert len(cats) >= 3
    for key, cat in cats.items():
        assert cat.get("title"), key
        lo, hi = map(int, str(cat["year"]).split("-"))
        assert 1900 <= lo <= hi <= 2100, key
        assert set(cat) - {"title"} <= DISCOGS_FILTERS, key
    titles = [c["title"] for c in cats.values()]
    assert len(set(titles)) == len(titles), "two categories share a title"

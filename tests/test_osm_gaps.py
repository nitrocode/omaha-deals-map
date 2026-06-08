"""Tests for the OSM gap report classifier."""
from scripts.oneoff.generate_osm_gaps import classify_gap


def test_no_gap_when_osm_has_image():
    assert classify_gap({"url": "x", "source": "osm"}) is None


def test_wikidata_source_means_missing_image_but_has_wikidata():
    assert classify_gap({"url": "x", "source": "wikidata"}) == \
        "no_osm_image_but_has_wikidata"


def test_og_source_means_missing_image_but_has_website():
    assert classify_gap({"url": "x", "source": "og"}) == \
        "no_osm_image_but_has_website"


def test_null_entry_means_missing_everything():
    assert classify_gap(None) == "missing_website_and_image"
    assert classify_gap({"url": None, "source": None}) == \
        "missing_website_and_image"

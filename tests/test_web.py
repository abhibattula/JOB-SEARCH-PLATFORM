"""013 (Refinements): web-layer presentation helpers."""
from web.main import _humandate


def test_iso_date_to_human():
    assert _humandate("2026-07-24") == "24 July 2026"


def test_iso_datetime_to_human():
    assert _humandate("2026-07-24T09:15:00") == "24 July 2026"


def test_day_has_no_leading_zero():
    assert _humandate("2026-07-04") == "4 July 2026"


def test_none_and_empty_pass_through():
    assert _humandate(None) == ""
    assert _humandate("") == ""


def test_unparseable_returned_unchanged():
    assert _humandate("sometime") == "sometime"

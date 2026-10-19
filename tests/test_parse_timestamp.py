import datetime

import pytest

from dashcamutils.helpers import Settings, parse_timestamp, parse_with_settings


def test_ymd_with_gps():
    d, g = parse_timestamp("GARMIN 2021/03/10 21:23:30 41.87074 -87.61696 35 MPH")
    assert d == datetime.datetime(2021, 3, 10, 21, 23, 30)
    assert g == (41.87074, -87.61696, 35)


def test_mdy_12_hour():
    d, g = parse_timestamp("GARMIN 10/23/2022 10:31:08 PM 41.87795 -87.62056 26 MPF")
    assert d == datetime.datetime(2022, 10, 23, 22, 31, 8)
    assert g == (41.87795, -87.62056, 26)


def test_mdy_24_hour():
    d, _ = parse_timestamp("GARMIN 10/23/2022 22:31:08 41.87795 -87.62056 26 MPH")
    assert d == datetime.datetime(2022, 10, 23, 22, 31, 8)


def test_ocr_noise_characters_removed():
    d, g = parse_timestamp("GARMIN 2021/03/10 21:23:30 41.87074 -87.61696 35 MPH)Z+")
    assert d is not None and g is not None


def test_missing_gps():
    d, g = parse_timestamp("GARMIN 2021/03/10 21:23:30")
    assert d is not None
    assert g is None


def test_garbage():
    assert parse_timestamp("nothing here") == (None, None)


@pytest.mark.parametrize("line", ["", "\n"])
def test_empty(line):
    assert parse_timestamp(line) == (None, None)


def test_day_first_detected_when_unambiguous():
    d, _ = parse_timestamp("GARMIN 23/10/2022 22:31:08 41.87795 -87.62056 26 MPH")
    assert d == datetime.datetime(2022, 10, 23, 22, 31, 8)


def test_ambiguous_uses_preference_and_override():
    line = "GARMIN 03/04/2022 10:00:00 41.87795 -87.62056 26 MPH"
    assert parse_timestamp(line)[0] == datetime.datetime(2022, 3, 4, 10)
    assert parse_timestamp(line, prefer="dmy")[0] == datetime.datetime(2022, 4, 3, 10)
    assert parse_timestamp(line, date_order="dmy")[0] == datetime.datetime(
        2022, 4, 3, 10
    )


def test_ymd_ignores_date_order():
    d, _ = parse_timestamp("GARMIN 2021/03/10 21:23:30", date_order="dmy")
    assert d == datetime.datetime(2021, 3, 10, 21, 23, 30)


def test_batch_learns_date_order():
    s = Settings()
    parse_with_settings("GARMIN 23/10/2022 22:31:08 41.87795 -87.62056 26 MPH", s)
    when, _ = parse_with_settings(
        "GARMIN 03/04/2022 10:00:00 41.87795 -87.62056 26 MPH", s
    )
    assert when == datetime.datetime(2022, 4, 3, 10)


def test_impossible_date_rejected():
    assert parse_timestamp("GARMIN 31/31/2022 10:00:00")[0] is None

import logging

from dashcamutils import helpers


def test_manual_file_missing(tmp_path):
    s = helpers.Settings(manual_ts_file=tmp_path / "none.txt")
    assert helpers.process_manual_timestamps(s, True) is False


def test_manual_check_only_handles_blank_and_bad_lines(tmp_path, caplog):
    f = tmp_path / "ManualTimestamps.txt"
    f.write_text(
        "a.JPG GARMIN 2021/03/10 21:23:30 41.87074 -87.61696 35 MPH\n"
        "\n"
        "b.JPG GARMIN 2021/03/10 21:23:30\n"
        "c.JPG\n"
    )
    s = helpers.Settings(manual_ts_file=f)
    with caplog.at_level(logging.INFO):
        assert helpers.process_manual_timestamps(s, True) is True
    errors = [r.message for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 2


def test_invalid_stamps_hint_at_repair(caplog):
    for repair, expected in ((False, True), (True, False)):
        caplog.clear()
        settings = helpers.Settings(repair=repair)
        helpers.check_invalid_timestamps_found(settings, True)
        assert any("--repair" in r.message for r in caplog.records) is expected

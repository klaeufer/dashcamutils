import logging

from dashcamutils import helpers


def test_manual_file_missing(tmp_path):
    s = helpers.Settings(manual_ts_file=tmp_path / "none.txt")
    assert helpers.process_manual_timestamps(s, True) == "missing"


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
        assert helpers.process_manual_timestamps(s, True) == "invalid"
    errors = [r.message for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 2


def test_manual_check_only_valid(tmp_path):
    f = tmp_path / "ManualTimestamps.txt"
    f.write_text(
        "a.JPG GARMIN 2021/03/10 21:23:30 41.87074 -87.61696 35 MPH\n",
        encoding="utf-8",
    )
    assert (
        helpers.process_manual_timestamps(helpers.Settings(manual_ts_file=f), True)
        == "valid"
    )


def test_manual_check_only_time_is_opt_in(tmp_path):
    f = tmp_path / "ManualTimestamps.txt"
    f.write_text("a.JPG GARMIN 2021/03/10 21:23:30\n", encoding="utf-8")
    assert helpers.process_manual_timestamps(
        helpers.Settings(manual_ts_file=f), True
    ) == ("invalid")
    assert (
        helpers.process_manual_timestamps(
            helpers.Settings(manual_ts_file=f, allow_time_only_manual=True), True
        )
        == "valid"
    )


def test_process_image_time_only_is_opt_in(tmp_path, monkeypatch):
    image = tmp_path / "a.jpg"
    image.write_bytes(b"not an image")
    monkeypatch.setattr(
        helpers,
        "read_timestamp",
        lambda imagefile, skip_ocr: "GARMIN 2021/03/10 21:23:30",
    )
    monkeypatch.setattr(helpers, "update_metadata", lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, "adjust_image", lambda *args: None)
    strict_report = tmp_path / "StrictInvalid.txt"
    settings = helpers.Settings(invalid_ts_file=strict_report)
    assert helpers.process_image(str(image), settings) is False
    assert strict_report.exists()

    opt_in_report = tmp_path / "OptInInvalid.txt"
    settings = helpers.Settings(invalid_ts_file=opt_in_report)
    assert helpers.process_image(str(image), settings, allow_time_only=True) is True
    assert not opt_in_report.exists()


def test_invalid_stamps_hint_at_repair(caplog):
    for repair, expected in ((False, True), (True, False)):
        caplog.clear()
        settings = helpers.Settings(repair=repair)
        helpers.check_invalid_timestamps_found(settings, True)
        assert any("--repair" in r.message for r in caplog.records) is expected

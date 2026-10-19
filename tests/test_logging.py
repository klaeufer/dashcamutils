import logging

from dashcamutils import helpers


def test_progress_is_written_to_stderr(monkeypatch, capsys):
    helpers._progress("[%d/%d] reading stamps %s", 1, 2, "a.jpg")
    assert capsys.readouterr().err == "[1/2] reading stamps a.jpg\n"


def test_recoverable_timestamp_is_warning(tmp_path, caplog):
    image = tmp_path / "a.jpg"
    image.touch()
    image.with_suffix(".txt").write_text(
        "GARMIN 2021/03/10 21:23:30\n", encoding="utf-8"
    )
    settings = helpers.Settings(invalid_ts_file=tmp_path / "Invalid.txt")
    with caplog.at_level(logging.WARNING):
        assert helpers.process_image(str(image), settings, skip_ocr=True) is False
    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert not any(record.levelno == logging.ERROR for record in caplog.records)

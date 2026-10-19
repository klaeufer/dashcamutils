import argparse
import sys

import pytest

from dashcamutils import tag_images


@pytest.mark.parametrize("value", ["-1", "-10", "1.5", "bad"])
def test_nonnegative_crop_value_rejected(value):
    with pytest.raises(argparse.ArgumentTypeError, match="nonnegative integer"):
        tag_images._nonnegative_int(value)


def test_crop_value_accepts_zero_and_positive():
    assert tag_images._nonnegative_int("0") == 0
    assert tag_images._nonnegative_int("123") == 123


def test_empty_input_exits_before_autofit(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["dashcam-tag"])
    monkeypatch.setattr(
        tag_images.autofit,
        "fit_segments",
        lambda *args: pytest.fail("empty input must not auto-fit"),
    )

    with pytest.raises(SystemExit) as exc:
        tag_images.main()

    assert exc.value.code == 2
    output = capsys.readouterr()
    assert "no images or ManualTimestamps.txt supplied" in output.err
    assert "Example: dashcam-tag" in output.err


def test_existing_manual_file_is_still_processed(tmp_path, monkeypatch):
    (tmp_path / "ManualTimestamps.txt").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["dashcam-tag"])
    monkeypatch.setattr(
        tag_images.helpers,
        "process_manual_timestamps",
        lambda settings, check_only: False,
    )
    monkeypatch.setattr(
        tag_images.autofit,
        "fit_segments",
        lambda *args: [(0, 0, 0.0)],
    )

    tag_images.main()


def test_settings_summary_hides_hemisphere_without_repair(caplog):
    args = argparse.Namespace(crop_bottom=0, angle=0.0, date_order="auto")
    settings = tag_images.helpers.Settings()
    with caplog.at_level("INFO"):
        tag_images._log_settings(args, settings, False)
    messages = [record.message for record in caplog.records]
    assert any("explicit 0px" in message for message in messages)
    assert any("explicit 0°" in message for message in messages)
    assert any("month-first fallback" in message for message in messages)
    assert not any("expected hemisphere" in message for message in messages)


def test_settings_summary_shows_hemisphere_for_repair(caplog):
    args = argparse.Namespace(crop_bottom=None, angle=None, date_order="dmy")
    with caplog.at_level("INFO"):
        tag_images._log_settings(args, tag_images.helpers.Settings(repair=True), False)
    assert any("expected hemisphere: NW" in record.message for record in caplog.records)


def test_settings_summary_reports_time_only_opt_in(caplog):
    args = argparse.Namespace(crop_bottom=0, angle=0.0, date_order="auto")
    settings = tag_images.helpers.Settings(allow_time_only_manual=True)
    with caplog.at_level("INFO"):
        tag_images._log_settings(args, settings, False)
    assert any("manual time-only entries: allowed" in r.message for r in caplog.records)


def test_normal_progress_counts_only_existing_files(tmp_path, monkeypatch, caplog):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.touch()
    second.touch()
    missing = tmp_path / "missing.jpg"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dashcam-tag",
            "-c",
            "0",
            "-r",
            "0",
            str(first),
            str(second),
            str(missing),
        ],
    )
    monkeypatch.setattr(
        tag_images.helpers,
        "process_image",
        lambda imagefile, settings, skip_ocr=False: True,
    )
    with caplog.at_level("INFO"):
        tag_images.main()
    messages = [record.getMessage() for record in caplog.records]
    assert messages.count(f"[1/2] processing {first}") == 1
    assert messages.count(f"[2/2] processing {second}") == 1
    assert any(f"Image file {missing} not found" in message for message in messages)

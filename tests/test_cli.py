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

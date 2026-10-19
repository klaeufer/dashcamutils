import datetime
from zoneinfo import ZoneInfo

import numpy as np
import piexif
import pytest
from PIL import Image, ImageDraw

from dashcamutils import helpers


def _jpeg(path, size=(1280, 1440)):
    Image.new("RGB", size, "gray").save(path, quality=95)


def test_metadata_roundtrip(tmp_path):
    f = tmp_path / "a.jpg"
    _jpeg(f)
    when = datetime.datetime(2021, 3, 10, 21, 23, 30)
    helpers.update_metadata(str(f), when, (41.87074, -87.61696, 35))
    exif = piexif.load(str(f))
    assert exif["Exif"][piexif.ExifIFD.DateTimeOriginal] == b"2021:03:10 21:23:30"
    assert exif["GPS"][piexif.GPSIFD.GPSLatitudeRef] == b"N"
    assert exif["GPS"][piexif.GPSIFD.GPSLongitudeRef] == b"W"
    assert exif["GPS"][piexif.GPSIFD.GPSLatitude][:2] == ((41, 1), (52, 1))
    assert exif["GPS"][piexif.GPSIFD.GPSSpeed] == (35, 1)
    assert f.stat().st_mtime == when.replace(tzinfo=datetime.UTC).timestamp()


def test_adjust_image_crops_and_keeps_exif(tmp_path):
    f = tmp_path / "a.jpg"
    _jpeg(f)
    helpers.update_metadata(str(f), datetime.datetime(2021, 3, 10), (41.0, -87.0, 1))
    helpers.adjust_image(str(f), helpers.Settings(crop_bottom=100, angle=1.5))
    with Image.open(tmp_path / "a-cropped.jpg") as out:
        assert out.size[0] < 1280 and out.size[1] < 1340
        assert out.info.get("exif")


def test_ocr_reads_rendered_text(tmp_path):
    img = Image.new("RGB", (1280, 1440), "black")
    ImageDraw.Draw(img).text(
        (20, 1395), "GARMIN 2021/03/10 21:23:30", fill="white", font_size=36
    )
    f = tmp_path / "a.jpg"
    img.save(f, quality=95)
    line = helpers.read_timestamp(str(f))
    when, _ = helpers.parse_timestamp(line)
    assert when == datetime.datetime(2021, 3, 10, 21, 23, 30)


def test_rotation_leaves_no_empty_corners(tmp_path):
    f = tmp_path / "a.jpg"
    Image.new("RGB", (1280, 1440), (200, 30, 30)).save(f, quality=100)
    helpers.adjust_image(str(f), helpers.Settings(angle=1.4))
    with Image.open(tmp_path / "a-cropped.jpg") as out:
        px = np.asarray(out)
    for corner in (px[0, 0], px[0, -1], px[-1, 0], px[-1, -1]):
        assert corner[0] > 150 and corner[1] < 80 and corner[2] < 80


def test_positive_angle_is_counterclockwise(tmp_path):
    f = tmp_path / "a.jpg"
    img = Image.new("RGB", (400, 400), "white")
    ImageDraw.Draw(img).rectangle((300, 190, 399, 210), fill="black")
    img.save(f, quality=100)
    helpers.adjust_image(str(f), helpers.Settings(angle=10))
    with Image.open(tmp_path / "a-cropped.jpg") as out:
        ys, _ = np.nonzero(np.asarray(out.convert("L")) < 50)
        # the right-hand bar moves up (smaller y) when rotated counterclockwise
        assert ys.mean() < out.height / 2


def test_timezone_written_and_applied(tmp_path):
    f = tmp_path / "a.jpg"
    _jpeg(f)
    when = datetime.datetime(2021, 3, 10, 21, 23, 30)
    chicago = ZoneInfo("America/Chicago")
    helpers.update_metadata(str(f), when, (41.0, -87.0, 1), chicago)
    exif = piexif.load(str(f))
    assert exif["Exif"][piexif.ExifIFD.DateTimeOriginal] == b"2021:03:10 21:23:30"
    assert exif["Exif"][piexif.ExifIFD.OffsetTimeOriginal] == b"-06:00"
    assert exif["GPS"][piexif.GPSIFD.GPSDateStamp] == b"2021:03:11"
    assert exif["GPS"][piexif.GPSIFD.GPSTimeStamp] == ((3, 1), (23, 1), (30, 1))
    assert f.stat().st_mtime == when.replace(tzinfo=chicago).timestamp()


def test_default_timezone_is_utc(tmp_path):
    f = tmp_path / "a.jpg"
    _jpeg(f)
    when = datetime.datetime(2021, 3, 10, 21, 23, 30)
    helpers.update_metadata(str(f), when, (41.0, -87.0, 1))
    exif = piexif.load(str(f))
    assert exif["Exif"][piexif.ExifIFD.OffsetTimeOriginal] == b"+00:00"
    assert exif["GPS"][piexif.GPSIFD.GPSTimeStamp] == ((21, 1), (23, 1), (30, 1))
    assert f.stat().st_mtime == when.replace(tzinfo=datetime.UTC).timestamp()


@pytest.mark.parametrize(
    "name, offset",
    [("UTC", 0), ("-05:00", -300), ("+0530", 330), ("America/Chicago", None)],
)
def test_parse_timezone(name, offset):
    tz = helpers.parse_timezone(name)
    if offset is not None:
        assert tz.utcoffset(None) == datetime.timedelta(minutes=offset)


def test_parse_timezone_rejects_unknown():
    with pytest.raises(ValueError):
        helpers.parse_timezone("Mars/Olympus")

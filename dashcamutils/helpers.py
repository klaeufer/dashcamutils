import datetime
import logging
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import piexif
from PIL import Image

# Region of the 1440p frame containing the Garmin timestamp/GPS overlay
# left, upper, right, lower of the timestamp strip
TS_CROP_BOX = (10, 1385, 10 + 1150, 1385 + 50)


@dataclass
class Settings:
    crop_bottom: int = 0
    angle: float = 0
    manual_ts_file: Path = Path("ManualTimestamps.txt")
    invalid_ts_file: Path = Path("InvalidTimestamps.txt")


_ocr_engine = None


def _ocr(img: Image.Image) -> str:
    """OCR an image with RapidOCR, creating the engine on first use."""
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr import RapidOCR

        _ocr_engine = RapidOCR()
    result = _ocr_engine(np.array(img.convert("RGB")))
    txts = getattr(result, "txts", None)
    return " ".join(txts or ())


def _basename(imagefile: str) -> str:
    return str(Path(imagefile).with_suffix(""))


def check_invalid_timestamps_exist(settings: Settings) -> None:
    if settings.invalid_ts_file.is_file():
        logging.info(
            f"Found existing invalid timestamps in {settings.invalid_ts_file}, "
            "appending if applicable"
        )


def check_invalid_timestamps_found(settings: Settings, found: bool) -> None:
    if found:
        logging.error(
            "Found one or more invalid timestamps, "
            f"please check {settings.invalid_ts_file}"
        )
        logging.error(
            f"Then rename to {settings.manual_ts_file}, fix manually, and rerun"
        )


def read_timestamp(imagefile: str, skip_ocr: bool = False) -> str:
    basename = _basename(imagefile)
    tsfile = basename + "-timestamp.jpg"
    datafile = basename + ".txt"

    if not skip_ocr:
        logging.info(
            f"{basename}: attempting OCR to write timestamp and GPS info to {datafile}"
        )
        try:
            with Image.open(imagefile) as img:
                strip = img.crop(TS_CROP_BOX)
            strip.save(tsfile)
            text = _ocr(strip)
            Path(datafile).write_text(text + "\n", encoding="utf-8")
        except Exception as e:
            logging.error(f"{basename}: OCR failed: {e}")

    logging.info(f"{basename}: reading timestamp and GPS info from {datafile}")
    try:
        with open(datafile, encoding="utf-8") as df:
            return df.readline()
    except OSError as e:
        logging.error(f"{basename}: cannot read {datafile}: {e}")
        return ""


def write_timestamp(imagefile: str, line: str) -> None:
    basename = _basename(imagefile)
    datafile = basename + ".txt"

    with open(datafile, "w", encoding="utf-8") as df:
        df.write(line)
    logging.info(f"{basename}: wrote timestamp back to {datafile}")


# timestamp and GPS format:
#  yyyymmdd GARMIN 2021/03/10 21:23:30 41.87074 -87.61696 35 MPH
#  mmddyyyy GARMIN 10/23/2022 10:31:08 PM 41.87795 -87.62056 26 MPF

invalid_chars = ")—Z+_'°=\"<>}~"

# Define all possible timestamp formats
TS_FORMATS = [
    (
        re.compile(
            "(\\d{4})/(\\d{2})/(\\d{2}).?([012]\\d)[:27 ]{0,2}([012345]\\d)[:27 ]{0,2}([012345]\\d)"
        ),
        "%Y%m%d%H%M%S",
    ),
    (
        re.compile(
            "(\\d{2})/(\\d{2})/(\\d{4}).?([012]\\d)[:27 ]{0,2}([012345]\\d)[:27 ]{0,2}([012345]\\d) (AM|PM)"
        ),
        "%m%d%Y%I%M%S%p",
    ),
    (
        re.compile(
            "(\\d{2})/(\\d{2})/(\\d{4}).?([012]\\d)[:27 ]{0,2}([012345]\\d)[:27 ]{0,2}([012345]\\d)"
        ),
        "%m%d%Y%H%M%S",
    ),
]

gps = re.compile("(\\d{2})[.-]*(\\d{5}).{0,2}-?(\\d{2,3})[.-]*(\\d{5})[. ]*(\\d*)")

type Gps = tuple[float, float, int]


def parse_timestamp(line: str) -> tuple[datetime.datetime | None, Gps | None]:
    for ch in invalid_chars:
        line = line.replace(ch, "")

    g = gps.search(line)
    location: Gps | None = None
    when: datetime.datetime | None = None

    for ts_regex, ts_format in TS_FORMATS:
        t = ts_regex.search(line)
        if not t:
            continue
        try:
            when = datetime.datetime.strptime("".join(t.groups()), ts_format)
        except ValueError:
            continue
        if g is not None:
            try:
                lat = float(g.group(1) + "." + g.group(2))
                lon = -float(g.group(3) + "." + g.group(4))
                speed = int(g.group(5)) if g.group(5) else 0
                location = (lat, lon, speed)
            except ValueError:
                pass
        break

    return (when, location)


def _dms(value: float) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Format an absolute coordinate as EXIF rational degrees/minutes/seconds."""
    value = abs(value)
    deg = int(value)
    minutes = int((value - deg) * 60)
    seconds = round(((value - deg) * 60 - minutes) * 60 * 10000)
    return ((deg, 1), (minutes, 1), (seconds, 10000))


def update_metadata(imagefile: str, when: datetime.datetime, location: Gps) -> None:
    logging.info(f"{imagefile}: tagging with timestamp and GPS metadata")
    lat, lon, speed = location
    try:
        exif = piexif.load(imagefile)
        exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = when.strftime(
            "%Y:%m:%d %H:%M:%S"
        ).encode()
        exif["GPS"].update(
            {
                piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
                piexif.GPSIFD.GPSLatitude: _dms(lat),
                piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
                piexif.GPSIFD.GPSLongitude: _dms(lon),
                piexif.GPSIFD.GPSSpeedRef: b"M",
                piexif.GPSIFD.GPSSpeed: (speed, 1),
            }
        )
        piexif.insert(piexif.dump(exif), imagefile)
        ts = when.timestamp()
        os.utime(imagefile, (ts, ts))
    except Exception as e:
        logging.error(f"{imagefile}: failed to write metadata: {e}")


def _inscribed_box(width: int, height: int, angle: float) -> tuple[int, int, int, int]:
    """Largest centered axis-aligned box lying fully inside a rotated image."""
    rad = math.radians(angle)
    sin_a, cos_a = abs(math.sin(rad)), abs(math.cos(rad))
    long_side, short_side = max(width, height), min(width, height)
    if short_side <= 2 * sin_a * cos_a * long_side or abs(sin_a - cos_a) < 1e-10:
        x = 0.5 * short_side
        w, h = (x / sin_a, x / cos_a) if width >= height else (x / cos_a, x / sin_a)
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        w = (width * cos_a - height * sin_a) / cos_2a
        h = (height * cos_a - width * sin_a) / cos_2a
    left, top = math.ceil((width - w) / 2), math.ceil((height - h) / 2)
    return (left, top, width - left, height - top)


def adjust_image(imagefile: str, settings: Settings) -> None:
    """Rotate counterclockwise by settings.angle degrees (as Image.rotate does).

    Rotating leaves empty wedges in the corners, so the result is cropped to the
    largest box that contains only real image content, then settings.crop_bottom
    pixels are removed from the bottom.
    """
    logging.info(f"{imagefile}: rotating and cropping image")
    try:
        with Image.open(imagefile) as img:
            exif = img.info.get("exif")
            out = img
            box = (0, 0, *img.size)
            if settings.angle:
                out = img.rotate(settings.angle, resample=Image.Resampling.BICUBIC)
                box = _inscribed_box(*img.size, settings.angle)
            left, top, right, bottom = box
            bottom -= settings.crop_bottom
            if bottom <= top:
                raise ValueError("crop_bottom leaves no image")
            out = out.crop((left, top, right, bottom))
            kwargs = {"exif": exif} if exif else {}
            out.save(f"{_basename(imagefile)}-cropped.jpg", quality=95, **kwargs)
    except Exception as e:
        logging.error(f"{imagefile}: failed to adjust image: {e}")


def process_image(imagefile: str, settings: Settings, skip_ocr: bool = False) -> bool:
    """Tag and crop one image. Returns False if its timestamp/GPS was invalid."""
    if not Path(imagefile).is_file():
        logging.warning(f"Image file {imagefile} not found, skipping")
        return True

    line = read_timestamp(imagefile, skip_ocr)
    when, location = parse_timestamp(line)

    if when is None or location is None:
        logging.error(
            f"{imagefile}: invalid or missing timestamp or GPS info {line.rstrip()}, "
            f"writing to {settings.invalid_ts_file}"
        )
        with open(settings.invalid_ts_file, "a", encoding="utf-8") as invalid_ts:
            invalid_ts.write(f"{imagefile} {line.rstrip()}\n")
        return False

    update_metadata(imagefile, when, location)
    adjust_image(imagefile, settings)
    return True


def process_manual_timestamps(settings: Settings, check_only: bool) -> bool:
    """Process the manual timestamps file. Returns False if it doesn't exist."""
    if not settings.manual_ts_file.is_file():
        return False

    logging.warning("Found manual timestamps, processing only the corresponding images")
    with open(settings.manual_ts_file, encoding="utf-8") as manual_ts:
        for raw_line in manual_ts:
            parts = raw_line.split(maxsplit=1)
            if not parts:
                continue
            imagefile = parts[0]
            line = parts[1] if len(parts) > 1 else ""
            when, location = parse_timestamp(line)
            if when is None or location is None:
                logging.error(
                    f"{imagefile}: invalid timestamp or GPS info {line.rstrip()}"
                )
                continue
            logging.info(f"{imagefile}: extracted {when} {location}")
            if check_only:
                continue
            write_timestamp(imagefile, line)
            process_image(imagefile, settings, True)
    return True

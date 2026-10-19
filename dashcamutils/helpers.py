import datetime
import logging
import math
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
import piexif
from PIL import Image, ImageOps

from . import sequence, stamps

# Region of the 1440p frame containing the Garmin timestamp/GPS overlay
# left, upper, right, lower of the timestamp strip
TS_CROP_BOX = (10, 1385, 10 + 1150, 1385 + 50)


type DateOrder = Literal["auto", "mdy", "dmy"]
type ManualResult = Literal["missing", "valid", "invalid"]


@dataclass
class Settings:
    crop_bottom: int = 0
    angle: float = 0
    gps_time_only: bool = True
    # per-image (crop, angle) when the camera moved within the batch
    mounts: dict[str, tuple[int, float]] = field(default_factory=dict)
    # zone the camera clock is set to; stamps carry no zone of their own
    tz: datetime.tzinfo = datetime.UTC
    # how to read ambiguous nn/nn/yyyy dates; "auto" infers it from the batch
    date_order: DateOrder = "auto"
    inferred_order: Literal["mdy", "dmy"] = "mdy"
    manual_ts_file: Path = Path("ManualTimestamps.txt")
    invalid_ts_file: Path = Path("InvalidTimestamps.txt")
    repaired_ts_file: Path = Path("RepairedTimestamps.txt")
    # expected hemisphere pair of the stamps' coordinates, N/S then E/W; the
    # camera prints a minus sign for S and W
    hemisphere: stamps.Hemisphere = "NW"
    # repair unreadable stamps using neighbouring images (batch mode)
    repair: bool = False
    interpolate: bool = True
    # reorder a batch by its readable timestamps instead of trusting list order
    sort_by_time: bool = False


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


def _variants(strip: Image.Image) -> Iterator[Image.Image]:
    """Preprocessings of the stamp strip, tried in turn when OCR misreads it."""
    yield strip
    gray = strip.convert("L")
    yield ImageOps.autocontrast(gray, cutoff=2).convert("RGB")
    binary = gray.point(lambda p: 255 if p > 150 else 0).convert("RGB")
    yield binary
    yield ImageOps.expand(strip, 20, fill=(0, 0, 0))
    yield ImageOps.expand(binary, 20, fill=(0, 0, 0))
    double = gray.resize((gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS)
    yield ImageOps.autocontrast(double, cutoff=2).convert("RGB")


def _ocr_stamp(strip: Image.Image) -> str:
    """OCR the stamp, retrying with other preprocessings until it parses cleanly.

    RapidOCR is erratic on this overlay: a strip it garbles can read perfectly
    after a contrast stretch or padding. The first reading with a full,
    clean-looking stamp wins; otherwise the one needing the least repair does.
    """
    best_text, best_cost = "", float("inf")
    for variant in _variants(strip):
        text = _ocr(variant)
        found = stamps.read_candidates(text)
        cost = found[0].cost if found else float("inf")
        if cost < best_cost or not best_text:
            best_text, best_cost = text, cost
        if best_cost <= sequence.CLEAN_COST:
            break
    return best_text


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
            "Recovery steps: (1) find the failure report; (2) copy its entries "
            f"to {settings.manual_ts_file} and edit them; (3) validate with "
            "dashcam-tag --validity_check_manual; (4) apply valid entries with "
            "dashcam-tag, preserving the same --timezone and other options"
        )
        if not settings.repair:
            logging.error(
                "Or try --repair, which fixes misread stamps from neighbouring "
                "images (list the images in capture order)"
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
            text = _ocr_stamp(strip)
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

# The separators between time fields are often misread by OCR (':' as '2' or '7')
_TIME = r".?([012]\d)[:27 ]{0,2}([012345]\d)[:27 ]{0,2}([012345]\d)"
YMD_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})" + _TIME)
# nn/nn/yyyy is month-first or day-first depending on the camera's setting
SLASH_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})" + _TIME + r"(?: (AM|PM))?")

gps = re.compile("(\\d{2})[.-]*(\\d{5}).{0,2}-?(\\d{2,3})[.-]*(\\d{5})[. ]*(\\d*)")

type Gps = tuple[float, float, int]


def _build(
    year: str, month: str, day: str, hms: tuple[str, ...], ampm: str | None
) -> datetime.datetime | None:
    try:
        if ampm:
            try:
                return datetime.datetime.strptime(
                    f"{year}{month}{day}{''.join(hms)}{ampm}", "%Y%m%d%I%M%S%p"
                )
            except ValueError:
                pass  # e.g. hour 13-23 with a spurious AM/PM
        return datetime.datetime.strptime(
            f"{year}{month}{day}{''.join(hms)}", "%Y%m%d%H%M%S"
        )
    except ValueError:
        return None


def _parse(
    line: str, date_order: DateOrder, prefer: Literal["mdy", "dmy"]
) -> tuple[datetime.datetime | None, Gps | None, Literal["mdy", "dmy"] | None]:
    """Parse a stamp; the last result is the order if the line settled it."""
    for ch in invalid_chars:
        line = line.replace(ch, "")

    when: datetime.datetime | None = None
    settled: Literal["mdy", "dmy"] | None = None

    if t := YMD_RE.search(line):
        when = _build(*t.group(1, 2, 3), t.group(4, 5, 6), None)
    elif t := SLASH_RE.search(line):
        first, second, year = t.group(1, 2, 3)
        hms, ampm = t.group(4, 5, 6), t.group(7)
        candidates: dict[Literal["mdy", "dmy"], datetime.datetime | None] = {
            "mdy": _build(year, first, second, hms, ampm),
            "dmy": _build(year, second, first, hms, ampm),
        }
        valid = [o for o, v in candidates.items() if v is not None]
        order: Literal["mdy", "dmy"] | None
        if date_order != "auto":
            order = date_order
        elif len(valid) == 1:
            order = valid[0]
            settled = order
        else:
            order = prefer
        when = candidates.get(order)

    location: Gps | None = None
    if when is not None and (g := gps.search(line)):
        try:
            lat = float(g.group(1) + "." + g.group(2))
            lon = -float(g.group(3) + "." + g.group(4))
            speed = int(g.group(5)) if g.group(5) else 0
            location = (lat, lon, speed)
        except ValueError:
            pass

    return (when, location, settled)


def parse_timestamp(
    line: str, date_order: DateOrder = "auto", prefer: Literal["mdy", "dmy"] = "mdy"
) -> tuple[datetime.datetime | None, Gps | None]:
    """Parse the OCR'd stamp, detecting its format.

    yyyy/mm/dd is unambiguous. For nn/nn/yyyy, auto mode picks month- or day-first
    when only one reading is a valid date, and otherwise falls back to `prefer`.
    """
    when, location, _ = _parse(line, date_order, prefer)
    return (when, location)


def parse_with_settings(
    line: str, settings: Settings
) -> tuple[datetime.datetime | None, Gps | None]:
    """Like parse_timestamp, but learns the date order across a batch."""
    when, location, settled = _parse(line, settings.date_order, settings.inferred_order)
    if settled and settled != settings.inferred_order:
        logging.info(f"detected {settled} date order from {line.strip()!r}")
        settings.inferred_order = settled
    return (when, location)


def _dms(value: float) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Format an absolute coordinate as EXIF rational degrees/minutes/seconds."""
    value = abs(value)
    deg = int(value)
    minutes = int((value - deg) * 60)
    seconds = round(((value - deg) * 60 - minutes) * 60 * 10000)
    return ((deg, 1), (minutes, 1), (seconds, 10000))


def parse_timezone(name: str) -> datetime.tzinfo:
    """Accept UTC, a fixed offset like +05:30, or an IANA name like America/Chicago."""
    if name.upper() in ("UTC", "Z"):
        return datetime.UTC
    if m := re.fullmatch(r"([+-])(\d{1,2})(?::?(\d{2}))?", name):
        delta = datetime.timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0))
        return datetime.timezone(-delta if m.group(1) == "-" else delta)
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError, OSError) as e:
        raise ValueError(f"unknown time zone {name!r}") from e


def _offset_string(moment: datetime.datetime) -> str:
    offset = moment.utcoffset() or datetime.timedelta(0)
    minutes = int(offset.total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


LOCAL_TIME_EXIF_TAGS = (
    piexif.ExifIFD.DateTimeOriginal,
    piexif.ExifIFD.DateTimeDigitized,
    piexif.ExifIFD.OffsetTime,
    piexif.ExifIFD.OffsetTimeOriginal,
    piexif.ExifIFD.OffsetTimeDigitized,
    piexif.ExifIFD.SubSecTime,
    piexif.ExifIFD.SubSecTimeOriginal,
    piexif.ExifIFD.SubSecTimeDigitized,
)


def update_metadata(
    imagefile: str,
    when: datetime.datetime,
    location: Gps | None,
    tz: datetime.tzinfo = datetime.UTC,
    note: str | None = None,
    gps_time_only: bool = False,
) -> None:
    """Tag the image; `when` is the stamp's wall-clock time in zone `tz`.

    With no `location` only the time is written.

    With `gps_time_only` (and a location) the local-time tags are removed, leaving
    just the UTC GPS date and time, so that Google Photos works out the time zone
    from the position. Without a location they are kept, as there is nothing to
    infer a zone from.

    `note` is stored in UserComment, e.g. to mark values that were estimated.
    """
    logging.info(f"{imagefile}: tagging with timestamp and GPS metadata")
    aware = when.replace(tzinfo=tz)
    utc = aware.astimezone(datetime.UTC)
    try:
        exif = piexif.load(imagefile)
        exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = when.strftime(
            "%Y:%m:%d %H:%M:%S"
        ).encode()
        exif["Exif"][piexif.ExifIFD.OffsetTimeOriginal] = _offset_string(aware).encode()
        exif["GPS"].update(
            {
                piexif.GPSIFD.GPSDateStamp: utc.strftime("%Y:%m:%d").encode(),
                piexif.GPSIFD.GPSTimeStamp: (
                    (utc.hour, 1),
                    (utc.minute, 1),
                    (utc.second, 1),
                ),
            }
        )
        if location is not None:
            lat, lon, speed = location
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
        if gps_time_only and location is not None:
            for tag in LOCAL_TIME_EXIF_TAGS:
                exif["Exif"].pop(tag, None)
            exif["0th"].pop(piexif.ImageIFD.DateTime, None)
        if note:
            exif["Exif"][piexif.ExifIFD.UserComment] = b"ASCII\0\0\0" + note.encode(
                "ascii", "replace"
            )
        piexif.insert(piexif.dump(exif), imagefile)
        ts = aware.timestamp()
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
            crop, angle = settings.mounts.get(
                imagefile, (settings.crop_bottom, settings.angle)
            )
            out = img
            box = (0, 0, *img.size)
            if angle:
                out = img.rotate(angle, resample=Image.Resampling.BICUBIC)
                box = _inscribed_box(*img.size, angle)
            left, top, right, bottom = box
            bottom -= crop
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
    when, location = parse_with_settings(line, settings)

    if when is None or location is None:
        logging.error(
            f"{imagefile}: invalid or missing timestamp or GPS info {line.rstrip()}, "
            f"writing to {settings.invalid_ts_file}"
        )
        with open(settings.invalid_ts_file, "a", encoding="utf-8") as invalid_ts:
            invalid_ts.write(f"{imagefile} {line.rstrip()}\n")
        return False

    update_metadata(
        imagefile, when, location, settings.tz, gps_time_only=settings.gps_time_only
    )
    adjust_image(imagefile, settings)
    return True


def process_batch(
    images: list[str], settings: Settings, skip_ocr: bool = False
) -> bool:
    """Tag and crop a sequence of images, repairing stamps from their neighbours.

    Images must be in capture order. Returns False if any stamp stayed unusable.
    """
    files = [f for f in images if Path(f).is_file()]
    for f in set(images) - set(files):
        logging.warning(f"Image file {f} not found, skipping")

    total = len(files)
    lines = []
    for current, f in enumerate(files, 1):
        logging.info("[%d/%d] OCR-reading %s", current, total, f)
        lines.append(read_timestamp(f, skip_ocr))
    first: stamps.DateFormat = (
        "dmy"
        if settings.date_order == "dmy"
        or (settings.date_order == "auto" and settings.inferred_order == "dmy")
        else "mdy"
    )
    formats: tuple[stamps.DateFormat, ...] = (
        ("ymd", first)
        if settings.date_order != "auto"
        else ("ymd", first, "dmy" if first == "mdy" else "mdy")
    )
    candidates = [
        stamps.read_candidates(line, formats, settings.hemisphere) for line in lines
    ]
    # the camera writes every stamp of a batch in one format, so lock to it
    fmt = stamps.detect_format(candidates)
    if fmt is not None:
        odd = sum(1 for cs in candidates if cs and cs[0].fmt != fmt)
        if odd:
            logging.warning(
                f"{odd} stamps looked like a different date format than the "
                f"batch's {fmt}; ignoring those readings"
            )
        candidates = stamps.only_format(candidates, fmt)
    backwards = sequence.count_out_of_order(candidates)
    if backwards:
        if settings.sort_by_time:
            order = sequence.time_order(candidates)
            logging.warning(
                f"images were out of time order ({backwards} backward steps); sorted by timestamp"
            )
            files = [files[i] for i in order]
            lines = [lines[i] for i in order]
            candidates = [candidates[i] for i in order]
        else:
            logging.warning(
                f"{backwards} readable timestamps run backwards in the image order; "
                "repair assumes capture order, so results may be poor "
                "(use --sort-by-time to reorder by timestamp)"
            )
    resolved = sequence.resolve(candidates, settings.interpolate)

    ok = True
    for current, (f, line, r) in enumerate(
        zip(files, lines, resolved, strict=True), 1
    ):
        logging.info("[%d/%d] writing %s", current, total, f)
        loc = r.location
        if r.when is None:
            logging.error(
                f"{f}: unusable timestamp {line.rstrip()}, "
                f"writing to {settings.invalid_ts_file}"
            )
            with open(settings.invalid_ts_file, "a", encoding="utf-8") as bad:
                bad.write(f"{f} {line.rstrip()}\n")
            ok = False
            continue
        note = None
        if r.status != "ok":
            fixed = f"GARMIN {r.when:%m/%d/%Y %H:%M:%S}"
            if loc is not None:
                fixed += f" {loc[0]:.5f} {loc[1]:.5f} {loc[2]} MPH"
            logging.warning(f"{f}: {r.status}: {line.rstrip()!r} -> {fixed}")
            with open(settings.repaired_ts_file, "a", encoding="utf-8") as audit:
                audit.write(f"{f} {fixed}  # {r.status}, OCR read: {line.rstrip()}\n")
            if r.status == "interpolated":
                note = "dashcamutils: position interpolated from neighbouring images"
        update_metadata(f, r.when, loc, settings.tz, note, settings.gps_time_only)
        adjust_image(f, settings)
    return ok


def manual_timestamp_images(settings: Settings) -> list[str]:
    """Image files named in the manual timestamps file."""
    if not settings.manual_ts_file.is_file():
        return []
    with open(settings.manual_ts_file, encoding="utf-8") as manual_ts:
        return [p[0] for line in manual_ts if (p := line.split(maxsplit=1))]


def process_manual_timestamps(settings: Settings, check_only: bool) -> ManualResult:
    """Process the manual timestamps file and report whether entries are valid."""
    if not settings.manual_ts_file.is_file():
        return "missing"

    logging.warning("Found manual timestamps, processing only the corresponding images")
    invalid = False
    with open(settings.manual_ts_file, encoding="utf-8") as manual_ts:
        for raw_line in manual_ts:
            parts = raw_line.split(maxsplit=1)
            if not parts:
                continue
            imagefile = parts[0]
            line = parts[1] if len(parts) > 1 else ""
            when, location = parse_with_settings(line, settings)
            if when is None or location is None:
                invalid = True
                logging.error(
                    f"{imagefile}: invalid timestamp or GPS info {line.rstrip()}"
                )
                continue
            logging.info(f"{imagefile}: extracted {when} {location}")
            if check_only:
                continue
            write_timestamp(imagefile, line)
            process_image(imagefile, settings, True)
    return "invalid" if invalid else "valid"

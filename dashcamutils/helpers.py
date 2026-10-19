import datetime
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Region of the 1440p frame containing the Garmin timestamp/GPS overlay
TS_CROP_GEOMETRY = "1150x50+10+1385"


@dataclass
class Settings:
    crop_height: int | None = None
    rotation: float = 0
    manual_ts_file: Path = Path("ManualTimestamps.txt")
    invalid_ts_file: Path = Path("InvalidTimestamps.txt")


def _run(cmd: list[str]) -> bool:
    """Run an external tool, logging (not raising) on failure."""
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        logging.error(f"{cmd[0]}: command not found, is it installed?")
    except subprocess.CalledProcessError as e:
        logging.error(f"{cmd[0]}: failed with exit status {e.returncode}")
    else:
        return True
    return False


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
        _run(["magick", imagefile, "-crop", TS_CROP_GEOMETRY, "+repage", tsfile])
        _run(
            [
                "ocrmypdf",
                "--tesseract-oem",
                "3",
                "--tesseract-pagesegmode",
                "7",
                "--image-dpi",
                "300",
                "--sidecar",
                datafile,
                tsfile,
                "/dev/null",
            ]
        )

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


def update_metadata(imagefile: str, when: datetime.datetime, location: Gps) -> None:
    logging.info(f"{imagefile}: tagging with timestamp and GPS metadata")
    stamp = when.strftime("%Y:%m:%d %H:%M:%S")
    lat, lon, speed = location
    # TODO hemisphere EW/NS prefixes: currently assumes N/W
    _run(
        [
            "exiftool",
            "-overwrite_original",
            f"-DateTimeOriginal={stamp}",
            f"-FileModifyDate={stamp}",
            f"-GPSLatitude={lat}",
            "-GPSLatitudeRef=N",
            f"-GPSLongitude={lon}",
            "-GPSLongitudeRef=W",
            f"-GPSSpeed={speed}",
            "-GPSSpeedRef=M",
            imagefile,
        ]
    )


def adjust_image(imagefile: str, settings: Settings) -> None:
    logging.info(f"{imagefile}: rotating and cropping image")
    _run(
        [
            "magick",
            imagefile,
            "-distort",
            "ScaleRotateTranslate",
            f"{settings.rotation}",
            "-crop",
            f"+0-{settings.crop_height or 0}",
            "+repage",
            f"{_basename(imagefile)}-cropped.jpg",
        ]
    )


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

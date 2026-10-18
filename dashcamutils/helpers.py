import datetime
import logging
import os
import re
import subprocess

ROTATION: float = 0
CROP: int | None = None
FILENAME_MANUAL_TS: str = "ManualTimestamps.txt"
FILENAME_INVALID_TS: str = "InvalidTimestamps.txt"


def check_invalid_timestamps_exist() -> None:
    if os.path.isfile(FILENAME_INVALID_TS):
        logging.info(
            f"Found existing invalid timestamps in {FILENAME_INVALID_TS}, appending if applicable"
        )


def check_invalid_timestamps_found() -> None:
    if found_invalid_timestamps:
        logging.error(
            f"Found one or more invalid timestamps, please check {FILENAME_INVALID_TS}"
        )
        logging.error(f"Then rename to {FILENAME_MANUAL_TS}, fix manually, and rerun")


def read_timestamp(imagefile: str, skip_ocr: bool = False) -> str:
    basename = imagefile.split(".JPG")[0]
    tsfile = basename + "-timestamp.jpg"
    datafile = basename + ".txt"

    if not skip_ocr:
        logging.info(
            f"{basename}: attempting OCR to write timestamp and GPS info to {datafile}"
        )
        subprocess.run(
            f"magick {imagefile} -crop 1150x50+10+1385 +repage {tsfile}".split()
        )
        subprocess.run(
            f"ocrmypdf --tesseract-oem 3 --tesseract-pagesegmode 7 --image-dpi 300 --sidecar {datafile} {tsfile} /dev/null".split()
        )

    logging.info(f"{basename}: reading timestamp and GPS info from {datafile}")
    with open(datafile) as df:
        return df.readline()


def write_timestamp(imagefile: str, line: str) -> None:
    basename = imagefile.split(".JPG")[0]
    datafile = basename + ".txt"

    with open(datafile, "w") as df:
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


# String -> (String?, (Float, Float, Int)?)
def parse_timestamp(line):
    for ch in invalid_chars:
        line = line.replace(ch, "")

    g = gps.search(line)

    d = None
    l = None

    # Try each timestamp format
    for ts_regex, ts_format in TS_FORMATS:
        t = ts_regex.search(line)
        if t:
            try:
                d = datetime.datetime.strptime("".join(t.groups()), ts_format)
                # Successfully parsed timestamp, now try GPS
                try:
                    if g is None:
                        raise ValueError("no GPS info")
                    lat = float(g.group(1) + "." + g.group(2))
                    lon = -float(g.group(3) + "." + g.group(4))
                    try:
                        speed = int(g.group(5))
                    except:
                        speed = 0
                    l = (lat, lon, speed)
                except:
                    pass
                break  # Successfully parsed timestamp, exit loop
            except:
                continue  # Try next format

    return (d, l)


def update_metadata(imagefile, data):
    (d, l) = data
    try:
        if d:
            logging.info(f"{imagefile}: tagging with timestamp")
            subprocess.run(["touch", "-d", f"{d}", f"{imagefile}"])
            subprocess.run(
                ["exiftool", "-datetimeoriginal<filemodifydate", f"{imagefile}"]
            )
        if l:
            logging.info(f"{imagefile}: tagging with GPS metadata")
            (lat, lon, speed) = l
            subprocess.run(
                f"exiftool -GPSLatitude={lat} -GPSLatitudeRef=N -GPSLongitude={lon} -GPSLongitudeRef=W -GPSSpeed={speed} -GPSSpeedRef=M {imagefile}".split()
            )
    except:
        logging.error(f"{imagefile}: error running Exiftool")


def adjust_image(imagefile):
    try:
        logging.info(f"{imagefile}: rotating and cropping image")
        basename = imagefile.split(".JPG")[0]
        subprocess.run(
            f"magick {imagefile} -distort ScaleRotateTranslate {ROTATION} -crop +0-{CROP} +repage {basename}-cropped.jpg".split()
        )
    except:
        logging.error(f"{imagefile}: error running ImageMagick convert")


found_invalid_timestamps = False


def process_image(imagefile: str, skip_ocr: bool = False) -> None:
    global found_invalid_timestamps

    if not os.path.isfile(imagefile):
        logging.warning(f"Image file {imagefile} not found, skipping")
        return

    line = read_timestamp(imagefile, skip_ocr)
    (d, l) = parse_timestamp(line)

    if not d or not l:
        found_invalid_timestamps = True
        logging.error(
            f"{imagefile}: invalid or missing timestamp or GPS info {line}, writing to {FILENAME_INVALID_TS}"
        )
        with open(FILENAME_INVALID_TS, "a") as invalid_ts:
            invalid_ts.write(f"{imagefile} {line}\n")

    update_metadata(imagefile, (d, l))
    adjust_image(imagefile)


def process_manual_timestamps(check_only: bool) -> None:
    if os.path.isfile(FILENAME_MANUAL_TS):
        logging.warning(
            "Found manual timestamps, processing only the corresponding images"
        )
        with open(FILENAME_MANUAL_TS) as manual_ts:
            for raw_line in manual_ts:
                [imagefile, line] = raw_line.split(maxsplit=1)
                try:
                    (d, (lat, lon, speed)) = parse_timestamp(line)
                    logging.info(f"{imagefile}: extracted {d} {lat} {lon} {speed}")
                    if check_only:
                        continue
                    write_timestamp(imagefile, line)
                    process_image(imagefile, True)
                except:
                    logging.error(
                        f"{imagefile}: invalid timestamp or GPS info {line.rstrip()}"
                    )
        exit(2)

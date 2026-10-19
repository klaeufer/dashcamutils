#!/usr/bin/env python

import argparse
import datetime
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from . import autofit, helpers


def _timezone(name: str) -> datetime.tzinfo:
    try:
        return helpers.parse_timezone(name)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def _auto_or[T](convert: Callable[[str], T]) -> Callable[[str], T | None]:
    def parse(value: str) -> T | None:
        return None if value.lower() == "auto" else convert(value)

    return parse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--crop-bottom",
        "--crop_height",
        dest="crop_bottom",
        help="pixels to crop from the bottom (e.g., the hood), or auto (default) "
        "to detect the hood from the whole batch",
        type=_auto_or(int),
        default=None,
    )
    parser.add_argument(
        "-r",
        "--angle",
        "--rotation_angle",
        dest="angle",
        help="rotation in degrees counterclockwise, as in PIL.Image.rotate, or "
        "auto (default) to estimate the camera tilt from the whole batch",
        type=_auto_or(float),
        default=None,
    )
    parser.add_argument(
        "-z",
        "--timezone",
        help="time zone the camera clock is set to: UTC (default), an offset "
        "like -05:00, or a name like America/Chicago",
        type=_timezone,
        default=datetime.UTC,
    )
    parser.add_argument(
        "-d",
        "--date-order",
        help="how to read ambiguous nn/nn/yyyy dates; auto (default) infers it "
        "from unambiguous stamps, e.g. 23/10/2022",
        choices=["auto", "mdy", "dmy"],
        default="auto",
    )
    parser.add_argument(
        "--hemisphere",
        help="expected hemispheres of the coordinates, latitude then longitude "
        "(NW default; the camera prints '-' for S and W); used by --repair to "
        "judge signs",
        choices=["NW", "NE", "SW", "SE"],
        default="NW",
    )
    parser.add_argument(
        "--repair",
        help="repair misread stamps by fuzzy parsing and checking them against "
        "neighbouring images (images must be in capture order); repairs are "
        "listed in RepairedTimestamps.txt",
        action="store_true",
    )
    parser.add_argument(
        "--interpolate",
        help="with --repair, estimate the position of images whose GPS can't be "
        "read from neighbouring images (default); otherwise, or when the "
        "neighbours are too far apart in time, the position is left blank and "
        "only the time is tagged",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--sort-by-time",
        help="with --repair, process images in the order of their readable "
        "timestamps rather than the order given",
        action="store_true",
    )
    parser.add_argument(
        "-s",
        "--skip_ocr",
        help="skip extraction of timestamp using OCR",
        action="store_true",
    )
    parser.add_argument(
        "-v",
        "--validity_check_manual",
        help="check validity of manual timestamps",
        action="store_true",
    )
    parser.add_argument("--verbose", help="enable debug logging", action="store_true")
    parser.add_argument("image", help="images to process", nargs="*")

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    logging.debug(args)

    settings = helpers.Settings(
        crop_bottom=args.crop_bottom or 0,
        angle=args.angle or 0.0,
        tz=args.timezone,
        date_order=args.date_order,
        hemisphere=args.hemisphere,
        repair=args.repair,
        interpolate=args.interpolate,
        sort_by_time=args.sort_by_time,
    )

    if not args.validity_check_manual and (
        args.crop_bottom is None or args.angle is None
    ):
        images = args.image or helpers.manual_timestamp_images(settings)
        found = [f for f in images if Path(f).is_file()]
        stretches = autofit.fit_segments(found, args.crop_bottom, args.angle)
        _, settings.crop_bottom, settings.angle = stretches[0]
        if len(stretches) > 1:
            ends = [s[0] for s in stretches[1:]] + [len(found)]
            for (first, c, a), end in zip(stretches, ends, strict=True):
                for f in found[first:end]:
                    settings.mounts[f] = (c, a)

    if not args.image:
        if helpers.process_manual_timestamps(settings, args.validity_check_manual):
            sys.exit(2)
        return

    helpers.check_invalid_timestamps_exist(settings)
    if settings.repair:
        found_invalid = not helpers.process_batch(args.image, settings, args.skip_ocr)
    else:
        found_invalid = False
        for imagefile in args.image:
            if not helpers.process_image(imagefile, settings, args.skip_ocr):
                found_invalid = True
    helpers.check_invalid_timestamps_found(settings, found_invalid)
    if found_invalid:
        sys.exit(1)


# ROTATION = 1.4
# CROP = 256 # 1080
# CROP = 365 # 1440

# TODO command-line option for original image resolution - or detect automatically?
# 1080
#    subprocess.run(f'convert -crop 1150x35+10+1035 +repage {imagefile} {tsfile}'.split())
# 1440

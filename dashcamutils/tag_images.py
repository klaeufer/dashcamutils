#!/usr/bin/env python

import argparse
import datetime
import logging
import sys

from . import helpers


def _timezone(name: str) -> datetime.tzinfo:
    try:
        return helpers.parse_timezone(name)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--crop-bottom",
        "--crop_height",
        dest="crop_bottom",
        help="pixels to crop from the bottom (e.g., the hood)",
        type=int,
    )
    parser.add_argument(
        "-r",
        "--angle",
        "--rotation_angle",
        dest="angle",
        help="rotation in degrees counterclockwise, as in PIL.Image.rotate",
        type=float,
        default=0,
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

    # Make -c required unless -v is specified
    if not args.validity_check_manual and args.crop_bottom is None:
        parser.error(
            "-c/--crop-bottom is required unless -v/--validity_check_manual is specified"
        )

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    logging.debug(args)

    settings = helpers.Settings(
        crop_bottom=args.crop_bottom or 0,
        angle=args.angle,
        tz=args.timezone,
        date_order=args.date_order,
    )

    if not args.image:
        if helpers.process_manual_timestamps(settings, args.validity_check_manual):
            sys.exit(2)
        return

    helpers.check_invalid_timestamps_exist(settings)
    found_invalid = False
    for imagefile in args.image:
        if not helpers.process_image(imagefile, settings, args.skip_ocr):
            found_invalid = True
    helpers.check_invalid_timestamps_found(settings, found_invalid)
    if found_invalid:
        sys.exit(1)


# TODO hemisphere EW/NS prefixes

# ROTATION = 1.4
# CROP = 256 # 1080
# CROP = 365 # 1440

# TODO command-line option for original image resolution - or detect automatically?
# 1080
#    subprocess.run(f'convert -crop 1150x35+10+1035 +repage {imagefile} {tsfile}'.split())
# 1440

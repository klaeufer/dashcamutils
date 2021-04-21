#!/usr/bin/env python

import argparse
import logging
import os

import helpers

parser = argparse.ArgumentParser()
parser.add_argument("-s", "--skip_ocr", help="skip extraction of timestamp using OCR", action="store_true")
parser.add_argument("-r", "--rotation_angle", help="image rotation angle", type=float, nargs='?', default=1.4)
parser.add_argument("-c", "--crop_height", help="height of hood section to be cropped in pixels", nargs='?', type=int, default=365)
parser.add_argument("images", help="images to process", nargs='*')
args = parser.parse_args()

logging.basicConfig(level=logging.DEBUG)
logging.info(args)

FILENAME_MANUAL_TS = "ManualTimestamps.txt"
FILENAME_INVALID_TS = "InvalidTimestamps.txt"

helpers.ROTATION = args.rotation_angle
helpers.CROP = args.crop_height
helpers.FILENAME_MANUAL_TS = FILENAME_MANUAL_TS
helpers.FILENAME_INVALID_TS = FILENAME_INVALID_TS
helpers.found_invalid_timestamps = False

# ROTATION = 1.4
# CROP = 256 # 1080
# CROP = 365 # 1440

# TODO hemisphere EW/NS prefixes

if os.path.isfile(FILENAME_INVALID_TS):
    logging.warning(f'Found existing invalid timestamps in {FILENAME_INVALID_TS}, appending')

if os.path.isfile(FILENAME_MANUAL_TS):
    logging.warning('Found manual timestamps, processing only the corresponding images')
    helpers.process_manual_timestamps()
    exit(2)

for imagefile in args.images:
    helpers.process_image(imagefile)

if helpers.found_invalid_timestamps:
    logging.error(f'Found one or more invalid timestamps, please check {FILENAME_INVALID_TS}')
    logging.error(f'Then rename to {FILENAME_MANUAL_TS}, fix manually, and rerun')

# TODO command-line option for original image resolution - or detect automatically?

# 1080
#    subprocess.run(f'convert -crop 1150x35+10+1035 +repage {imagefile} {tsfile}'.split())
# 1440
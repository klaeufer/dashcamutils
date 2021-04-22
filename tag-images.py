#!/usr/bin/env python

import argparse
import logging

import helpers

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--crop_height", help="height of hood section to be cropped in pixels", nargs='?', type=int, default=365)
parser.add_argument("-r", "--rotation_angle", help="image rotation angle", type=float, nargs='?', default=1.4)
parser.add_argument("-s", "--skip_ocr", help="skip extraction of timestamp using OCR", action="store_true")
parser.add_argument("-v", "--validity_check_manual", help="check validity of manual timestamps", action="store_true")
parser.add_argument("images", help="images to process", nargs='*')
args = parser.parse_args()

logging.basicConfig(level=logging.DEBUG)
logging.info(args)

helpers.ROTATION = args.rotation_angle
helpers.CROP = args.crop_height
helpers.FILENAME_MANUAL_TS = "ManualTimestamps.txt"
helpers.FILENAME_INVALID_TS = "InvalidTimestamps.txt"

helpers.check_invalid_timestamps_exist()
helpers.process_manual_timestamps(args.validity_check_manual)

for imagefile in args.images:
    helpers.process_image(imagefile)

helpers.check_invalid_timestamps_found()

# TODO hemisphere EW/NS prefixes

# ROTATION = 1.4
# CROP = 256 # 1080
# CROP = 365 # 1440

# TODO command-line option for original image resolution - or detect automatically?
# 1080
#    subprocess.run(f'convert -crop 1150x35+10+1035 +repage {imagefile} {tsfile}'.split())
# 1440
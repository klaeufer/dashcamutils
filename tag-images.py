#!/usr/bin/env python

import argparse
import logging
import os
import sys
import subprocess
import re
from datetime import datetime
import exif

parser = argparse.ArgumentParser()
parser.add_argument("-s", "--skip_ocr", help="skip extraction of timestamp using OCR", action="store_true")
parser.add_argument("-r", "--rotation_angle", help="image rotation angle", type=float, nargs='?', default=1.4)
parser.add_argument("-c", "--crop_height", help="height of hood section to be cropped in pixels", nargs='?', type=int, default=365)
parser.add_argument("images", help="images to process", nargs='*')
args = parser.parse_args()

logging.basicConfig(level=logging.DEBUG)
logging.info(args)

ROTATION = args.rotation_angle
CROP = args.crop_height
FILENAME_MANUAL_TS = "ManualTimestamps.txt"
FILENAME_INVALID_TS = "InvalidTimestamps.txt"

# ROTATION = 1.4
# CROP = 256 # 1080
# CROP = 365 # 1440

# TODO command line options for running only some of the stages
# TODO hemisphere EW/NS prefixes

invalid_chars = ')—Z+_\'°=\"<>}~'
ts = re.compile('(\d{4})/(\d{2})/(\d{2}).?([012]\d)[:27 ]{0,2}([012345]\d)[:27 ]{0,2}([012345]\d)')
gps = re.compile('(\d{2})[.-]*(\d{5}).{0,2}-?(\d{2})[.-]*(\d{5})[. ]*(\d*)')

def process_image(imagefile):
    basename = imagefile.split('.JPG')[0]
    tsfile = basename + '-timestamp.jpg'
    datafile = basename + '.txt'

    if not args.skip_ocr:
        subprocess.run(f'convert -crop 1150x50+10+1385 +repage {imagefile} {tsfile}'.split())
        subprocess.run(f'ocrmypdf --tesseract-oem 3 --tesseract-pagesegmode 7 --image-dpi 300 --sidecar {datafile} {tsfile} /dev/null'.split())

    line = open(datafile, 'r').readline()
    for ch in invalid_chars:
        line = line.replace(ch, "")
    t = ts.search(line)
    g = gps.search(line)
    if not t:
        logging.warning(f'{basename}: invalid timestamp {t}')
        return
    if not g:
        logging.warning(f'{basename}: invalid GPS info {g}')
        return
    try:
        d = datetime.strptime(''.join(t.groups()), '%Y%m%d%H%M%S')
        lat = float(g.group(1) + '.' + g.group(2))
        lon = -float(g.group(3) + '.' + g.group(4))
        try:
            speed = int(g.group(5))
        except:
            speed = 0
        logging.info(f'{basename}: extracted {d} {lat} {lon} {speed}')

        subprocess.run(['touch', '-d', f'{d}', f'{imagefile}'])
        subprocess.run(['exiftool', '-datetimeoriginal<filemodifydate', f'{imagefile}'])
        subprocess.run(f'exiftool -GPSLatitude={lat} -GPSLatitudeRef=N -GPSLongitude={lon} -GPSLongitudeRef=W -GPSSpeed={speed} -GPSSpeedRef=M {imagefile}'.split())
        subprocess.run(f'convert -distort ScaleRotateTranslate {ROTATION} -crop +0-{CROP} +repage {imagefile} {basename}-cropped.jpg'.split())

    except:
        logging.warning('Other error with Exiftool or ImageMagick convert')


if os.path.isfile(FILENAME_MANUAL_TS):
    logging.info("Found manual timestamps")
    sys.exit(77)

for arg in args.images:
    process_image(arg)

# TODO command-line option for original image resolution

# 1080
#    subprocess.run(f'convert -crop 1150x35+10+1035 +repage {imagefile} {tsfile}'.split())
# 1440
#!/usr/bin/env python

import logging
import os
import subprocess
import re
import datetime
import exif
import pytesseract

def check_invalid_timestamps_exist():
    if os.path.isfile(FILENAME_INVALID_TS):
        logging.warning(f'Found existing invalid timestamps in {FILENAME_INVALID_TS}, appending')

def check_invalid_timestamps_found():
    if found_invalid_timestamps:
        logging.error(f'Found one or more invalid timestamps, please check {FILENAME_INVALID_TS}')
        logging.error(f'Then rename to {FILENAME_MANUAL_TS}, fix manually, and rerun')

def read_timestamp(imagefile, skip_ocr=False):
    basename = imagefile.split('.JPG')[0]
    tsfile = basename + '-timestamp.jpg'
    datafile = basename + '.txt'

    if not skip_ocr:
        logging.info(f'{basename}: using OCR to write timestamp and GPS info using OCR to {datafile}')
        subprocess.run(f'convert -crop 1150x50+10+1385 +repage {imagefile} {tsfile}'.split())
        subprocess.run(f'ocrmypdf --tesseract-oem 3 --tesseract-pagesegmode 7 --image-dpi 300 --sidecar {datafile} {tsfile} /dev/null'.split())

    logging.info(f'{basename}: reading timestamp and GPS info from {datafile}')
    with open(datafile, 'r') as df:
        return df.readline()

def write_timestamp(imagefile, line):
    basename = imagefile.split('.JPG')[0]
    datafile = basename + '.txt'

    with open(datafile, 'w') as df:
        df.write(line)
    logging.info(f'{basename}: wrote timestamp back to {datafile}')

# timestamp and GPS format: GARMIN 2021/03/10 21:23:30 41.87074 -87.61696 35 MPH

invalid_chars = ')—Z+_\'°=\"<>}~'
ts = re.compile('(\d{4})/(\d{2})/(\d{2}).?([012]\d)[:27 ]{0,2}([012345]\d)[:27 ]{0,2}([012345]\d)')
gps = re.compile('(\d{2})[.-]*(\d{5}).{0,2}-?(\d{2})[.-]*(\d{5})[. ]*(\d*)')

def parse_timestamp(line):
    for ch in invalid_chars:
        line = line.replace(ch, "")
    t = ts.search(line)
    g = gps.search(line)
    try:
        d = datetime.datetime.strptime(''.join(t.groups()), '%Y%m%d%H%M%S')
        lat = float(g.group(1) + '.' + g.group(2))
        lon = -float(g.group(3) + '.' + g.group(4))
        try:
            speed = int(g.group(5))
        except:
            speed = 0
        return (d, lat, lon, speed)
    except:
        return None

def update_metadata(imagefile, data):
    logging.info(f'{imagefile}: tagging with timestamp and GPS metadata')
    (d, lat, lon, speed) = data
    subprocess.run(['touch', '-d', f'{d}', f'{imagefile}'])
    subprocess.run(['exiftool', '-datetimeoriginal<filemodifydate', f'{imagefile}'])
    subprocess.run(f'exiftool -GPSLatitude={lat} -GPSLatitudeRef=N -GPSLongitude={lon} -GPSLongitudeRef=W -GPSSpeed={speed} -GPSSpeedRef=M {imagefile}'.split())

def adjust_image(imagefile):
    logging.info(f'{imagefile}: rotating and cropping image')
    basename = imagefile.split('.JPG')[0]
    subprocess.run(f'convert -distort ScaleRotateTranslate {ROTATION} -crop +0-{CROP} +repage {imagefile} {basename}-cropped.jpg'.split())

found_invalid_timestamps = False

def process_image(imagefile, skip_ocr=False):
    global found_invalid_timestamps

    if not os.path.isfile(imagefile):
        logging.warning(f'Image file {imagefile} not found, skipping')
        return

    line = read_timestamp(imagefile, skip_ocr)
    data = parse_timestamp(line)

    if not data:
        found_invalid_timestamps = True
        logging.error(f'{imagefile}: invalid timestamp or GPS info {line}, writing to {FILENAME_INVALID_TS}')
        with open(FILENAME_INVALID_TS, "a") as invalid_ts:
            invalid_ts.write(f'{imagefile} {line}')
        return

    try:
        (d, lat, lon, speed) = data
        update_metadata(imagefile, data)
        adjust_image(imagefile)
    except:
        logging.error(f'{imagefile}: error running Exiftool or ImageMagick convert')

def process_manual_timestamps(check_only):
    if os.path.isfile(FILENAME_MANUAL_TS):
        logging.warning('Found manual timestamps, processing only the corresponding images')
        with open(FILENAME_MANUAL_TS, "r") as manual_ts:
            for raw_line in manual_ts:
                [imagefile, line] = raw_line.split(maxsplit=1)
                try:
                    (d, lat, lon, speed) = parse_timestamp(line)
                    logging.info(f'{imagefile}: extracted {d} {lat} {lon} {speed}')
                    if check_only:
                        continue
                    write_timestamp(imagefile, line)
                    process_image(imagefile, True)
                except:
                    logging.error(f'{imagefile}: invalid timestamp or GPS info {line}')
        exit(2)

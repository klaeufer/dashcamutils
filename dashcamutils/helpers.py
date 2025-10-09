import logging
import os
import subprocess
import re
import datetime

def check_invalid_timestamps_exist():
    if os.path.isfile(FILENAME_INVALID_TS):
        logging.info(f'Found existing invalid timestamps in {FILENAME_INVALID_TS}, appending if applicable')

def check_invalid_timestamps_found():
    if found_invalid_timestamps:
        logging.error(f'Found one or more invalid timestamps, please check {FILENAME_INVALID_TS}')
        logging.error(f'Then rename to {FILENAME_MANUAL_TS}, fix manually, and rerun')

def read_timestamp(imagefile, skip_ocr=False):
    basename = imagefile.split('.JPG')[0]
    tsfile = basename + '-timestamp.jpg'
    datafile = basename + '.txt'

    if not skip_ocr:
        logging.info(f'{basename}: attempting OCR to write timestamp and GPS info to {datafile}')
        subprocess.run(f'magick {imagefile} -crop 1150x50+10+1385 +repage {tsfile}'.split())
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

# timestamp and GPS format:
#  yyyymmdd GARMIN 2021/03/10 21:23:30 41.87074 -87.61696 35 MPH
#  mmddyyyy GARMIN 10/23/2022 10:31:08 PM 41.87795 -87.62056 26 MPF

invalid_chars = ')—Z+_\'°=\"<>}~'
yyyymmdd =    re.compile('(\\d{4})/(\\d{2})/(\\d{2}).?([012]\\d)[:27 ]{0,2}([012345]\\d)[:27 ]{0,2}([012345]\\d)')
mmddyyyy =    re.compile('(\\d{2})/(\\d{2})/(\\d{4}).?([012]\\d)[:27 ]{0,2}([012345]\\d)[:27 ]{0,2}([012345]\\d) (AM|PM)')
mmddyyyy24h = re.compile('(\\d{2})/(\\d{2})/(\\d{4}).?([012]\\d)[:27 ]{0,2}([012345]\\d)[:27 ]{0,2}([012345]\\d)')
# 1) CHOOSE TS format here
#ts = yyyymmdd
#ts = mmddyyyy
ts = mmddyyyy24h
gps = re.compile('(\\d{2})[.-]*(\\d{5}).{0,2}-?(\\d{2,3})[.-]*(\\d{5})[. ]*(\\d*)')

# String -> (String?, (Float, Float, Int)?)
def parse_timestamp(line):
    for ch in invalid_chars:
        line = line.replace(ch, "")
    t = ts.search(line)
    g = gps.search(line)

    d = None
    l = None

    # attempt to parse GPS data only if time/date stamp is valid
    try:
# 2) CHOOSE HERE BASED ON TS FORMAT        
#        d = datetime.datetime.strptime(''.join(t.groups()), '%Y%m%d%H%M%S')
#        d = datetime.datetime.strptime(''.join(t.groups()), '%m%d%Y%I%M%S%p')
        d = datetime.datetime.strptime(''.join(t.groups()), '%m%d%Y%H%M%S')
        try:
            lat = float(g.group(1) + '.' + g.group(2))
            lon = -float(g.group(3) + '.' + g.group(4))
            try:
                speed = int(g.group(5))
            except:
                speed = 0
            l = (lat, lon, speed)
        except:
            pass
    except:
        pass

    return (d, l)

def update_metadata(imagefile, data):
    (d, l) = data
    try:
        if d:
            logging.info(f'{imagefile}: tagging with timestamp')
            subprocess.run(['touch', '-d', f'{d}', f'{imagefile}'])
            subprocess.run(['exiftool', '-datetimeoriginal<filemodifydate', f'{imagefile}'])
        if l:
            logging.info(f'{imagefile}: tagging with GPS metadata')
            (lat, lon, speed) = l
            subprocess.run(f'exiftool -GPSLatitude={lat} -GPSLatitudeRef=N -GPSLongitude={lon} -GPSLongitudeRef=W -GPSSpeed={speed} -GPSSpeedRef=M {imagefile}'.split())
    except:
        logging.error(f'{imagefile}: error running Exiftool')

def adjust_image(imagefile):
    try:
        logging.info(f'{imagefile}: rotating and cropping image')
        basename = imagefile.split('.JPG')[0]
        subprocess.run(f'magick {imagefile} -distort ScaleRotateTranslate {ROTATION} -crop +0-{CROP} +repage {basename}-cropped.jpg'.split())
    except:
        logging.error(f'{imagefile}: error running ImageMagick convert')

found_invalid_timestamps = False

def process_image(imagefile, skip_ocr=False):
    global found_invalid_timestamps

    if not os.path.isfile(imagefile):
        logging.warning(f'Image file {imagefile} not found, skipping')
        return

    line = read_timestamp(imagefile, skip_ocr)
    (d, l) = parse_timestamp(line)

    if not d or not l:
        found_invalid_timestamps = True
        logging.error(f'{imagefile}: invalid or missing timestamp or GPS info {line}, writing to {FILENAME_INVALID_TS}')
        with open(FILENAME_INVALID_TS, "a") as invalid_ts:
            invalid_ts.write(f'{imagefile} {line}')

    update_metadata(imagefile, (d, l))
    adjust_image(imagefile)

def process_manual_timestamps(check_only):
    if os.path.isfile(FILENAME_MANUAL_TS):
        logging.warning('Found manual timestamps, processing only the corresponding images')
        with open(FILENAME_MANUAL_TS, "r") as manual_ts:
            for raw_line in manual_ts:
                [imagefile, line] = raw_line.split(maxsplit=1)
                try:
                    (d, (lat, lon, speed)) = parse_timestamp(line)
                    logging.info(f'{imagefile}: extracted {d} {lat} {lon} {speed}')
                    if check_only:
                        continue
                    write_timestamp(imagefile, line)
                    process_image(imagefile, True)
                except:
                    logging.error(f'{imagefile}: invalid timestamp or GPS info {line.rstrip()}')
        exit(2)

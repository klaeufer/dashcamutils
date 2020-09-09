#!/usr/bin/env python

import sys
import subprocess
import re
from datetime import datetime
import exif


ROTATION = 1
#CROP = 256 # 1080
CROP = 365 # 1440


# TODO command line options for running only some of the stages
# TODO hemisphere EW/NS prefixes

invalid_chars = ')—Z+_\'°=\"<>}~'
ts = re.compile('(\d{4})/(\d{2})/(\d{2}).?([012]\d)[:27 ]{0,2}([012345]\d)[:27 ]{0,2}([012345]\d)')
gps = re.compile('(\d{2})[.-]*(\d{5}).{0,2}-?(\d{2})[.-]*(\d{5})[. ]*(\d*)')

for arg in sys.argv[1:]:

    imagefile = arg
    basename = imagefile.split('.JPG')[0]
    tsfile = basename + '-timestamp.jpg'
    datafile = basename + '.txt'

# 1080
#    subprocess.run(f'convert -crop 1150x35+10+1035 +repage {imagefile} {tsfile}'.split())
# 1440
#    subprocess.run(f'convert -crop 1150x50+10+1385 +repage {imagefile} {tsfile}'.split())
#    subprocess.run(f'ocrmypdf --tesseract-oem 3 --tesseract-pagesegmode 7 --image-dpi 300 --sidecar {datafile} {tsfile} /dev/null'.split())

    line = open(datafile, 'r').readline()
    for ch in invalid_chars:
        line = line.replace(ch, "")
    t = ts.search(line)
    g = gps.search(line)
    print(basename, end=': ')
    if not t:
        print(line, 'INVALID TIMESTAMP')
        continue
    if not g:
        print(line, 'INVALID GPS INFO')
        continue
    try:
        d = datetime.strptime(''.join(t.groups()), '%Y%m%d%H%M%S')
        lat = float(g.group(1) + '.' + g.group(2))
        lon = -float(g.group(3) + '.' + g.group(4))
        try:
            speed = int(g.group(5))
        except:
            speed = 0
        print(d, lat, lon, speed)

        subprocess.run(['touch', '-d', f'{d}', f'{imagefile}'])
        subprocess.run(['exiftool', '-datetimeoriginal<filemodifydate', f'{imagefile}'])
        subprocess.run(f'exiftool -GPSLatitude={lat} -GPSLatitudeRef=N -GPSLongitude={lon} -GPSLongitudeRef=W -GPSSpeed={speed} -GPSSpeedRef=M {imagefile}'.split())
        subprocess.run(f'convert -distort ScaleRotateTranslate {ROTATION} -crop +0-{CROP} +repage {imagefile} {basename}-cropped.jpg'.split())

    except:
        print(line, 'INVALID TIMESTAMP')

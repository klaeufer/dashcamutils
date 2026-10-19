[![CI](https://github.com/klaeufer/dashcamutils/actions/workflows/ci.yml/badge.svg)](https://github.com/klaeufer/dashcamutils/actions/workflows/ci.yml)


# Purpose

The current line of Garmin dash cams include a timestamp and GPS information visually in the image.
This utility extracts this information using OCR, parses it, and populates the corresponding EXIF metadata.
It then crops the image to remove the timestamp and usually the vehicle hood.

# Dependencies

- Python 3.12 or later

All other dependencies are Python packages installed automatically: Pillow (cropping/rotation), RapidOCR (OCR; downloads its models on first use), and piexif (EXIF metadata).

# Usage

```
usage: tag_images [-h] [-c CROP_BOTTOM] [-r ANGLE] [-z TIMEZONE]
                  [-d {auto,mdy,dmy}] [-s] [-v] [--verbose] [image ...]

  -c, --crop-bottom CROP_BOTTOM
                        pixels to crop from the bottom (e.g., the hood)
  -r, --angle ANGLE     rotation in degrees counterclockwise, as in
                        PIL.Image.rotate
  -z, --timezone TIMEZONE
                        time zone the camera clock is set to: UTC (default),
                        an offset like -05:00, or a name like America/Chicago
  -d, --date-order {auto,mdy,dmy}
                        how to read ambiguous nn/nn/yyyy dates; auto
                        (default) infers it from unambiguous stamps
  -s, --skip_ocr        skip extraction of timestamp using OCR
  -v, --validity_check_manual
                        check validity of manual timestamps
```

`--crop_height` and `--rotation_angle` remain as aliases. Note that positive angles now
rotate counterclockwise (Pillow convention; ImageMagick rotated clockwise), so negate
angles previously used with ImageMagick. After rotating, the output is automatically
cropped to remove the empty corner wedges, so rotated images come out slightly smaller.

## Time stamp formats and time zones

The stamp format is detected automatically: `yyyy/mm/dd`, and `mm/dd/yyyy` or `dd/mm/yyyy`
with either a 24-hour or AM/PM clock. A date such as `23/10/2022` can only be day-first,
and once one is seen the rest of the batch is read the same way; a lone ambiguous date
like `03/04/2022` is read month-first unless you pass `-d dmy`.

The stamp carries no time zone, so it is assumed to be UTC. If your camera clock is set to
local time, pass `-z`. The stamp is written to `DateTimeOriginal` as shown, together with
`OffsetTimeOriginal`, the UTC `GPSDateStamp`/`GPSTimeStamp`, and the file modification time.

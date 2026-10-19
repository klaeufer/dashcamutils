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
usage: tag_images [-h] [-c CROP_BOTTOM] [-r ANGLE] [-s] [-v] [--verbose]
                  [image ...]

  -c, --crop-bottom CROP_BOTTOM
                        pixels to crop from the bottom (e.g., the hood)
  -r, --angle ANGLE     rotation in degrees counterclockwise, as in
                        PIL.Image.rotate
  -s, --skip_ocr        skip extraction of timestamp using OCR
  -v, --validity_check_manual
                        check validity of manual timestamps
```

`--crop_height` and `--rotation_angle` remain as aliases. Note that positive angles now
rotate counterclockwise (Pillow convention; ImageMagick rotated clockwise), so negate
angles previously used with ImageMagick. After rotating, the output is automatically
cropped to remove the empty corner wedges, so rotated images come out slightly smaller.

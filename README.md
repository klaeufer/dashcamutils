# Purpose

The current line of Garmin dash cams include a timestamp and GPS information visually in the image.
This utility extracts this information using OCR, parses it, and populates the corresponding EXIF metadata.
It then crops the image to remove the timestamp and usually the vehicle hood.

# Dependencies

- Python 3
- ImageMagick
- OcrMyPDF
- ExifTool

The plan is to replace the three external command-line dependencies with these Python libraries:

- exif
- Pillow
- pytesseract

# Usage

```
usage: tag_images.py [-h] [-c [CROP_HEIGHT]] [-r [ROTATION_ANGLE]] [-s] [-v]
                     [images [images ...]]

positional arguments:
  images                images to process

optional arguments:
  -h, --help            show this help message and exit
  -c [CROP_HEIGHT], --crop_height [CROP_HEIGHT]
                        height of hood section to be cropped in pixels
  -r [ROTATION_ANGLE], --rotation_angle [ROTATION_ANGLE]
                        image rotation angle
  -s, --skip_ocr        skip extraction of timestamp using OCR
  -v, --validity_check_manual
                        check validity of manual timestamps
```

This creates the following files for each original image file `f.JPG` in the same directory as the original image:

- `f-timestamp.jpg`
- `f.txt`
- `f.JPG_original`
- `f-cropped.jpg`

In addition, for each image where the OCR step fails, the script appends the invalid timestamp to
the file `InvalidTimestamps.txt` in the current directory.

One can then perform the following steps:

- Rename `InvalidTimestamps.txt` to `ManualTimestamps.txt`. 
- Manually edit the invalid timestamps based on visual inspection of the corresponding images.
- Check the validity of the edited timestamps using the `--validity_check_manual` option and re-edit if necessary.
- Rerun the script without the `--validity_check_manual` option.

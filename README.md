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
- Manually edit the invalid timestamps based on visual inspection of the corresponding images, or use AI to fix based on suitable heuristics:
  - all timestamps are in the standard Garmin format, though in some cases only date and time are present while GPS location/speed are not
  - actual deviations from the correct format are caused by OCR problems
  - the first field on each line is the image file name
  - the second field is always the string GARMIN (which sometimes gets garbled because of OCR problems)
  - images are taken in consecutive numerical order (part of the filenames)
  - the images were taken while driving, so consecutive images taken during the same trip would be close to each other in time and location 
- Check the validity of the edited timestamps using the `--validity_check_manual` option and re-edit if necessary:

  ```bash
  tag_images -v 2>&1 > /dev/null | grep ERROR
  ```

- Rerun the script without the `--validity_check_manual` option.

# Development

First-time setup:

```
$ pipenv install -r requirements.txt
$ pipenv shell
$ pipenv install -e .
$ tag_images ...
```

For subsequent uses, simply repeat the `pipenv shell` command and then
run `tag_images`.

# Purpose

The current line of Garmin dash cams include a timestamp and GPS information visually in the image.
This utility parses this information and populates the corresponding EXIF metadata.
It then crops 

# Dependencies

- ImageMagick
- OcrMyPDF
- ExifTool

# Usage

    tag-images.py *.JPG

This creates the following files for each original image file `f.JPG`:

- `f-timestamp.jpg`
- `f.txt`
- `f.JPG_original`
- `f-cropped.jpg`

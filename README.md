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

# Purpose

The current line of Garmin dash cams include a timestamp and GPS information visually in the image.
This utility extracts this information using OCR, parses it, and populates the corresponding EXIF metadata.
It then crops the image to remove the timestamp and usually the vehicle hood.

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

When the OCR step fails, one can manually populate the metadata file (`.txt`) by visually inspecting the image and then run only the tagging and cropping stages.

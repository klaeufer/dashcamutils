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
                  [-d {auto,mdy,dmy}] [--hemisphere {NW,NE,SW,SE}]
                  [--repair] [--interpolate | --no-interpolate]
                  [--sort-by-time] [-s] [-v] [--verbose]
                  [image ...]

  -c, --crop-bottom CROP_BOTTOM
                        pixels to crop from the bottom (e.g., the hood), or
                        auto (default) to detect the hood from the batch
  -r, --angle ANGLE     rotation in degrees counterclockwise, as in
                        PIL.Image.rotate, or auto (default) to estimate the
                        camera tilt from the batch
  -z, --timezone TIMEZONE
                        time zone the camera clock is set to: UTC (default),
                        an offset like -05:00, or a name like America/Chicago
  -d, --date-order {auto,mdy,dmy}
                        how to read ambiguous nn/nn/yyyy dates; auto
                        (default) infers it from unambiguous stamps
  --hemisphere {NW,NE,SW,SE}
                        expected hemispheres of latitude then longitude
                        (default NW; the camera prints '-' for S and W)
  --repair              repair misread stamps by fuzzy parsing and checking
                        them against neighbouring images (capture order)
  --interpolate, --no-interpolate
                        with --repair, estimate the position of images whose
                        GPS can't be read from their neighbours (default)
  --sort-by-time        with --repair, process images in the order of their
                        readable timestamps rather than the order given
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

## Repairing misread stamps

OCR often garbles a stamp: separators read as digits, letters for digits, a dropped digit.
With `--repair`, all the images are read first (list them in capture order, e.g. a shell
glob) and each stamp is parsed tolerantly into several candidate readings. A reading that
is clean and consistent with its neighbours is trusted; for the others the candidate is
chosen that keeps time moving forward, the date equal to the batch's, and the distance
travelled plausible for the elapsed time, and single-digit errors in the coordinates are
corrected when that makes them fit. Signs follow the camera's `-` for S and W; `--hemisphere`
says which signs to expect when none is visible, and a reading whose signs contradict it
needs the neighbours' support to be believed.

Repair works in stages, and each image gets the best result that can be justified:

1. a clean or repairable stamp is tagged with its time and position;
2. if only the GPS part is unreadable, the position is interpolated linearly between the
   nearest located neighbours (unless `--no-interpolate`), provided they are within 10
   minutes of each other, and the image is marked in the EXIF `UserComment`;
3. otherwise the image is tagged with its time only and the position is left blank, to be
   added later by hand if wanted;
4. only if even the time can't be read does the image go to `InvalidTimestamps.txt`.

Every image that is not a clean reading is listed in `RepairedTimestamps.txt` (with the
status `repaired`, `interpolated` or `time-only`) next to what OCR read, so they can be
reviewed. A batch is assumed to use one date format throughout (as a camera writes them): the format
most cleanly read stamps agree on is chosen, and readings in any other format are ignored
with a warning. OCR is also retried on the stamp with a few preprocessings (contrast,
binarising, padding) when the first reading doesn't parse cleanly. Interpolation is
not attempted across gaps over 10 minutes.

Repair assumes the images are listed in capture order; if the readable timestamps run
backwards a warning is logged, and `--sort-by-time` reorders the batch by them instead.
Repair is a heuristic: it
works best on densely sampled sequences, where neighbours constrain each stamp tightly.

## Automatic hood crop and rotation

Unless you pass `-c` and `-r`, both are estimated once from the whole batch (up to 40
evenly spaced images, at least 5) and logged, so you can reuse the values explicitly.

- **Hood (`-c auto`)**: the hood's crest shows up as a step, in the central columns, in
  both average brightness and how much the picture changes from frame to frame (the hood
  changes less than the scenery, even when it is dark and reflective). The crop is
  everything below that step. It needs a moving car with varied scenery and at least
  5 images; if the scene barely changes (parked) or no clear step is found, no cropping is done.
- **Camera moved mid-batch**: with `-c auto`, the batch is also checked for a jump in
  the hood edge (for example the camera got knocked between drives). If one is found, a
  warning lists where, and each stretch gets its own crop and tilt. The split point is
  accurate to a few images in very long batches. An explicit `-c` disables this.
- **Tilt (`-r auto`)**: the camera's roll is found by searching for the rotation that
  lines up the scene's vertical edges (trunks, poles, buildings) best. It is only applied when
  most images show clear vertical structure and agree; otherwise there is a warning and no rotation. Dense
  forest or winding roads often give too little to go on, so check the result and pass `-r`
  yourself if it declines or looks wrong.

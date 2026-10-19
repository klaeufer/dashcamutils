[![CI](https://github.com/klaeufer/dashcamutils/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/klaeufer/dashcamutils/actions/workflows/ci.yml?query=branch%3Amain)
[![CodeQL](https://github.com/klaeufer/dashcamutils/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/klaeufer/dashcamutils/actions/workflows/codeql.yml?query=branch%3Amain)
[![Actionlint](https://github.com/klaeufer/dashcamutils/actions/workflows/actionlint.yml/badge.svg?branch=main)](https://github.com/klaeufer/dashcamutils/actions/workflows/actionlint.yml?query=branch%3Amain)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/github/license/klaeufer/dashcamutils)](https://github.com/klaeufer/dashcamutils/blob/main/LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/klaeufer/dashcamutils/main)](https://github.com/klaeufer/dashcamutils/commits/main)


# Purpose

The current line of Garmin dash cams include a timestamp and GPS information visually in the image.
This utility extracts this information using OCR, parses it, and populates the corresponding EXIF metadata.
It then crops the image to remove the timestamp and usually the vehicle hood.

# Dependencies

- Python 3.12 or later

All other dependencies are Python packages installed automatically: Pillow (cropping/rotation), RapidOCR (OCR; downloads its models on first use), and piexif (EXIF metadata).

# Usage

The command is `dashcam-tag`; the earlier name `tag_images` still works as an alias.
Typical use, on a folder of images listed in capture order:

```
dashcam-tag --repair -z America/Chicago GRMN*.JPG
```

Hood crop and tilt are detected automatically, stamps are repaired from their neighbours,
and each image is tagged and cropped.

```
usage: dashcam-tag [-h] [-c CROP_BOTTOM] [-r ANGLE] [-z TIMEZONE]
                   [--gps-time-only | --no-gps-time-only] [-d {auto,mdy,dmy}]
                   [--hemisphere {NW,NE,SW,SE}] [--repair]
                   [--interpolate | --no-interpolate] [--sort-by-time] [-s]
                   [-v] [--verbose]
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
  --gps-time-only, --no-gps-time-only
                        write the time only as UTC GPS date/time and remove
                        the local-time tags, so Google Photos infers the time
                        zone from the location (default; images without a
                        location keep their local-time tags)
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
local time, pass `-z`. The UTC `GPSDateStamp`/`GPSTimeStamp` and the file modification time
are always written; with `--no-gps-time-only` the stamp is also written to `DateTimeOriginal`
as shown, together with `OffsetTimeOriginal`.

Google Photos can get confused by local-time tags that don't match the position, so by
default `DateTimeOriginal`, `DateTimeDigitized`, `DateTime`, the `OffsetTime*` and
`SubSecTime*` tags are removed, leaving only the UTC GPS date and time, from which Google
Photos works out the local time zone of the location. Images with no location keep their
local-time tags, since there is nothing to infer a zone from. Pass `--no-gps-time-only`
to keep `DateTimeOriginal` and `OffsetTimeOriginal` as described above. Note that the
removed tags are gone from the original once it is processed.

## What is changed and written

The original images are modified in place, and only their metadata: the EXIF block (GPS
position and time, the tags above, and a `UserComment` note on images whose position was
interpolated) and the file modification time. Their pixels are not touched. There is no
backup, so work on copies if you want to keep the original EXIF.

Next to the originals, in the current directory, the tool writes:

- `<name>-cropped.jpg`: the rotated and cropped image, with the same EXIF;
- `<name>.txt` and `<name>-timestamp.jpg`: the OCR text and the stamp strip it was read from;
- `InvalidTimestamps.txt` and `RepairedTimestamps.txt`: images needing attention (see below).

Running the tool again on the same originals gives the same tags and cropped images; the two
log files are appended to, so they accumulate duplicate lines.

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
reviewed. A batch is assumed to use one date format throughout, as a camera writes them:
the format most cleanly read stamps agree on is chosen, and readings in any other format
are ignored with a warning. OCR is also retried on the stamp with a few preprocessings (contrast,
binarising, padding) when the first reading doesn't parse cleanly. Interpolation is
not attempted across gaps over 10 minutes.

Repair assumes the images are listed in capture order; if the readable timestamps run
backwards a warning is logged, and `--sort-by-time` reorders the batch by them instead.
Repair is a heuristic: it works best on densely sampled sequences, where neighbours constrain each stamp tightly.

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

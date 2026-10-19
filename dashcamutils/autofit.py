"""Estimate the hood crop and the roll angle of a dash cam from a batch of images.

Both are properties of how the camera is mounted, so they are estimated once from
many frames rather than per image: the hood is the part of the frame that never
changes while the scenery does, and roll shows up as a tilt of the scene's
dominant vertical edges.
"""

import logging
import math
from collections.abc import Sequence

import numpy as np
from PIL import Image

SAMPLE_FRAMES = 40
WORK_WIDTH = 640
MIN_FRAMES = 5

# Hood: a row counts as hood if enough of its pixels are static across frames
STATIC_ROW_FRACTION = 0.1
MAX_HOOD_FRACTION = 0.4  # more than this of the frame is implausible
HOOD_MARGIN = 0.01  # of image height, to clear the antialiased edge

# Angle
MAX_TILT = 8.0  # degrees searched on either side of upright
MIN_CONFIDENT_FRAMES = 0.3
MAX_SPREAD = 0.6  # degrees of disagreement between confident frames
# best edge-alignment energy relative to the mean over all tilts; forest
# footage scores about 1.0, scenes with real vertical lines several times that
CONFIDENT = 1.5


def _load_gray(
    paths: Sequence[str], width: int = WORK_WIDTH
) -> tuple[np.ndarray, tuple[int, int]]:
    """Stack of downscaled grayscale frames, plus the full image size."""
    step = max(1, len(paths) // SAMPLE_FRAMES)
    frames = []
    size = (0, 0)
    for p in paths[::step][:SAMPLE_FRAMES]:
        with Image.open(p) as img:
            if size == (0, 0):
                size = img.size
            elif img.size != size:
                continue
            img.draft("L", (width, width * size[1] // size[0]))
            small = img.convert("L").resize((width, round(width * size[1] / size[0])))
            frames.append(np.asarray(small, dtype=np.float32))
    if not frames:
        return np.empty((0, 0, 0), dtype=np.float32), size
    return np.stack(frames), size


def estimate_hood_crop(paths: Sequence[str]) -> int | None:
    """Pixels to remove from the bottom to drop the hood, or None if unsure."""
    stack, (_, full_h) = _load_gray(paths)
    if len(stack) < MIN_FRAMES:
        logging.warning(f"hood detection needs at least {MIN_FRAMES} images")
        return None
    # a parked car sees a static scene everywhere, so nothing can be told apart
    std = stack.std(axis=0)
    h = std.shape[0]
    scene = float(np.median(std[: h // 2]))
    if scene < 8:
        logging.warning("scenery barely changes between images; cannot find the hood")
        return None
    static = std < max(4.0, 0.2 * scene)
    frac = static.mean(axis=1)
    rows = 0
    for y in range(h - 1, -1, -1):
        if frac[y] < STATIC_ROW_FRACTION:
            break
        rows += 1
    if rows / h > MAX_HOOD_FRACTION:
        logging.warning("static region too large to be a hood; not cropping")
        return None
    return round((rows / h + HOOD_MARGIN) * full_h) if rows else 0


def _edge_energy(gx: np.ndarray, tilt: float) -> float:
    """How sharply the vertical edges line up once rows are sheared by `tilt`.

    Edges that lean by `tilt` become exactly vertical after the shear, where they
    pile into a few columns and the sum of squared column totals peaks.
    """
    h, w = gx.shape
    shift = np.rint((np.arange(h) - h / 2) * math.tan(math.radians(tilt))).astype(int)
    cols = (np.arange(w)[None, :] - shift[:, None]) % w
    totals = np.bincount(cols.ravel(), weights=gx.ravel(), minlength=w)
    return float(np.square(totals).sum())


def _frame_tilt(gray: np.ndarray) -> tuple[float, float] | None:
    """(lean of vertical edges in degrees CCW, confidence) for one frame."""
    gx = np.abs(np.diff(gray, axis=1))
    gx = np.where(gx > np.percentile(gx, 90), gx, 0.0)
    if not gx.any():
        return None
    coarse = np.arange(-MAX_TILT, MAX_TILT + 0.01, 0.5)
    scores = [_edge_energy(gx, t) for t in coarse]
    best = float(coarse[int(np.argmax(scores))])
    fine = np.arange(best - 0.5, best + 0.51, 0.1)
    fine_scores = [_edge_energy(gx, t) for t in fine]
    top = np.flatnonzero(np.array(fine_scores) >= max(fine_scores) * 0.9999)
    return float(fine[int(round(float(top.mean())))]), max(fine_scores) / float(
        np.mean(scores)
    )


def estimate_angle(paths: Sequence[str]) -> float | None:
    """Rotation (degrees counterclockwise, as Image.rotate) that levels the camera.

    Returns None when the frames do not agree on a tilt.
    """
    stack, _ = _load_gray(paths)
    if len(stack) < MIN_FRAMES:
        logging.warning(f"angle detection needs at least {MIN_FRAMES} images")
        return None
    # the hood and overlay are tilted with the camera, so skip the bottom quarter
    top = stack[:, : stack.shape[1] * 3 // 4, :]
    found = [t for g in top if (t := _frame_tilt(g)) is not None]
    confident = [a for a, c in found if c > CONFIDENT]
    if len(confident) < MIN_CONFIDENT_FRAMES * len(stack):
        logging.warning("no clear vertical lines in most images; not rotating")
        return None
    tilt = float(np.median(confident))
    spread = float(np.median(np.abs(np.array(confident) - tilt)))
    if spread > MAX_SPREAD:
        logging.warning(f"images disagree about the tilt (spread {spread:.2f} deg)")
        return None
    return round(-tilt, 1) + 0.0 if math.isfinite(tilt) else None


def fit(
    paths: Sequence[str], crop: int | None, angle: float | None
) -> tuple[int, float]:
    """Fill in whichever of `crop` and `angle` is None by estimating from `paths`.

    Estimates that fail fall back to no crop / no rotation, with a warning.
    """
    if crop is None:
        found = estimate_hood_crop(paths)
        if found is None:
            logging.warning("could not detect the hood; not cropping (use -c)")
        else:
            logging.info(f"detected hood: cropping {found} pixels (-c {found})")
        crop = found or 0
    if angle is None:
        found_angle = estimate_angle(paths)
        if found_angle is None:
            logging.warning("could not detect the tilt; not rotating (use -r)")
        else:
            logging.info(
                f"detected tilt: rotating {found_angle} degrees (-r {found_angle})"
            )
        angle = found_angle or 0.0
    return crop, angle

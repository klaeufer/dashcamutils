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
SEGMENT_FRAMES = 120  # frames examined when looking for a mid-batch camera shift
WORK_WIDTH = 640
MIN_FRAMES = 5

# Hood: searched for in this band of the frame (the stamp sits below it)
HOOD_SEARCH_TOP, HOOD_SEARCH_BOTTOM = 0.55, 0.95
HOOD_MIN_FIT = 0.6  # share of profile variance a hood/scenery step must explain
HOOD_MARGIN = 0.0
MIN_SEGMENT = 8  # frames a stretch needs before it can have its own hood crop
MIN_SHIFT = 0.02  # hood edge move, as a share of image height, that counts as a shift
SHIFT_GAIN = 0.05  # how much better two crops must fit than one

# Angle
MAX_TILT = 8.0  # degrees searched on either side of upright
MIN_CONFIDENT_FRAMES = 0.3
MAX_SPREAD = 0.6  # degrees of disagreement between confident frames
# best edge-alignment energy relative to the mean over all tilts; forest
# footage scores about 1.0, scenes with real vertical lines several times that
CONFIDENT = 1.5


def _load_gray(
    paths: Sequence[str], width: int = WORK_WIDTH, limit: int = SAMPLE_FRAMES
) -> tuple[np.ndarray, tuple[int, int]]:
    """Stack of downscaled grayscale frames, plus the full image size."""
    step = max(1, len(paths) // limit)
    frames = []
    size = (0, 0)
    for p in paths[::step][:limit]:
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


def _hood_split(stack: np.ndarray) -> tuple[int, float]:
    """Row where the hood starts, and how well a hood/scenery split fits (0 to 1).

    Down the central columns, where the hood crest is highest, the hood differs
    from the scenery in two ways that hold up even for a dark, reflective hood:
    it keeps a different average brightness, and it varies less over time. We fit
    a two-level step to both profiles and keep the best row.
    """
    h, w = stack.shape[1:]
    centre = slice(w * 3 // 10, w * 7 // 10)
    brightness = stack[:, :, centre].mean(axis=0).mean(axis=1)
    variability = stack[:, :, centre].std(axis=0).mean(axis=1)
    lo, hi = int(h * HOOD_SEARCH_TOP), int(h * HOOD_SEARCH_BOTTOM)
    feats = []
    for prof in (brightness, variability):
        seg = prof[lo:hi]
        spread = float(seg.std())
        feats.append((seg - seg.mean()) / spread if spread > 1e-6 else seg * 0)
    x = np.stack(feats, axis=1)
    n = len(x)
    # sum of squares within each side of every candidate split, from cumulative sums
    cs = np.vstack([np.zeros(x.shape[1]), np.cumsum(x, axis=0)])
    cs2 = np.vstack([np.zeros(x.shape[1]), np.cumsum(x * x, axis=0)])
    best_k, best_sse = 0, float("inf")
    total = float((cs2[n] - cs[n] ** 2 / n).sum())
    for k in range(int(n * 0.05), int(n * 0.95)):
        left = cs2[k] - cs[k] ** 2 / k
        right = (cs2[n] - cs2[k]) - (cs[n] - cs[k]) ** 2 / (n - k)
        sse = float((left + right).sum())
        if sse < best_sse:
            best_k, best_sse = k, sse
    fit = 1 - best_sse / total if total > 0 else 0.0
    return lo + best_k, fit


def _hood_crop(stack: np.ndarray, full_h: int) -> int | None:
    """Hood crop from a stack of frames: None if unknowable, 0 if no hood found."""
    if len(stack) < MIN_FRAMES:
        logging.warning(f"hood detection needs at least {MIN_FRAMES} images")
        return None
    h = stack.shape[1]
    # a parked car sees a static scene everywhere, so nothing can be told apart
    scene = float(np.median(stack.std(axis=0)[: h // 2]))
    if scene < 8:
        logging.warning("scenery barely changes between images; cannot find the hood")
        return None
    row, fit = _hood_split(stack)
    logging.debug(f"hood split at row {row}/{h}, fit {fit:.2f}")
    if fit < HOOD_MIN_FIT:
        logging.warning(
            f"no clear hood edge found (fit {fit:.2f}); not cropping (use -c)"
        )
        return 0
    return round((1 - row / h + HOOD_MARGIN) * full_h)


def estimate_hood_crop(paths: Sequence[str]) -> int | None:
    """Pixels to remove from the bottom to drop the hood, or None if unsure."""
    stack, (_, full_h) = _load_gray(paths)
    return _hood_crop(stack, full_h)


def _find_shifts(stack: np.ndarray, offset: int = 0) -> list[int]:
    """Frame indices where the hood edge jumps, found by recursive best split."""
    n = len(stack)
    if n < 2 * MIN_SEGMENT:
        return []
    h = stack.shape[1]
    if float(np.median(stack.std(axis=0)[: h // 2])) < 8:
        return []
    _, whole = _hood_split(stack)
    best: tuple[float, int] | None = None
    for k in range(MIN_SEGMENT, n - MIN_SEGMENT + 1):
        row_l, fit_l = _hood_split(stack[:k])
        row_r, fit_r = _hood_split(stack[k:])
        score = min(fit_l, fit_r)
        if (
            score >= HOOD_MIN_FIT
            and score > whole + SHIFT_GAIN
            and abs(row_l - row_r) / h >= MIN_SHIFT
            and (best is None or score > best[0])
        ):
            best = (score, k)
    if best is None:
        return []
    k = best[1]
    return (
        _find_shifts(stack[:k], offset)
        + [offset + k]
        + _find_shifts(stack[k:], offset + k)
    )


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
    return _angle(stack)


def _angle(stack: np.ndarray) -> float | None:
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


def fit_segments(
    paths: Sequence[str], crop: int | None, angle: float | None
) -> list[tuple[int, int, float]]:
    """Like `fit`, but notices when the camera moved partway through the batch.

    Returns (first image index, crop, angle) for each stretch of images that shares
    a mounting, in order. Shifts are only looked for when the crop is automatic, and
    their position is accurate to the sampling step (a few images in a long batch).
    """
    if crop is not None or len(paths) < 2 * MIN_SEGMENT:
        c, a = fit(paths, crop, angle)
        return [(0, c, a)]
    step = max(1, len(paths) // SEGMENT_FRAMES)
    stack, (_, full_h) = _load_gray(paths, limit=SEGMENT_FRAMES)
    starts = [0] + [k * step for k in _find_shifts(stack)]
    if len(starts) == 1:
        c, a = fit(paths, crop, angle)
        return [(0, c, a)]
    logging.warning(
        f"the camera seems to have moved: {len(starts)} stretches of images "
        f"starting at images {[s + 1 for s in starts]}; fitting each separately"
    )
    ends = starts[1:] + [len(paths)]
    out = []
    for first, end in zip(starts, ends, strict=True):
        logging.info(f"images {first + 1}-{end}:")
        c, a = fit(paths[first:end], None, angle)
        out.append((first, c, a))
    return out

"""Per-image hood-boundary estimation for optional crop planning.

The estimate is heuristic and should be reviewed before relying on it. Coordinates
use the decoded image's pixel grid, origin at top-left, with y increasing downward.
"""

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class HoodPlan:
    angle: float
    crop_bottom: int
    boundary_y: tuple[int, ...]
    confidence: float
    needs_review: bool
    review_reasons: tuple[str, ...]


def estimate(
    image: Image.Image, margin: int = 10, reference_fraction: float = 1 / 3
) -> HoodPlan:
    """Estimate hood boundary and return a compatible bottom-crop plan.

    The cut is selected from the center reference region after leveling the
    boundary. The remaining frame retains full width, matching the approved
    center-reference policy; this does not guarantee hood removal at the sides.
    """
    if margin < 0:
        raise ValueError("margin must be nonnegative")
    if not 0 < reference_fraction <= 1:
        raise ValueError("reference_fraction must be in (0, 1]")
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    h, w = gray.shape
    y0, y1 = max(0, h - int(h * 0.313)), min(int(h * 0.92), h - int(h * 0.125))
    if y1 <= y0 + 5:
        raise ValueError("hood search band is empty")

    # Vertical edge energy, with modest row smoothing to reduce single-pixel noise.
    gradient = np.abs(np.gradient(gray, axis=0))
    center_fraction = 0.60
    cx = (w - 1) / 2
    center = gradient[
        y0:y1,
        max(0, int(cx - w * center_fraction / 2)) : min(
            w, int(cx + w * center_fraction / 2)
        ),
    ]
    profile = np.convolve(center.mean(axis=1), np.ones(9) / 9, mode="same")
    peak = int(np.argmax(profile))
    center_y = y0 + peak
    radius = max(18, int(h * 0.035))
    lo, hi = max(y0, center_y - radius), min(y1, center_y + radius + 1)
    boundary = lo + np.argmax(gradient[lo:hi], axis=0)
    kernel = max(9, (w // 90) | 1)
    boundary = np.convolve(
        boundary.astype(float), np.ones(kernel) / kernel, mode="same"
    )
    xs = np.arange(w, dtype=float)
    central = np.abs(xs - cx) <= w * center_fraction / 2
    slope, intercept = np.polyfit(xs[central], boundary[central], 1)
    angle = float(np.degrees(np.arctan(slope)))
    boundary = boundary.astype(float)
    boundary_tuple = tuple(int(y) for y in np.rint(boundary))

    # Apply PIL's counterclockwise rotation convention to boundary coordinates.
    rotated_y = (
        -np.sin(np.radians(angle)) * (xs - cx)
        + np.cos(np.radians(angle)) * (boundary - (h - 1) / 2)
        + (h - 1) / 2
    )
    reference = np.abs(xs - cx) <= w * reference_fraction / 2
    cut_y = int(np.floor(float(rotated_y[reference].min()) - margin))
    cut_y = max(1, min(h, cut_y))
    peak_quality = float(profile[peak] / max(float(profile.max()), 1e-6))
    residual = float(
        np.median(np.abs(boundary[central] - (slope * xs[central] + intercept)))
    )
    reasons = []
    if peak_quality < 0.25:
        reasons.append("weak_center_edge")
    if residual > 14:
        reasons.append("inconsistent_center_line")
    if cut_y <= 1:
        reasons.append("invalid_crop_extent")
    confidence = float(
        np.clip(0.5 * peak_quality + 0.5 * max(0, 1 - residual / 28), 0, 1)
    )
    return HoodPlan(
        angle, h - cut_y, boundary_tuple, confidence, bool(reasons), tuple(reasons)
    )


def plan_from_boundary(
    points, width, height, angle, margin=10, reference_fraction=1 / 3
):
    """Construct a plan from a per-column manual boundary override."""
    values = np.asarray(points, dtype=float)
    if (
        len(values) != width
        or not np.isfinite(values).all()
        or min(values) < 0
        or max(values) >= height
    ):
        raise ValueError(
            "boundary override must contain one in-range point per image column"
        )
    if not math.isfinite(angle) or abs(angle) > 15:
        raise ValueError("override angle must be finite and within 15 degrees")
    xs = np.arange(width, dtype=float)
    cx = (width - 1) / 2
    rotated_y = (
        -np.sin(np.radians(angle)) * (xs - cx)
        + np.cos(np.radians(angle)) * (values - (height - 1) / 2)
        + (height - 1) / 2
    )
    reference = np.abs(xs - cx) <= width * reference_fraction / 2
    cut_y = max(
        1, min(height, int(np.floor(float(rotated_y[reference].min()) - margin)))
    )
    return HoodPlan(
        float(angle), height - cut_y, tuple(int(y) for y in points), 1.0, False, ()
    )

"""Reconcile per-image candidate readings across a sequence of images.

Images are assumed to be in capture order (filename order). Confident readings
act as anchors; for the others we choose the candidate that is consistent with
the anchors around it (time moves forward, the vehicle can't teleport), try
single-digit repairs of the coordinates, and finally fall back to interpolating
between anchors.
"""

import datetime
import itertools
import math
from dataclasses import dataclass
from typing import Literal

from .stamps import Reading

type Status = Literal["ok", "repaired", "interpolated", "time-only", "unreadable"]

CLEAN_COST = 0.5  # readings at or below this cost are trusted anchors
MAX_SPEED_MS = 70.0  # ~155 mph; faster between two stamps is implausible
SLACK_M = 150.0  # GPS jitter and speed variation allowance
METERS_PER_DEG = 111_320.0
# Anchors further apart than this say nothing reliable about what lies between
MAX_INTERPOLATION_GAP = datetime.timedelta(minutes=10)


@dataclass(frozen=True)
class Resolved:
    when: datetime.datetime | None
    lat: float | None
    lon: float | None
    speed: int
    status: Status

    @property
    def location(self) -> tuple[float, float, int] | None:
        if self.lat is None or self.lon is None:
            return None
        return (self.lat, self.lon, self.speed)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * METERS_PER_DEG
    dx = (lon2 - lon1) * METERS_PER_DEG * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _plausible_step(a: Reading | Resolved, b: Reading | Resolved) -> bool:
    """Can the vehicle get from stamp `a` to later stamp `b`?"""
    if a.when is None or b.when is None or b.when < a.when:
        return False
    if None in (a.lat, a.lon, b.lat, b.lon):
        return True
    assert a.lat is not None and a.lon is not None
    assert b.lat is not None and b.lon is not None
    dt = (b.when - a.when).total_seconds()
    return distance_m(a.lat, a.lon, b.lat, b.lon) <= MAX_SPEED_MS * dt + SLACK_M


def _digit_variants(value: float, places: int) -> list[float]:
    """`value` with each single digit replaced by every other digit."""
    sign = -1 if value < 0 else 1
    text = f"{abs(value):.{places}f}"
    out = []
    for i, ch in enumerate(text):
        if ch == ".":
            continue
        for d in "0123456789":
            if d != ch:
                out.append(sign * float(text[:i] + d + text[i + 1 :]))
    return out


def _repair_position(
    r: Reading, prev: Reading | Resolved | None, nxt: Reading | Resolved | None
) -> Reading | None:
    """A single-digit fix to lat or lon that makes `r` fit its neighbours."""
    if r.lat is None or r.lon is None:
        return None
    options: list[Reading] = []
    for lat in [r.lat, *_digit_variants(r.lat, 5)]:
        for lon in [r.lon] if lat != r.lat else [r.lon, *_digit_variants(r.lon, 5)]:
            if (lat, lon) == (r.lat, r.lon):
                continue
            cand = Reading(r.when, lat, lon, r.speed, r.cost + 1.0)
            if all(
                n is None or ok
                for n, ok in (
                    (prev, prev is None or _plausible_step(prev, cand)),
                    (nxt, nxt is None or _plausible_step(cand, nxt)),
                )
            ):
                options.append(cand)
    if not options:
        return None
    # prefer the fix nearest to where the neighbours say we should be
    refs = [x for x in (prev, nxt) if x is not None and x.lat is not None]
    if not refs:
        return None

    def off(c: Reading) -> float:
        assert c.lat is not None and c.lon is not None
        return sum(distance_m(c.lat, c.lon, x.lat or 0, x.lon or 0) for x in refs)

    return min(options, key=off)


def _clean(cs: list[Reading]) -> bool:
    return bool(cs) and cs[0].cost <= CLEAN_COST


def _anchor_times(
    candidates: list[list[Reading]],
) -> list[datetime.datetime | None]:
    """Time of each image's clean reading, else None."""
    return [cs[0].when if _clean(cs) else None for cs in candidates]


def _time_variants(when: datetime.datetime) -> list[datetime.datetime]:
    """`when` with each single digit of its date and time replaced."""
    text = when.strftime("%Y%m%d%H%M%S")
    out = []
    for i, ch in enumerate(text):
        for d in "0123456789":
            if d == ch:
                continue
            try:
                out.append(
                    datetime.datetime.strptime(
                        text[:i] + d + text[i + 1 :], "%Y%m%d%H%M%S"
                    )
                )
            except ValueError:
                continue
    return out


def count_out_of_order(candidates: list[list[Reading]]) -> int:
    """How many times the clean readings' times step backwards in list order."""
    times = [t for t in _anchor_times(candidates) if t is not None]
    return sum(b < a for a, b in itertools.pairwise(times))


def time_order(candidates: list[list[Reading]]) -> list[int]:
    """Indices that put the images in time order.

    Images with a clean reading are sorted by it; the others keep their place
    relative to the nearest earlier anchor (or the first anchor, if none).
    """
    times = _anchor_times(candidates)
    known = [t for t in times if t is not None]
    if not known:
        return list(range(len(candidates)))
    keys: list[datetime.datetime] = []
    current = next(t for t in times if t is not None)
    for t in times:
        current = t or current
        keys.append(current)
    return sorted(range(len(candidates)), key=lambda i: (keys[i], i))


def resolve(
    candidates: list[list[Reading]], interpolate: bool = False
) -> list[Resolved]:
    """Pick one reading per image, repairing against neighbours."""
    n = len(candidates)
    out: list[Resolved | None] = [None] * n

    def as_resolved(r: Reading, status: Status) -> Resolved:
        return Resolved(r.when, r.lat, r.lon, r.speed or 0, status)

    # pass 1: clean readings are anchors
    for i, cs in enumerate(candidates):
        if _clean(cs):
            out[i] = as_resolved(cs[0], "ok")

    # an apparently clean reading that contradicts its neighbours even though
    # they agree with each other (a dropped digit moved the longitude, or a
    # misread digit put the date a week off) is not an anchor
    anchors = [i for i, r in enumerate(out) if r is not None]
    suspect = []
    for k, i in enumerate(anchors):
        r = out[i]
        if r is None:
            continue
        before = [x for j in anchors[max(0, k - 2) : k] if (x := out[j])]
        after = [x for j in anchors[k + 1 : k + 3] if (x := out[j])]
        if before and after:
            b, nx = before[-1], after[0]
            if _plausible_step(b, nx) and not (
                _plausible_step(b, r) and _plausible_step(r, nx)
            ):
                suspect.append(i)
        elif len(before) == 2 or len(after) == 2:
            # at an edge, judge against the two neighbours on the one side
            side = before or after
            if _plausible_step(*side) and not any(
                _plausible_step(x, r) if before else _plausible_step(r, x) for x in side
            ):
                suspect.append(i)
    for i in suspect:
        out[i] = None

    def neighbour(i: int, step: int) -> Resolved | None:
        j = i + step
        while 0 <= j < n:
            r = out[j]
            if r is not None and r.status == "ok":
                return r
            j += step
        return None

    # pass 2: choose the candidate consistent with surrounding anchors
    for i, cs in enumerate(candidates):
        if out[i] is not None:
            continue
        prev, nxt = neighbour(i, -1), neighbour(i, +1)
        full = [c for c in cs if c.location is not None]
        for c in full:
            if (prev is None or _plausible_step(prev, c)) and (
                nxt is None or _plausible_step(c, nxt)
            ):
                out[i] = as_resolved(c, "repaired")
                break
        if out[i] is not None or not full:
            continue
        best = full[0]
        # a single misread digit in the date or time can put the reading
        # outside the window its neighbours allow
        if (prev is not None and prev.when and best.when < prev.when) or (
            nxt is not None and nxt.when and best.when > nxt.when
        ):
            lo = prev.when if prev and prev.when else None
            hi = nxt.when if nxt and nxt.when else None
            fits = [
                t
                for t in _time_variants(best.when)
                if (lo is None or t >= lo) and (hi is None or t <= hi)
            ]
            if len(fits) >= 1:
                target = best.when
                t = min(fits, key=lambda x: abs((x - target).total_seconds()))
                best = Reading(t, best.lat, best.lon, best.speed, best.cost + 1.0)
        fixed = _repair_position(best, prev, nxt)
        if (
            fixed is None
            and (prev is None or _plausible_step(prev, best))
            and (nxt is None or _plausible_step(best, nxt))
        ):
            fixed = best
        if fixed and (prev is None or _plausible_step(prev, fixed)):
            out[i] = as_resolved(fixed, "repaired")

    # pass 3: time-only readings and remaining gaps
    for i, cs in enumerate(candidates):
        if out[i] is not None:
            continue
        prev, nxt = neighbour(i, -1), neighbour(i, +1)
        when = next(
            (
                c.when
                for c in cs
                if (prev is None or prev.when is None or c.when >= prev.when)
                and (nxt is None or nxt.when is None or c.when <= nxt.when)
            ),
            None,
        )
        out[i] = Resolved(when, None, None, 0, "time-only" if when else "unreadable")

    if interpolate:
        for i in range(n):
            r = out[i]
            if r is None or r.when is None or r.location is not None:
                continue
            _fill(out, i)

    return [r for r in out if r is not None] if all(out) else []


def _fill(out: list[Resolved | None], i: int) -> None:
    """Interpolate the position of image `i`, whose time is known, linearly in time
    between the nearest located neighbours."""
    n = len(out)

    def located(step: int) -> int | None:
        for j in itertools.count(i + step, step):
            if not 0 <= j < n:
                return None
            r = out[j]
            if r is not None and r.location is not None and r.when is not None:
                return j
        return None

    a, b = located(-1), located(+1)
    cur = out[i]
    if a is None or b is None or cur is None:
        return
    ra, rb = out[a], out[b]
    assert ra is not None and rb is not None
    assert ra.when and rb.when and ra.lat is not None and rb.lat is not None
    assert ra.lon is not None and rb.lon is not None
    if rb.when - ra.when > MAX_INTERPOLATION_GAP:
        return
    when = cur.when
    if when is None:
        return
    span = (rb.when - ra.when).total_seconds()
    f = (
        0.0
        if span <= 0
        else min(max((when - ra.when).total_seconds() / span, 0.0), 1.0)
    )
    out[i] = Resolved(
        when,
        ra.lat + (rb.lat - ra.lat) * f,
        ra.lon + (rb.lon - ra.lon) * f,
        round(ra.speed + (rb.speed - ra.speed) * f),
        "interpolated",
    )

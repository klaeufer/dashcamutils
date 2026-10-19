"""Tolerant parsing of OCR'd Garmin stamp lines into scored candidate readings.

A clean stamp looks like ``GARMIN 03/21/2026 21:14:57 41.89173 -87.66727 5 MPH``.
OCR garbles the punctuation, swaps letters for digits, and sometimes turns a
separator into a stray digit, so instead of matching a rigid pattern we reduce
the line to its digits and look for every way of laying the stamp's fields
(date, time, latitude, longitude, speed) over them. Each way is a candidate with
a cost (the number of digits we had to discard); the sequence logic in
``sequence.py`` then picks among candidates using the neighbouring images.
"""

import datetime
import re
from dataclasses import dataclass
from typing import Literal

type DateFormat = Literal["mdy", "dmy", "ymd"]
type Hemisphere = Literal["NW", "NE", "SW", "SE"]

ALL_FORMATS: tuple[DateFormat, ...] = ("mdy", "dmy", "ymd")

# Characters OCR commonly returns in place of a digit
CONFUSABLES = {
    "O": "0",
    "o": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "l": "1",
    "i": "1",
    "|": "1",
    "!": "1",
    "Z": "2",
    "S": "5",
    "B": "8",
    "g": "9",
}
DASHES = "-–—−_~"  # noqa: RUF001 (the odd dashes are what OCR produces)
UNIT_LETTERS = "MPHFK"
MAX_SKIP = 2  # stray digits tolerated before any one field
MIN_YEAR, MAX_YEAR = 2000, 2099

_AMPM = re.compile(r"(?<![A-Za-z])([AP])M(?![A-Za-z])")


@dataclass(frozen=True)
class Reading:
    """One interpretation of a stamp line; lower cost means fewer repairs."""

    when: datetime.datetime
    lat: float | None
    lon: float | None
    speed: int | None
    cost: float
    fmt: DateFormat = "ymd"

    @property
    def location(self) -> tuple[float, float, int] | None:
        if self.lat is None or self.lon is None:
            return None
        return (self.lat, self.lon, self.speed or 0)


def _digit_stream(text: str) -> list[tuple[str, int]]:
    """Digits of `text` with confusable letters mapped, each with its index."""
    out: list[tuple[str, int]] = []
    n = len(text)
    for i, c in enumerate(text):
        if c.isdigit():
            out.append((c, i))
        elif c in CONFUSABLES:
            prev = text[i - 1] if i else ""
            nxt = text[i + 1] if i + 1 < n else ""
            touches_digit = prev.isdigit() or nxt.isdigit()
            if touches_digit and nxt not in UNIT_LETTERS:
                out.append((CONFUSABLES[c], i))
    return out


def _make_date(fmt: DateFormat, s: str) -> datetime.date | None:
    if fmt == "ymd":
        y, m, d = s[0:4], s[4:6], s[6:8]
    elif fmt == "mdy":
        m, d, y = s[0:2], s[2:4], s[4:8]
    else:
        d, m, y = s[0:2], s[2:4], s[4:8]
    try:
        year = int(y)
        if not MIN_YEAR <= year <= MAX_YEAR:
            return None
        return datetime.date(year, int(m), int(d))
    except ValueError:
        return None


def _make_time(s: str, ampm: str | None) -> datetime.time | None:
    h, m, sec = int(s[0:2]), int(s[2:4]), int(s[4:6])
    if ampm and 1 <= h <= 12:
        h = h % 12 + (12 if ampm == "P" else 0)
    if h > 23 or m > 59 or sec > 59:
        return None
    return datetime.time(h, m, sec)


def _sign_before(text: str, index: int) -> bool:
    """True if a dash-like character sits just before text[index]."""
    return any(c in DASHES for c in text[max(0, index - 2) : index])


def read_candidates(
    line: str,
    formats: tuple[DateFormat, ...] = ALL_FORMATS,
    hemisphere: Hemisphere = "NW",
) -> list[Reading]:
    """All plausible readings of `line`, best (lowest cost) first."""
    ampm_match = _AMPM.search(line)
    ampm = ampm_match.group(1) if ampm_match else None
    if ampm_match:
        line = line[: ampm_match.start()] + " " + line[ampm_match.end() :]

    # confusables are mapped first so a letter-for-digit at the start of the
    # numbers (e.g. "GARMINO3/...") isn't mistaken for part of the header
    stream = _digit_stream(line)
    if not stream:
        return []
    first = stream[0][1]
    text = line[first:]
    stream = [(c, i - first) for c, i in stream]
    cut = re.search(f"[{UNIT_LETTERS}]", text)
    if cut:
        stream = [(c, i) for c, i in stream if i < cut.start()]
    digits = "".join(c for c, _ in stream)
    where = [i for _, i in stream]
    n = len(digits)

    lat_south = hemisphere[0] == "S"
    lon_east = hemisphere[1] == "E"

    found: dict[tuple, Reading] = {}  # keyed by format too, so they stay distinct

    def finish(
        fmt: DateFormat, cost: float, d: int, t: int, la: int, lo: int, lo_len: int
    ) -> None:
        date = _make_date(fmt, digits[d : d + 8])
        time = _make_time(digits[t : t + 6], ampm)
        if date is None or time is None:
            return
        lat_i = int(digits[la : la + 2])
        lon_i = int(digits[lo : lo + lo_len - 5])
        if lat_i > 90 or lon_i > 180 or (lo_len == 8 and lon_i < 100):
            return
        rest = digits[lo + lo_len :]
        speed = int(rest[:3]) if rest else None
        # speeds are one or two digits; more usually means a longitude digit
        # was misaligned into the speed
        cost += (1.5 + len(rest) - 3 if len(rest) >= 3 else 0) + (
            0.5 if not rest else 0
        )

        lat = float(f"{digits[la : la + 2]}.{digits[la + 2 : la + 7]}")
        lon = float(
            f"{digits[lo : lo + lo_len - 5]}.{digits[lo + lo_len - 5 : lo + lo_len]}"
        )
        # fields are separated by something other than a digit in a real stamp;
        # digits running straight on from the previous field are suspect
        for prev_end, start in ((t + 5, la), (la + 6, lo)):
            if text[where[prev_end] + 1 : where[start]].strip("0123456789") == "":
                cost += 1
        lat_neg = _sign_before(text, where[la])
        lon_neg = _sign_before(text, where[lo])
        # An unseen dash defaults to the expected hemisphere; a seen one that
        # contradicts it is kept, at a cost, and the sequence pass can overrule.
        for lat_sign, lat_cost in {
            (-1 if lat_neg else 1): 0.0 if lat_neg == lat_south else 1.0,
            (-1 if lat_south else 1): 1.5 if lat_neg != lat_south else 0.0,
        }.items():
            for lon_sign, lon_cost in {
                (-1 if lon_neg else 1): 0.0 if lon_neg == (not lon_east) else 1.0,
                (1 if lon_east else -1): 1.5 if lon_neg == lon_east else 0.2,
            }.items():
                when = datetime.datetime.combine(date, time)
                total = cost + lat_cost + lon_cost
                key = (fmt, when, lat_sign * lat, lon_sign * lon, speed)
                if key not in found or found[key].cost > total:
                    found[key] = Reading(
                        when, lat_sign * lat, lon_sign * lon, speed, total, fmt
                    )

    for fmt in formats:
        for s_d in range(MAX_SKIP + 1):
            d = s_d
            for s_t in range(MAX_SKIP + 1):
                t = d + 8 + s_t
                for s_la in range(MAX_SKIP + 1):
                    la = t + 6 + s_la
                    for s_lo in range(MAX_SKIP + 1):
                        lo = la + 7 + s_lo
                        for lo_len in (7, 8):
                            if lo + lo_len > n:
                                continue
                            cost = float(s_d + s_t + s_la + s_lo)
                            finish(fmt, cost, d, t, la, lo, lo_len)

    # time-only readings when the GPS part is unreadable
    if not found:
        for fmt in formats:
            for s_d in range(MAX_SKIP + 1):
                for s_t in range(MAX_SKIP + 1):
                    t = s_d + 8 + s_t
                    if t + 6 > n:
                        continue
                    date = _make_date(fmt, digits[s_d : s_d + 8])
                    time = _make_time(digits[t : t + 6], ampm)
                    if date and time:
                        when = datetime.datetime.combine(date, time)
                        found[(fmt, when, None, None, None)] = Reading(
                            when, None, None, None, 3.0 + s_d + s_t, fmt
                        )

    return sorted(found.values(), key=lambda r: r.cost)


def detect_format(
    candidates: list[list[Reading]], clean: float = 0.5
) -> DateFormat | None:
    """The date format most clean readings in a batch agree on.

    A camera writes every stamp of a batch the same way, so each clean line votes
    for the formats it could be (an ambiguous 03/04/2026 votes for both slash
    orders) and the winner is returned; None if nothing was read cleanly. Ties
    between the slash orders go to month-first.
    """
    votes: dict[DateFormat, int] = dict.fromkeys(ALL_FORMATS, 0)
    for cs in candidates:
        for fmt in {c.fmt for c in cs if c.cost <= clean and c.location}:
            votes[fmt] += 1
    if not any(votes.values()):
        return None
    best: DateFormat = "mdy"
    for fmt in ("ymd", "dmy"):
        if votes[fmt] > votes[best]:
            best = fmt
    return best


def only_format(
    candidates: list[list[Reading]], fmt: DateFormat
) -> list[list[Reading]]:
    """Candidates restricted to readings in format `fmt`."""
    return [[c for c in cs if c.fmt == fmt] for cs in candidates]

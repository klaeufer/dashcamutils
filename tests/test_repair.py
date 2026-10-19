import datetime

from dashcamutils import sequence, stamps


def best(line: str, **kw) -> stamps.Reading:
    return stamps.read_candidates(line, **kw)[0]


def test_clean_line():
    r = best("GARMIN 03/21/2026 21:14:57 41.89173 -87.66727 5 MPH")
    assert r.when == datetime.datetime(2026, 3, 21, 21, 14, 57)
    assert r.location == (41.89173, -87.66727, 5)
    assert r.cost <= sequence.CLEAN_COST


def test_noisy_separators_and_letters():
    r = best("GARMIN) 06/24/2026 18:23:21 36.99341 -1O1.89957 17 MPH=")
    assert r.location == (36.99341, -101.89957, 17)


def test_gps_does_not_leak_from_time():
    cands = stamps.read_candidates(
        "GARMIN 03/21/2026 14203525 39.09443 -94.58123 5 MPH"
    )
    assert cands
    assert all(c.lat != 14.20352 for c in cands)
    assert cands[0].location == (39.09443, -94.58123, 5)


def test_signs_follow_dashes_not_assumption():
    r = best("GARMIN 03/21/2026 21:14:57 -33.89173 151.66727 5 KPH", hemisphere="SE")
    assert r.lat is not None and r.lat < 0 and r.lon is not None and r.lon > 0


def test_unreadable_gps_gives_time_only():
    r = best("GARMIN 07/06/2026 17:34:17")
    assert r.when == datetime.datetime(2026, 7, 6, 17, 34, 17)
    assert r.location is None


def _seq(lines: list[str], interpolate: bool = False):
    return sequence.resolve([stamps.read_candidates(x) for x in lines], interpolate)


GOOD = "GARMIN 03/21/2026 21:14:{s:02d} 41.89{p:03d} -87.66727 30 MPH"


def test_misaligned_longitude_repaired_from_neighbours():
    lines = [GOOD.format(s=s, p=s) for s in (10, 11, 12, 13)]
    lines[2] = "GARMIN 03/21/2026 21:14:12 41.89012 -87.6672730 MPH"  # no space
    res = _seq(lines)
    assert [r.status for r in res][:2] == ["ok", "ok"]
    assert res[2].lon == -87.66727 and res[2].when is not None


def test_implausible_jump_is_not_accepted_as_clean():
    lines = [GOOD.format(s=s, p=s) for s in (10, 11, 12, 13, 14)]
    lines[2] = "GARMIN 03/21/2026 21:14:12 41.89012 -7.66727 30 MPH"
    res = _seq(lines)
    assert res[2].status != "ok"
    assert res[2].lon != -7.66727


def test_unreadable_is_interpolated_only_on_request():
    lines = [GOOD.format(s=s, p=s) for s in (10, 12, 14)]
    lines[1] = "GARMIN 03/21/2026 21:14:12"
    assert _seq(lines)[1].status == "unreadable"
    mid = _seq(lines, interpolate=True)[1]
    assert mid.status == "interpolated"
    assert mid.lat is not None and 41.89010 < mid.lat < 41.89014


def test_wrong_date_pulled_to_batch_consensus():
    lines = [GOOD.format(s=s, p=s) for s in (10, 11, 12)]
    lines[1] = "GARMIN 03/27/2026 21:14:11 41.89011 -87.66727 30 MPH"
    res = _seq(lines)
    assert res[1].when is not None and res[1].when.day == 21


def test_out_of_order_detected_and_sorted():
    lines = [GOOD.format(s=s, p=s) for s in (10, 11, 12, 13)]
    lines[1] = "GARMIN 03/21/2026 21:14:11"  # unreadable GPS, follows 10
    shuffled = [lines[2], lines[0], lines[1], lines[3]]
    cands = [stamps.read_candidates(x) for x in shuffled]
    assert sequence.count_out_of_order(cands) == 1
    order = sequence.time_order(cands)
    assert [shuffled[i] for i in order][0] == lines[0]
    assert sequence.count_out_of_order([cands[i] for i in order]) == 0

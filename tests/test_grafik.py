"""Регрессия на эталонной картинке tests/fixtures/grafik.webp (сверено с превью вручную)."""

from datetime import date
from pathlib import Path

import cv2
import pytest

from basen_kalendarz.events import free_intervals, fmt_lanes, fmt_time, merge_same_time
from basen_kalendarz.export import build_calendar
from basen_kalendarz.grid import POOLS, detect_grid
from basen_kalendarz.occupancy import occupancy

IMAGE = Path(__file__).parent / "fixtures" / "grafik.webp"


@pytest.fixture(scope="module")
def parsed():
    img = cv2.imread(str(IMAGE))
    grid = detect_grid(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    busy = occupancy(img, grid, POOLS["sportowy"])
    return grid, busy


def by_day_lane(intervals, day, lane):
    return [(fmt_time(iv.start_min), fmt_time(iv.end_min))
            for iv in intervals if iv.day == day and iv.lane == lane]


def test_grid_shape(parsed):
    grid, _ = parsed
    assert len(grid.col_x) == 66          # 6:00 … 22:00 по 15 минут + 22:20
    assert len(grid.day_rows) == 7


def test_free_intervals(parsed):
    _, busy = parsed
    ivs = free_intervals(busy)
    assert len(ivs) == 77
    assert by_day_lane(ivs, 0, 1) == [("7:30", "8:00"), ("21:30", "22:20")]
    assert by_day_lane(ivs, 0, 3) == [("7:30", "8:00"), ("16:15", "17:00"), ("18:45", "22:20")]
    assert by_day_lane(ivs, 0, 4) == [("6:00", "8:00"), ("16:15", "17:00"), ("18:45", "22:20")]
    assert by_day_lane(ivs, 1, 4) == [("6:00", "9:30"), ("17:45", "22:20")]
    assert by_day_lane(ivs, 3, 4) == [("7:00", "8:00"), ("13:15", "22:20")]
    assert by_day_lane(ivs, 5, 1) == [("7:30", "11:15"), ("13:30", "22:20")]
    assert by_day_lane(ivs, 2, 6) == [("6:00", "22:20")]
    # в воскресенье sportowy свободен целиком
    assert [(iv.lane, iv.start_min, iv.end_min) for iv in ivs if iv.day == 6] == \
        [(lane, 6 * 60, 22 * 60 + 20) for lane in range(1, 7)]


def test_merge_same_time(parsed):
    _, busy = parsed
    merged = merge_same_time(free_intervals(busy))
    assert len(merged) == 31
    tuesday = [(fmt_time(m.start_min), fmt_time(m.end_min), m.lanes) for m in merged if m.day == 1]
    assert tuesday == [("6:00", "9:30", [4]), ("7:30", "9:30", [1, 2, 3, 5, 6]),
                       ("17:45", "22:20", [1, 2, 3, 4, 5, 6])]
    # разное окончание — разные события, даже при общем начале
    monday_1615 = {(fmt_time(m.end_min), tuple(m.lanes)) for m in merged
                   if m.day == 0 and m.start_min == 16 * 60 + 15}
    assert monday_1615 == {("17:00", (3, 4)), ("22:20", (5, 6))}


def test_fmt_lanes():
    assert fmt_lanes([4]) == "дорожка 4"
    assert fmt_lanes([2, 3]) == "дорожки 2, 3"
    assert fmt_lanes([1, 2, 3, 5, 6]) == "дорожки 1–3, 5, 6"
    assert fmt_lanes([1, 2, 3, 4, 5, 6]) == "дорожки 1–6"


def test_calendar_single_events(parsed):
    _, busy = parsed
    merged = merge_same_time(free_intervals(busy))
    # с понедельника по понедельник: неделя целиком + понедельник ещё раз
    cal = build_calendar(merged, "sportowy", date(2026, 10, 19), date(2026, 10, 26))
    events = cal.walk("VEVENT")
    mondays = sum(1 for m in merged if m.day == 0)
    assert len(events) == len(merged) + mondays
    assert not any("RRULE" in ev for ev in events)
    assert len({str(ev["UID"]) for ev in events}) == len(events)
    starts = [ev.decoded("dtstart") for ev in events]
    assert min(starts).date() == date(2026, 10, 19)
    assert max(starts).date() == date(2026, 10, 26)
    assert events[0]["SUMMARY"] == "Sportowy · свободна дорожка 4"
    assert events[1]["SUMMARY"] == "Sportowy · свободны дорожки 1–3, 5, 6"
    assert all(ev["TRANSP"] == "TRANSPARENT" for ev in events)

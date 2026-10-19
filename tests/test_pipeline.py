"""Разбор страницы бассейна и сборка календаря из архива недель (без сети)."""

from datetime import date
from pathlib import Path

import pytest

from basen_kalendarz.events import SharedInterval
from basen_kalendarz.fetch import FetchError, find_schedule, parse_date_range
from basen_kalendarz.weeks import Week, build_feed, load_weeks, save_week

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("text, expected", [
    ("Rezerwacje pływalni w dniach 19-25.10.26 r.", (date(2026, 10, 19), date(2026, 10, 25))),
    ("Rezerwacje pływalni w dniach 19-25.10.2026 r.", (date(2026, 10, 19), date(2026, 10, 25))),
    ("w dniach 27.10-02.11.26 r.", (date(2026, 10, 27), date(2026, 11, 2))),
    ("w dniach 29.12.26 – 04.01.27", (date(2026, 12, 29), date(2027, 1, 4))),
    ("w dniach 29.12-04.01.27", (date(2026, 12, 29), date(2027, 1, 4))),
])
def test_parse_date_range(text, expected):
    assert parse_date_range(text) == expected


@pytest.mark.parametrize("text", ["Rezerwacje pływalni", "w dniach 25-19.10.26"])
def test_parse_date_range_rejects(text):
    with pytest.raises(FetchError):
        parse_date_range(text)


def test_find_schedule_on_real_page():
    title, urls, alt = find_schedule((FIXTURES / "rezerwacje.html").read_text(encoding="utf-8"))
    assert title == "Rezerwacje pływalni w dniach 19-25.10.26 r."
    assert alt == "Rezerwacje pływalni w dniach 19-25.10.2026 r."
    assert urls[0] == "/home/_processed_/5/1/csm_MP_72cdc03759.webp"     # desktop, 846 px
    assert len(urls) == 4


def test_find_schedule_without_block():
    with pytest.raises(FetchError):
        find_schedule("<html><h2>Aktualności</h2><img src='/x.jpg'></html>")


def _week(start: date, end: date, lanes: list[int]) -> Week:
    return Week(start, end, "sportowy", "t", "u", "now",
                [SharedInterval(day=d, start_min=480, end_min=540, lanes=lanes) for d in range(7)])


def test_weeks_roundtrip_and_feed(tmp_path):
    save_week(tmp_path, _week(date(2026, 10, 12), date(2026, 10, 18), [1]))
    save_week(tmp_path, _week(date(2026, 10, 19), date(2026, 10, 25), [2]))
    # период пересекается с соседними неделями: побеждает та, что начинается позже
    save_week(tmp_path, _week(date(2026, 10, 17), date(2026, 10, 20), [3]))
    weeks = load_weeks(tmp_path)
    assert [w.date_from for w in weeks] == [date(2026, 10, 12), date(2026, 10, 17), date(2026, 10, 19)]

    events = build_feed(weeks, "sportowy").walk("VEVENT")
    by_day = {ev.decoded("dtstart").date(): str(ev["SUMMARY"]) for ev in events}
    assert len(events) == len(by_day) == 14              # 12–25.10, по событию в день, без дублей
    assert by_day[date(2026, 10, 16)] == "Sportowy · свободна дорожка 1"
    assert by_day[date(2026, 10, 17)] == "Sportowy · свободна дорожка 3"
    assert by_day[date(2026, 10, 18)] == "Sportowy · свободна дорожка 3"
    assert by_day[date(2026, 10, 20)] == "Sportowy · свободна дорожка 2"
    assert by_day[date(2026, 10, 21)] == "Sportowy · свободна дорожка 2"

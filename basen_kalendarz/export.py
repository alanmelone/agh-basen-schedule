"""Выгрузка интервалов в JSON и iCalendar (.ics) для импорта или подписки в Google Calendar."""

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from .events import SharedInterval, fmt_lanes, fmt_time
from .grid import DAYS

TZ = ZoneInfo("Europe/Warsaw")


def write_json(intervals: list[SharedInterval], path: Path) -> None:
    data = [
        {**asdict(iv), "day_name": DAYS[iv.day],
         "start": fmt_time(iv.start_min), "end": fmt_time(iv.end_min)}
        for iv in intervals
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _at(day: date, minutes: int) -> datetime:
    return datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=TZ)


def new_calendar(pool: str) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//basen-kalendarz//PL")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", f"Basen {pool} — свободные дорожки")
    cal.add("x-wr-timezone", "Europe/Warsaw")
    return cal


def add_events(cal: Calendar, intervals: list[SharedInterval], pool: str,
               date_from: date, date_to: date, skip: set[date] = frozenset()) -> set[date]:
    """Отдельное (неповторяющееся) событие на каждую дату с date_from по date_to включительно.

    Даты из skip пропускаются. Возвращает даты, которые покрыл этот вызов.
    """
    by_weekday: dict[int, list[SharedInterval]] = {}
    for iv in intervals:
        by_weekday.setdefault(iv.day, []).append(iv)

    covered = set()
    stamp = datetime.now(timezone.utc).replace(microsecond=0)
    day = date_from
    while day <= date_to:
        if day in skip:
            day += timedelta(days=1)
            continue
        covered.add(day)
        for iv in by_weekday.get(day.weekday(), []):
            # UID зависит только от содержания, поэтому повторный импорт того же
            # расписания обновляет события, а не создаёт дубликаты.
            key = f"{pool}|wolne|{day}|{iv.lanes}|{iv.start_min}|{iv.end_min}"
            ev = Event()
            ev.add("uid", hashlib.sha1(key.encode()).hexdigest() + "@basen-kalendarz")
            ev.add("dtstamp", stamp)
            ev.add("dtstart", _at(day, iv.start_min))
            ev.add("dtend", _at(day, iv.end_min))
            free = "свободна" if len(iv.lanes) == 1 else "свободны"
            ev.add("summary", f"{pool.capitalize()} · {free} {fmt_lanes(iv.lanes)}")
            # свободная дорожка — справка, а не встреча: не помечает время как занятое
            ev.add("transp", "TRANSPARENT")
            cal.add_component(ev)
        day += timedelta(days=1)
    return covered


def build_calendar(intervals: list[SharedInterval], pool: str,
                   date_from: date, date_to: date) -> Calendar:
    """Календарь на один период с одним недельным расписанием."""
    cal = new_calendar(pool)
    add_events(cal, intervals, pool, date_from, date_to)
    cal.add_missing_timezones()
    return cal


def write_ics(cal: Calendar, path: Path) -> None:
    path.write_bytes(cal.to_ical())

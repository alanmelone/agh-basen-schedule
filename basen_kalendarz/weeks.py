"""Архив распознанных недель (data/weeks/<начало>.json) и сборка общего календаря из них."""

import json
from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path

from icalendar import Calendar

from .events import SharedInterval
from .export import add_events, new_calendar


@dataclass
class Week:
    date_from: date
    date_to: date
    pool: str
    title: str
    image_url: str
    fetched_at: str
    intervals: list[SharedInterval]


def save_week(directory: Path, week: Week) -> Path:
    """Пишет неделю в <directory>/<date_from>.json; повторный запуск перезаписывает тот же файл."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{week.date_from.isoformat()}.json"
    data = {**asdict(week), "date_from": week.date_from.isoformat(),
            "date_to": week.date_to.isoformat()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def load_weeks(directory: Path) -> list[Week]:
    names = {f.name for f in fields(SharedInterval)}
    weeks = []
    for path in sorted(directory.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        weeks.append(Week(
            date_from=date.fromisoformat(d["date_from"]),
            date_to=date.fromisoformat(d["date_to"]),
            pool=d["pool"],
            title=d["title"],
            image_url=d["image_url"],
            fetched_at=d["fetched_at"],
            intervals=[SharedInterval(**{k: v for k, v in iv.items() if k in names})
                       for iv in d["intervals"]],
        ))
    return weeks


def build_feed(weeks: list[Week], pool: str) -> Calendar:
    """Общий календарь из всех недель; при пересечении периодов побеждает неделя, начинающаяся позже."""
    cal = new_calendar(pool)
    covered: set[date] = set()
    for week in sorted(weeks, key=lambda w: w.date_from, reverse=True):
        if week.pool == pool:
            covered |= add_events(cal, week.intervals, pool, week.date_from, week.date_to, covered)
    cal.add_missing_timezones()
    return cal

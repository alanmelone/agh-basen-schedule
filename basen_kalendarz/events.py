"""Склейка свободных слотов каждой дорожки в интервалы."""

from dataclasses import dataclass

import numpy as np

from .grid import SLOT_BOUNDS_MIN


@dataclass
class LaneInterval:
    day: int          # 0 = понедельник
    lane: int         # номер дорожки, с 1
    start_min: int    # минуты от полуночи
    end_min: int


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Непрерывные отрезки True в виде [начальный слот, конечный слот)."""
    padded = np.concatenate([[False], mask, [False]])
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


@dataclass
class SharedInterval:
    """Одинаковый отрезок времени, свободный на нескольких дорожках."""
    day: int
    start_min: int
    end_min: int
    lanes: list[int]


def merge_same_time(intervals: list[LaneInterval]) -> list[SharedInterval]:
    """Объединяет отрезки разных дорожек с одинаковыми днём, началом и концом."""
    groups: dict[tuple[int, int, int], list[int]] = {}
    for iv in intervals:
        groups.setdefault((iv.day, iv.start_min, iv.end_min), []).append(iv.lane)
    return [
        SharedInterval(day=day, start_min=start, end_min=end, lanes=sorted(lanes))
        for (day, start, end), lanes in sorted(groups.items())
    ]


def fmt_lanes(lanes: list[int]) -> str:
    """[1, 2, 3, 5, 6] → «дорожки 1–3, 5, 6»; [4] → «дорожка 4»."""
    parts, i = [], 0
    while i < len(lanes):
        j = i
        while j + 1 < len(lanes) and lanes[j + 1] == lanes[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f"{lanes[i]}–{lanes[j]}")
        else:
            parts.extend(str(n) for n in lanes[i:j + 1])
        i = j + 1
    return ("дорожка " if len(lanes) == 1 else "дорожки ") + ", ".join(parts)


def free_intervals(busy: np.ndarray) -> list[LaneInterval]:
    """Свободные интервалы по дорожкам; busy — матрица [день, дорожка, слот] из occupancy()."""
    t = SLOT_BOUNDS_MIN
    return [
        LaneInterval(day=day, lane=lane + 1, start_min=t[s0], end_min=t[s1])
        for day, day_busy in enumerate(busy)
        for lane, lane_busy in enumerate(day_busy)
        for s0, s1 in _runs(~lane_busy)
    ]


def fmt_time(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"

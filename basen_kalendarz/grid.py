"""Распознавание сетки расписания: колонки времени, блоки дней и строки дорожек.

Ожидаемая вёрстка (экспорт из Excel):
- дни разделены сплошными горизонтальными линиями на всю ширину;
- в каждом дне строка-шапка с часами и 15 строк дорожек:
  6 sportowy + 6 szkoleniowy + 3 rekreacyjny;
- колонки по 15 минут с 6:00 до 22:00 и последняя колонка 22:00–22:20.
"""

from dataclasses import dataclass

import numpy as np

DAYS = ["PON", "WT", "ŚR", "CZW", "PT", "SB", "ND"]
ROWS_PER_DAY = 15
POOLS = {
    "sportowy": range(0, 6),
    "szkoleniowy": range(6, 12),
    "rekreacyjny": range(12, 15),
}

# Границы колонок в минутах от полуночи: 6:00, 6:15, ..., 22:00, 22:20.
SLOT_BOUNDS_MIN = [6 * 60 + 15 * i for i in range(65)] + [22 * 60 + 20]

# Пороги подобраны под картинку ~846 px шириной (колонка ~12 px, строка ~21 px).
LINE_CONTRAST = 30      # насколько линия темнее пикселей в 2 px от неё
LINE_MIN_SHARE = 0.3    # доля длины, на которой линия должна быть видна
# Вертикальные линии часто перекрыты цветными блоками (утро почти всё закрашено),
# поэтому порог ниже; шум внутри сетки не поднимается выше ~0.1.
COL_LINE_MIN_SHARE = 0.2
COL_GAP = (10, 14)      # шаг регулярных 15-минутных колонок, px
ROW_GAP = (17, 25)      # высота строки дорожки, px


class GridError(Exception):
    """Сетка не совпала с ожидаемой вёрсткой — парсить такую картинку нельзя."""


@dataclass
class Grid:
    col_x: list[int]            # x-границы колонок, len == len(SLOT_BOUNDS_MIN)
    day_rows: list[list[int]]   # для каждого дня y-границы 15 строк (16 значений)

    @property
    def slots(self) -> int:
        return len(self.col_x) - 1


def _line_profile(gray: np.ndarray, axis: int) -> np.ndarray:
    """Доля пикселей вдоль каждой линии, которые темнее обоих соседей в 2 px.

    axis=1 — ищем вертикальные линии (профиль по x), axis=0 — горизонтальные.
    Тонкая линия сетки темнее соседей с обеих сторон, а край цветного блока —
    только с одной, поэтому края блоков в профиль почти не попадают.
    """
    g = gray.astype(np.int16)
    neighbours = np.minimum(np.roll(g, 2, axis=axis), np.roll(g, -2, axis=axis))
    mask = g < neighbours - LINE_CONTRAST
    return mask.mean(axis=1 - axis)


def _peaks(profile: np.ndarray, threshold: float) -> list[int]:
    """Позиции линий: по одной (самой сильной) на каждый кластер соседних пикселей."""
    idx = np.flatnonzero(profile > threshold)
    peaks: list[int] = []
    cluster: list[int] = []
    for i in idx:
        if cluster and i - cluster[-1] > 2:
            peaks.append(max(cluster, key=lambda j: profile[j]))
            cluster = []
        cluster.append(int(i))
    if cluster:
        peaks.append(max(cluster, key=lambda j: profile[j]))
    return peaks


def _day_separators(gray: np.ndarray) -> list[int]:
    """Сплошные тёмные линии на всю ширину — границы дней (верх каждого дня + низ последнего)."""
    # Линии почти чёрные; насыщенный красный блок на весь день в сером даёт ~60–80.
    full = np.flatnonzero((gray < 40).mean(axis=1) > 0.9)
    seps: list[int] = []
    for y in full:
        if not seps or y - seps[-1] > 2:
            seps.append(int(y))
    if len(seps) < len(DAYS) + 1:
        raise GridError(f"найдено {len(seps)} разделителей дней, нужно {len(DAYS) + 1}")
    return seps[: len(DAYS) + 1]


def _columns(gray: np.ndarray, top: int, bottom: int) -> list[int]:
    profile = _line_profile(gray[top:bottom], axis=1)
    lines = _peaks(profile, COL_LINE_MIN_SHARE)

    # 6:00 — начало самой длинной серии колонок с регулярным шагом.
    best_start, best_len, start = 0, 0, 0
    for i in range(1, len(lines) + 1):
        if i == len(lines) or not COL_GAP[0] <= lines[i] - lines[i - 1] <= COL_GAP[1]:
            if i - start > best_len:
                best_start, best_len = start, i - start
            start = i
    cols = lines[best_start : best_start + len(SLOT_BOUNDS_MIN)]
    if len(cols) != len(SLOT_BOUNDS_MIN):
        raise GridError(f"найдено {len(cols)} границ колонок от 6:00, нужно {len(SLOT_BOUNDS_MIN)}")
    return cols


def _rows(gray: np.ndarray, x0: int, x1: int, top: int, bottom: int) -> list[int]:
    """Границы 15 строк дорожек одного дня (между разделителями top и bottom)."""
    profile = _line_profile(gray[:, x0:x1], axis=0)
    lines = [y for y in _peaks(profile, LINE_MIN_SHARE) if top + 3 < y < bottom - 3]
    # Над дорожками только шапка с подписями часов, поэтому берём последние 15 линий:
    # нижняя граница шапки + 14 границ между дорожками, низ дня — сам разделитель.
    rows = lines[-ROWS_PER_DAY:] + [bottom]
    gaps = np.diff(rows)
    if len(rows) != ROWS_PER_DAY + 1 or not all(ROW_GAP[0] <= g <= ROW_GAP[1] for g in gaps):
        raise GridError(f"строки дня {top}–{bottom} не совпали с вёрсткой: {rows}")
    return rows


def detect_grid(gray: np.ndarray) -> Grid:
    seps = _day_separators(gray)
    cols = _columns(gray, seps[0], seps[-1])
    day_rows = [_rows(gray, cols[0], cols[-1], a, b) for a, b in zip(seps, seps[1:])]
    return Grid(col_x=cols, day_rows=day_rows)

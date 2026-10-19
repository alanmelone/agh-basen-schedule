"""Занятость ячеек: любая заливка, кроме белой, означает «дорожка занята»."""

import numpy as np

from .grid import Grid

CELL_MARGIN = 3        # отступ от линий сетки внутрь ячейки, px
# Минимальный канал медианного цвета: у пустых ячеек ≥ 250, у самых бледных
# заливок (Aqua Fitness, HOPE) ≈ 200–210, промежуток между ними пуст.
WHITE_MIN_CHANNEL = 230


def occupancy(img_bgr: np.ndarray, grid: Grid, lanes: range) -> np.ndarray:
    """Матрица [день, дорожка, слот] → True, если ячейка закрашена."""
    busy = np.zeros((len(grid.day_rows), len(lanes), grid.slots), dtype=bool)
    m = CELL_MARGIN
    for d, rows in enumerate(grid.day_rows):
        for li, lane in enumerate(lanes):
            y0, y1 = rows[lane] + m, rows[lane + 1] - m + 1
            for s in range(grid.slots):
                x0, x1 = grid.col_x[s] + m, grid.col_x[s + 1] - m + 1
                # медиана устойчива к подписям (AGH, JŻ…) и артефактам сжатия
                color = np.median(img_bgr[y0:y1, x0:x1].reshape(-1, 3), axis=0)
                busy[d, li, s] = color.min() < WHITE_MIN_CHANNEL
    return busy

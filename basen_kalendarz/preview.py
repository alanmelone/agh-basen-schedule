"""Превью для глазной проверки: распознанные занятые ячейки поверх исходной картинки."""

import cv2
import numpy as np

from .grid import Grid

MARK_BGR = (255, 0, 255)   # пурпурный — не встречается в легенде расписания


def render_preview(img_bgr: np.ndarray, grid: Grid, lanes: range, busy: np.ndarray) -> np.ndarray:
    out = img_bgr.copy()
    for d, rows in enumerate(grid.day_rows):
        # рамка проверяемого бассейна
        cv2.rectangle(out, (grid.col_x[0], rows[lanes.start]),
                      (grid.col_x[-1], rows[lanes.stop]), (0, 160, 0), 2)
        for li, lane in enumerate(lanes):
            y0, y1 = rows[lane], rows[lane + 1]
            for s in np.flatnonzero(busy[d, li]):
                x0, x1 = grid.col_x[s], grid.col_x[s + 1]
                # крестик в центре занятой ячейки: цвет под ним остаётся виден
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                cv2.line(out, (cx - 3, cy - 3), (cx + 3, cy + 3), MARK_BGR, 2)
                cv2.line(out, (cx - 3, cy + 3), (cx + 3, cy - 3), MARK_BGR, 2)
    return out

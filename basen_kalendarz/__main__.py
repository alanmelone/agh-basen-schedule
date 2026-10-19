"""CLI: картинка с расписанием → events.json, kalendarz.ics, podglad.png.

    python -m basen_kalendarz data/grafik.webp --od 2026-10-19 --do 2026-10-25
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import cv2

from .events import free_intervals, fmt_lanes, fmt_time, merge_same_time
from .export import build_calendar, write_ics, write_json
from .grid import DAYS, POOLS, GridError, detect_grid
from .occupancy import occupancy
from .preview import render_preview


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="basen_kalendarz", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", type=Path, help="картинка с расписанием (png/jpg/webp)")
    p.add_argument("--basen", choices=POOLS, default="sportowy")
    p.add_argument("--od", type=date.fromisoformat, default=date.today(),
                   help="первый день, YYYY-MM-DD (по умолчанию сегодня)")
    p.add_argument("--do", type=date.fromisoformat, default=None,
                   help="последний день включительно, YYYY-MM-DD (по умолчанию неделя от --od)")
    p.add_argument("--out", type=Path, default=Path("out"), help="папка для результатов")
    args = p.parse_args(argv)
    date_to = args.do or args.od + timedelta(days=6)
    if date_to < args.od:
        p.error("--do раньше, чем --od")

    img = cv2.imread(str(args.image))
    if img is None:
        print(f"не удалось прочитать картинку: {args.image}", file=sys.stderr)
        return 1
    try:
        grid = detect_grid(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    except GridError as e:
        print(f"сетка не распознана: {e}", file=sys.stderr)
        return 2

    lanes = POOLS[args.basen]
    busy = occupancy(img, grid, lanes)
    intervals = merge_same_time(free_intervals(busy))

    args.out.mkdir(parents=True, exist_ok=True)
    write_json(intervals, args.out / "events.json")
    cal = build_calendar(intervals, args.basen, args.od, date_to)
    write_ics(cal, args.out / "kalendarz.ics")
    cv2.imwrite(str(args.out / "podglad.png"), render_preview(img, grid, lanes, busy))

    for iv in intervals:
        print(f"{DAYS[iv.day]:>4}  {fmt_time(iv.start_min):>5}–{fmt_time(iv.end_min):<5}  "
              f"{fmt_lanes(iv.lanes)}")
    print(f"\n{len(intervals)} интервалов в неделю, {len(cal.walk('VEVENT'))} событий "
          f"с {args.od} по {date_to}; результаты в {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

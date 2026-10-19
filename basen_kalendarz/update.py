"""Еженедельный пайплайн: страница бассейна → картинка → распознавание → архив недель → сайт с .ics.

    python -m basen_kalendarz.update --weeks data/weeks --site site --work work
"""

import argparse
import html
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2

from .events import free_intervals, fmt_lanes, fmt_time, merge_same_time
from .export import write_ics
from .fetch import PAGE_URL, FetchError, fetch_schedule
from .grid import DAYS, POOLS, GridError, detect_grid
from .occupancy import occupancy
from .preview import render_preview
from .weeks import Week, build_feed, load_weeks, save_week


def _index_html(pool: str, weeks: list[Week], ics_name: str) -> str:
    latest = max(weeks, key=lambda w: w.date_from)
    rows = "\n".join(
        f"<li>{w.date_from:%d.%m.%Y} — {w.date_to:%d.%m.%Y}</li>"
        for w in sorted(weeks, key=lambda w: w.date_from, reverse=True)
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Basen {pool}</title>
<style>
  body {{ font: 16px/1.5 system-ui, sans-serif; max-width: 46rem; margin: 2rem auto; padding: 0 1rem;
         color: #1d1d1f; background: #fff; }}
  code {{ background: #f2f2f2; padding: .1rem .3rem; border-radius: 4px; word-break: break-all; }}
  img {{ max-width: 100%; border: 1px solid #ddd; }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e8e8e8; background: #161616; }} code {{ background: #2a2a2a; }}
  }}
</style>
</head>
<body>
<h1>Basen {pool} — свободные дорожки</h1>
<p>Календарь: <a href="{ics_name}"><code id="url">{ics_name}</code></a></p>
<p>Proton Calendar: «+» рядом с календарями → <i>Add calendar from URL</i> → вставить эту ссылку.</p>
<p>Последнее расписание: <b>{html.escape(latest.title)}</b>, загружено {latest.fetched_at}
   (<a href="{html.escape(latest.image_url)}">исходная картинка</a>).</p>
<p>Распознанные занятые ячейки отмечены крестиками, всё остальное считается свободным:</p>
<p><a href="podglad.webp"><img src="podglad.webp" alt="Превью распознавания"></a></p>
<h2>Недели в календаре</h2>
<ul>
{rows}
</ul>
<script>
  document.getElementById("url").textContent = new URL("{ics_name}", location.href).href;
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="basen_kalendarz.update", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=PAGE_URL, help="страница с расписанием")
    p.add_argument("--basen", choices=POOLS, default="sportowy")
    p.add_argument("--weeks", type=Path, default=Path("data/weeks"), help="архив распознанных недель")
    p.add_argument("--site", type=Path, default=Path("site"), help="папка сайта для GitHub Pages")
    p.add_argument("--work", type=Path, default=Path("work"), help="картинка и превью этого запуска")
    args = p.parse_args(argv)

    try:
        schedule = fetch_schedule(args.url)
        grid = detect_grid(cv2.cvtColor(schedule.image, cv2.COLOR_BGR2GRAY))
    except (FetchError, GridError, OSError) as e:
        print(f"ошибка: {e}", file=sys.stderr)
        return 1

    lanes = POOLS[args.basen]
    busy = occupancy(schedule.image, grid, lanes)
    intervals = merge_same_time(free_intervals(busy))
    week = Week(
        date_from=schedule.date_from,
        date_to=schedule.date_to,
        pool=args.basen,
        title=schedule.title,
        image_url=schedule.image_url,
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        intervals=intervals,
    )
    week_path = save_week(args.weeks, week)

    args.work.mkdir(parents=True, exist_ok=True)
    preview = render_preview(schedule.image, grid, lanes, busy)
    cv2.imwrite(str(args.work / f"{week.date_from}-grafik.png"), schedule.image)
    cv2.imwrite(str(args.work / f"{week.date_from}-podglad.png"), preview)

    weeks = load_weeks(args.weeks)
    ics_name = f"{args.basen}.ics"
    args.site.mkdir(parents=True, exist_ok=True)
    write_ics(build_feed(weeks, args.basen), args.site / ics_name)
    cv2.imwrite(str(args.site / "podglad.webp"), preview, [cv2.IMWRITE_WEBP_QUALITY, 85])
    (args.site / "index.html").write_text(_index_html(args.basen, weeks, ics_name), encoding="utf-8")

    print(f"{schedule.title}: {week.date_from} — {week.date_to}")
    print(f"картинка: {schedule.image_url} ({schedule.image.shape[1]}×{schedule.image.shape[0]})")
    for iv in intervals:
        print(f"{DAYS[iv.day]:>4}  {fmt_time(iv.start_min):>5}–{fmt_time(iv.end_min):<5}  "
              f"{fmt_lanes(iv.lanes)}")
    print(f"неделя сохранена в {week_path}; календарь из {len(weeks)} недель → {args.site / ics_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

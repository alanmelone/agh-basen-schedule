"""Загрузка текущего расписания со страницы бассейна AGH: даты недели и картинка."""

import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin

import cv2
import numpy as np

PAGE_URL = "https://basen.agh.edu.pl/plywalnia/rezerwacje"
USER_AGENT = "Mozilla/5.0 (compatible; basen-kalendarz)"
TIMEOUT = 30

# «19-25.10.26», «19-25.10.2026», «27.10-02.11.26», «29.12.26-04.01.27»
DATE_RANGE = re.compile(
    r"(\d{1,2})(?:\.(\d{1,2}))?(?:\.(\d{4}|\d{2}))?\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?!\d)"
)


class FetchError(Exception):
    """На странице не нашлось ожидаемого заголовка с датами или картинки."""


@dataclass
class Schedule:
    date_from: date
    date_to: date
    title: str
    image_url: str
    image: np.ndarray        # BGR, самый крупный из вариантов картинки


def _year(text: str) -> int:
    return int(text) if len(text) == 4 else 2000 + int(text)


def parse_date_range(text: str) -> tuple[date, date]:
    m = DATE_RANGE.search(text)
    if not m:
        raise FetchError(f"не нашёл диапазон дат в «{text}»")
    d1, m1, y1, d2, m2, y2 = m.groups()
    date_to = date(_year(y2), int(m2), int(d2))
    date_from = date(_year(y1) if y1 else date_to.year, int(m1 or m2), int(d1))
    if date_from > date_to and not y1:      # «29.12-04.01.27»: начало в прошлом году
        date_from = date_from.replace(year=date_to.year - 1)
    if not 0 <= (date_to - date_from).days <= 31:
        raise FetchError(f"странный диапазон дат в «{text}»: {date_from} — {date_to}")
    return date_from, date_to


class _PageParser(HTMLParser):
    """Собирает заголовки h2 и картинки (все варианты из <picture>) в порядке документа."""

    def __init__(self):
        super().__init__()
        self.items: list[tuple[str, object]] = []   # ("h2", текст) | ("picture", [url, ...])
        self._h2: list[str] | None = None
        self._picture: list[str] | None = None
        self._alt = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h2":
            self._h2 = []
        elif tag == "picture":
            self._picture = []
        elif tag == "source" and self._picture is not None and a.get("srcset"):
            # srcset вида «/path.webp 1x» — берём только адрес
            self._picture.append(a["srcset"].split()[0])
        elif tag == "img" and a.get("src"):
            if self._picture is not None:
                self._picture.append(a["src"])
                self._alt = a.get("alt") or ""
            else:
                self.items.append(("picture", ([a["src"]], a.get("alt") or "")))

    def handle_endtag(self, tag):
        if tag == "h2" and self._h2 is not None:
            self.items.append(("h2", " ".join("".join(self._h2).split())))
            self._h2 = None
        elif tag == "picture" and self._picture is not None:
            self.items.append(("picture", (self._picture, self._alt)))
            self._picture, self._alt = None, ""

    def handle_data(self, data):
        if self._h2 is not None:
            self._h2.append(data)


def find_schedule(html: str) -> tuple[str, list[str], str]:
    """(заголовок, варианты картинки, alt) для блока «Rezerwacje pływalni w dniach …»."""
    parser = _PageParser()
    parser.feed(html)
    title = None
    for kind, value in parser.items:
        if kind == "h2" and "w dniach" in value:
            title = value
        elif kind == "picture" and title is not None:
            urls, alt = value
            return title, urls, alt
    raise FetchError("на странице нет блока «Rezerwacje pływalni w dniach …» с картинкой")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def fetch_schedule(page_url: str = PAGE_URL) -> Schedule:
    html = _get(page_url).decode("utf-8", errors="replace")
    title, urls, alt = find_schedule(html)
    try:
        date_from, date_to = parse_date_range(title)
    except FetchError:
        date_from, date_to = parse_date_range(alt)

    # Варианты для разных экранов отличаются размером; парсеру нужен самый крупный.
    best_url, best = None, None
    for url in dict.fromkeys(urljoin(page_url, u) for u in urls):
        img = cv2.imdecode(np.frombuffer(_get(url), np.uint8), cv2.IMREAD_COLOR)
        if img is not None and (best is None or img.shape[1] > best.shape[1]):
            best_url, best = url, img
    if best is None:
        raise FetchError(f"не удалось скачать картинку расписания: {urls}")
    return Schedule(date_from, date_to, title, best_url, best)

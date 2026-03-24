import re
import threading
import time
from datetime import datetime, timedelta

from core.search import (
    SearchResult,
    switch_layout,
    EN_TO_RU,
    RU_TO_EN,
    _notify,
    _play_sound,
)

_sw_lock = threading.Lock()
_sw_start: float | None = None


def _parse_duration(text: str) -> int:
    text = text.strip().lower()
    total = 0
    for m in re.finditer(r"(\d+)\s*([a-zа-яё]+)", text):
        num = int(m.group(1))
        unit = m.group(2)
        if unit in ("s", "sec", "сек", "секунд", "секунды", "секунда", "с"):
            total += num
        elif unit in (
            "m", "min", "мин", "минут", "минуты", "минута", "м",
        ):
            total += num * 60
        elif unit in (
            "h", "hr", "hour", "hours", "ч", "час", "часа", "часов",
        ):
            total += num * 3600
    if total == 0 and re.fullmatch(r"\d+", text):
        total = int(text) * 60
    return total


def _fmt_sw(s: int) -> str:
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    if s >= 60:
        return f"{s // 60}:{s % 60:02d}"
    return f"{s} с"


def stopwatch_elapsed_secs() -> int | None:
    with _sw_lock:
        if _sw_start is None:
            return None
        return int(time.monotonic() - _sw_start)


def _stopwatch_start():
    global _sw_start
    with _sw_lock:
        _sw_start = time.monotonic()
    _notify("Секундомер", "Старт", "chronometer")


def _stopwatch_lap_notify():
    e = stopwatch_elapsed_secs()
    if e is None:
        _notify("Секундомер", "Ещё не запущен — Enter для старта", "dialog-information")
        return
    _notify("Секундомер", _fmt_sw(e), "chronometer")


def _stopwatch_reset():
    global _sw_start
    with _sw_lock:
        _sw_start = None
    _notify("Секундомер", "Сброшен", "chronometer")


def _stopwatch_stop():
    global _sw_start
    with _sw_lock:
        e = None if _sw_start is None else int(time.monotonic() - _sw_start)
        _sw_start = None
    if e is not None:
        _notify("Секундомер остановлен", _fmt_sw(e), "chronometer")
    else:
        _notify("Секундомер", "Не был запущен", "dialog-information")


def _split_leading_duration(s: str) -> tuple[int, str] | None:
    s = s.strip()
    total = 0
    pos = 0
    pattern = re.compile(r"^\s*(\d+)\s*([a-zа-яё]+)")
    while pos < len(s):
        m = pattern.match(s, pos)
        if not m:
            break
        chunk = f"{m.group(1)} {m.group(2)}"
        one = _parse_duration(chunk)
        if one <= 0:
            break
        total += one
        pos = m.end()
    rest = s[pos:].strip()
    if total > 0:
        return total, rest or "Напоминание"
    if re.fullmatch(r"\d+", s):
        total = int(s) * 60
        return total, "Напоминание"
    return None


def _fire_timer(title: str, message: str):
    _play_sound()
    _notify(title, message, "alarm-symbolic", "critical")


class TimerRunner:
    _ALARM_RE = re.compile(r"^(\d{1,2})[.:](\d{2})\s*(.*)", re.I)

    def match(self, query: str) -> list[SearchResult]:
        q = query.strip()
        for variant in (q, switch_layout(q, EN_TO_RU), switch_layout(q, RU_TO_EN)):
            sw = self._match_stopwatch(variant)
            if sw:
                return sw
            rem = self._match_remind_through(variant)
            if rem:
                return rem

            m = self._ALARM_RE.match(variant)
            if m:
                h, mn = int(m.group(1)), int(m.group(2))
                msg = m.group(3).strip() or "Будильник"
                target = datetime.now().replace(hour=h, minute=mn, second=0, microsecond=0)
                if target < datetime.now():
                    target += timedelta(days=1)
                s = int((target - datetime.now()).total_seconds())
                return [
                    SearchResult(
                        title=f"Будильник на {h}:{mn:02d}",
                        subtitle=f"{msg} — через {self._fmt(s)}",
                        icon_name="alarm-symbolic",
                        score=1.0,
                        category="Таймер",
                        action=lambda s=s, ms=msg: self._set(s, "Будильник", ms),
                    )
                ]

            m = re.match(
                r"^([\d]+\s*[a-zа-яё]+(?:\s+\d+\s*[a-zа-яё]+)*)\s+(.+)",
                variant,
            )
            if m:
                time_str = m.group(1)
                msg = m.group(2).strip() or "Напоминание"
                s = _parse_duration(time_str)
                if s > 0:
                    return [
                        SearchResult(
                            title=f"Напомнить через {self._fmt(s)}",
                            subtitle=msg,
                            icon_name="appointment-soon",
                            score=1.0,
                            category="Таймер",
                            action=lambda s=s, ms=msg: self._set(s, "Напоминание", ms),
                        )
                    ]

            s = _parse_duration(variant)
            if s > 0:
                return [
                    SearchResult(
                        title=f"Таймер на {self._fmt(s)}",
                        subtitle="Enter — запустить",
                        icon_name="chronometer",
                        score=1.0,
                        category="Таймер",
                        action=lambda s=s: self._set(s, "Таймер", f"Таймер на {self._fmt(s)}"),
                    )
                ]
        return []

    def _match_remind_through(self, variant: str) -> list[SearchResult] | None:
        v = variant.strip()
        m = re.match(
            r"^(?:напомни(?:ть)?|remind(?:\s+me)?)\s+через\s+(.+)$",
            v,
            re.I,
        )
        rest = None
        if m:
            rest = m.group(1).strip()
        else:
            m2 = re.match(r"^через\s+(.+)$", v, re.I)
            if m2:
                rest = m2.group(1).strip()
        if not rest:
            return None
        sp = _split_leading_duration(rest)
        if not sp:
            return None
        secs, msg = sp
        if secs <= 0:
            return None
        return [
            SearchResult(
                title=f"Напомнить через {self._fmt(secs)}",
                subtitle=msg[:120],
                icon_name="appointment-soon",
                score=1.0,
                category="Таймер",
                action=lambda s=secs, ms=msg: self._set(s, "Напоминание", ms),
            )
        ]

    def _match_stopwatch(self, variant: str) -> list[SearchResult] | None:
        low = re.sub(r"\s+", " ", variant.strip().lower()).strip()
        if low in (
            "секундомер сброс",
            "stopwatch reset",
            "reset stopwatch",
        ):
            return [
                SearchResult(
                    title="Секундомер — сброс",
                    subtitle="Enter — обнулить",
                    icon_name="chronometer",
                    score=1.0,
                    category="Таймер",
                    action=lambda: _stopwatch_reset(),
                )
            ]
        if low in (
            "секундомер стоп",
            "stopwatch stop",
        ):
            return [
                SearchResult(
                    title="Секундомер — стоп",
                    subtitle="Enter — остановить и показать время",
                    icon_name="chronometer",
                    score=1.0,
                    category="Таймер",
                    action=lambda: _stopwatch_stop(),
                )
            ]
        if low in ("секундомер", "stopwatch", "sw"):
            e = stopwatch_elapsed_secs()
            if e is None:
                return [
                    SearchResult(
                        title="Секундомер — старт",
                        subtitle="Enter — запустить · потом снова «секундомер» — показать время",
                        icon_name="chronometer",
                        score=1.0,
                        category="Таймер",
                        action=lambda: _stopwatch_start(),
                    )
                ]
            return [
                SearchResult(
                    title=f"Секундомер: {_fmt_sw(e)}",
                    subtitle="Enter — уведомить время · «секундомер стоп» · «секундомер сброс»",
                    icon_name="chronometer",
                    score=1.0,
                    category="Таймер",
                    action=lambda: _stopwatch_lap_notify(),
                )
            ]
        return None

    @staticmethod
    def _fmt(s: int) -> str:
        if s >= 3600:
            return f"{s // 3600}ч {s % 3600 // 60}м"
        if s >= 60:
            return f"{s // 60}м {s % 60}с" if s % 60 else f"{s // 60}м"
        return f"{s}с"

    @staticmethod
    def _set(secs: int, title: str, msg: str):
        _notify("Запущено", f"{title}: {msg}", "chronometer")
        t = threading.Timer(secs, _fire_timer, args=(title, msg))
        t.daemon = True
        t.start()


RUNNERS = [TimerRunner()]

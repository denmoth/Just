"""Media keys via playerctl (MPRIS)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

from core.search import SearchResult, smart_score, switch_layout, EN_TO_RU, RU_TO_EN, _run_cmd

_LOG = logging.getLogger("just.media")


def _playerctl_available() -> bool:
    return shutil.which("playerctl") is not None


def _pc(*args: str, timeout: float = 3.0) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["playerctl", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (r.stdout or "").strip()
        if r.returncode != 0 and r.stderr:
            _LOG.debug("playerctl %s: stderr=%s", args, r.stderr.strip())
        return r.returncode, out
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        _LOG.debug("playerctl timeout: %s", args)
        return 124, ""


def _now_playing_text() -> Optional[str]:
    if not _playerctl_available():
        return None
    st, status = _pc("status", "-f", "{{status}}")
    if st != 0:
        return None
    _, artist = _pc("metadata", "artist")
    _, title = _pc("metadata", "title")
    parts = [p for p in (artist, title) if p]
    if not parts:
        return status or "—"
    return f"{status}: {' — '.join(parts)}"


class MediaRunner:
    """play / pause / next / previous / stop / now playing."""

    _ACTIONS: list[dict] = [
        {
            "triggers": [
                "play-pause", "play pause", "пауза", "паузить", "плей пауза",
                "toggle pause", "переключить паузу",
            ],
            "title": "Медиа: пауза / продолжить",
            "sub": "playerctl play-pause",
            "icon": "media-playback-pause-symbolic",
            "cmd": ["play-pause"],
        },
        {
            "triggers": ["play", "воспроизвести", "продолжить", "дальше", "старт трек"],
            "title": "Медиа: воспроизведение",
            "sub": "playerctl play",
            "icon": "media-playback-start-symbolic",
            "cmd": ["play"],
        },
        {
            "triggers": ["pause", "остановить музыку", "приостановить"],
            "title": "Медиа: пауза",
            "sub": "playerctl pause",
            "icon": "media-playback-pause-symbolic",
            "cmd": ["pause"],
        },
        {
            "triggers": ["stop", "стоп", "остановить плеер"],
            "title": "Медиа: стоп",
            "sub": "playerctl stop",
            "icon": "media-playback-stop-symbolic",
            "cmd": ["stop"],
        },
        {
            "triggers": ["next", "следующий", "след трек", "вперёд", "вперед", "skip"],
            "title": "Медиа: следующий трек",
            "sub": "playerctl next",
            "icon": "media-skip-forward-symbolic",
            "cmd": ["next"],
        },
        {
            "triggers": ["previous", "prev", "предыдущий", "назад", "пред трек"],
            "title": "Медиа: предыдущий трек",
            "sub": "playerctl previous",
            "icon": "media-skip-backward-symbolic",
            "cmd": ["previous"],
        },
    ]

    _INFO_TRIGGERS = [
        "что играет", "что сейчас играет", "now playing",
        "текущий трек", "сейчас в плеере", "плеер что", "музыка что",
    ]

    def match(self, query: str) -> list[SearchResult]:
        q = query.lower().strip()
        if len(q) < 2:
            return []

        if not _playerctl_available():
            best = 0.0
            for t in ("музыка", "плеер", "playerctl", "пауза", "next", "трек"):
                for v in (q, switch_layout(q, EN_TO_RU), switch_layout(q, RU_TO_EN)):
                    best = max(best, smart_score(v, t))
            if best > 0.45:
                return [
                    SearchResult(
                        title="Медиа: установите playerctl",
                        subtitle="Например: pacman -S playerctl  (MPRIS)",
                        icon_name="dialog-information-symbolic",
                        score=min(best, 0.7),
                        category="Медиа",
                        action=None,
                    ),
                ]
            return []

        results: list[SearchResult] = []

        info_best = 0.0
        for trig in self._INFO_TRIGGERS:
            for v in (q, switch_layout(q, EN_TO_RU), switch_layout(q, RU_TO_EN)):
                info_best = max(info_best, smart_score(v, trig.strip()))

        if info_best > 0.42:
            sub = _now_playing_text() or "Нет активного плеера (MPRIS)"
            results.append(
                SearchResult(
                    title="Сейчас играет",
                    subtitle=sub,
                    icon_name="audio-headphones-symbolic",
                    score=info_best,
                    category="Медиа",
                    action=None,
                    usage_key="media:nowplaying",
                ),
            )

        for row in self._ACTIONS:
            best = 0.0
            for trig in row["triggers"]:
                for v in (q, switch_layout(q, EN_TO_RU), switch_layout(q, RU_TO_EN)):
                    best = max(best, smart_score(v, trig))
            if best > 0.38:
                cmd = row["cmd"]

                def _act(c: list[str] = cmd) -> None:
                    _run_cmd(["playerctl", *c])

                results.append(
                    SearchResult(
                        title=row["title"],
                        subtitle=row["sub"],
                        icon_name=row["icon"],
                        score=best,
                        category="Медиа",
                        action=_act,
                        usage_key=f"media:{cmd[0]}",
                    ),
                )

        results.sort(key=lambda r: -r.score)
        return results[:6]


RUNNERS = [MediaRunner()]

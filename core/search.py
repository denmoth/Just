import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Optional

from core.config import APP_NAME

# ── Keyboard Layout ──

_EN = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./~QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?"
_RU = "ёйцукенгшщзхъфывапролджэячсмитьбю.ЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,"

EN_TO_RU: dict = dict(zip(_EN, _RU))
RU_TO_EN: dict = dict(zip(_RU, _EN))


def switch_layout(text: str, mapping: dict) -> str:
    return "".join(mapping.get(c, c) for c in text)


# ── Fuzzy Search ──

def levenshtein(a: str, b: str, limit: int = -1) -> int:
    la, lb = len(a), len(b)
    if la < lb:
        return levenshtein(b, a, limit)
    if limit >= 0 and (la - lb) > limit:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(
                prev[j + 1] + 1,
                curr[j] + 1,
                prev[j] + (0 if ca == cb else 1),
            ))
        prev = curr
    return prev[-1]


def trigram_sim(a: str, b: str) -> float:
    if len(a) < 3 or len(b) < 3:
        return 0.0
    ta = {a[i:i + 3] for i in range(len(a) - 2)}
    tb = {b[i:i + 3] for i in range(len(b) - 2)}
    u = ta | tb
    return len(ta & tb) / len(u) if u else 0.0


def smart_score(query: str, target: str) -> float:
    q = query.lower()
    t = target.lower()
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    if t.startswith(q):
        return 0.95
    if q in t:
        return 0.85
    words = t.split()
    for w in words:
        if w.startswith(q):
            return 0.8
    if abs(len(q) - len(t)) > max(len(q), len(t)) * 0.6:
        return 0.0
    tg = trigram_sim(q, t)
    if tg > 0.5:
        return 0.3 + tg * 0.5
    md = max(len(q), len(t))
    lim = int(md * 0.4) + 1
    d = levenshtein(q, t, lim)
    if d == 0:
        return 1.0
    ratio = d / md
    if ratio <= 0.15:
        return 0.75
    if ratio <= 0.25:
        return 0.65
    if ratio <= 0.35:
        return 0.55
    for w in words:
        wl = max(len(q), len(w))
        wlim = int(wl * 0.3) + 1
        wd = levenshtein(q, w, wlim)
        if wd <= wl * 0.25:
            return 0.55
    return 0.1 if tg > 0.15 else 0.0


def multi_layout_score(query: str, target: str) -> float:
    q = query.lower().strip()
    best = smart_score(q, target)
    q_ru = switch_layout(q, EN_TO_RU)
    if q_ru != q:
        best = max(best, smart_score(q_ru, target) * 0.98)
    q_en = switch_layout(q, RU_TO_EN)
    if q_en != q:
        best = max(best, smart_score(q_en, target) * 0.98)
    return best


# ── Search Result ──

@dataclass
class SearchResult:
    title: str = ""
    subtitle: str = ""
    icon_name: str = ""
    action: Optional[Callable] = None
    score: float = 0.0
    category: str = ""
    file_path: str = ""
    preview_kind: str = ""
    preview_text: str = ""
    preview_data: Optional[dict[str, Any]] = None
    usage_key: str = ""
    browse_url: str = ""


# ── Helpers ──

def _clipboard(text: str):
    try:
        subprocess.run(
            ["qdbus6", "org.kde.klipper", "/klipper",
             "org.kde.klipper.klipper.setClipboardContents", text],
            check=True, timeout=2,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        try:
            subprocess.run(["wl-copy", text], check=True, timeout=2)
        except Exception:
            pass


def _kill_pids(pids: list[str]):
    for pid in pids:
        try:
            subprocess.run(["kill", "-15", pid], timeout=3)
        except Exception:
            pass


def _xdg_open(url: str):
    try:
        subprocess.Popen(
            ["xdg-open", url],
            start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _run_cmd(cmd):
    try:
        subprocess.Popen(
            cmd,
            shell=isinstance(cmd, str),
            start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _notify(title: str, body: str, icon: str = "dialog-information", urgency: str = "normal"):
    try:
        subprocess.Popen(
            ["notify-send", "-a", APP_NAME, "-i", icon, "-u", urgency, title, body],
            start_new_session=True,
        )
    except Exception:
        pass


def _play_sound():
    for p in (
        "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
        "/usr/share/sounds/freedesktop/stereo/complete.oga",
    ):
        if os.path.exists(p):
            try:
                subprocess.Popen(
                    ["paplay", p],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
            return

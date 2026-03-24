from pathlib import Path
from PyQt6.QtGui import QColor


def _parse_rgb(s: str, fallback: str = "128,128,128") -> tuple[int, int, int]:
    try:
        parts = (s or fallback).split(",")
        return int(parts[0]), int(parts[1]), int(parts[2])
    except Exception:
        parts = fallback.split(",")
        return int(parts[0]), int(parts[1]), int(parts[2])


def load_kde_colors() -> dict[str, tuple[int, int, int]]:
    path = Path.home() / ".config" / "kdeglobals"
    data: dict[str, dict[str, str]] = {}
    section = ""
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("["):
                section = line.split("]")[0] + "]"
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                data.setdefault(section, {})[k.strip()] = v.strip()
    except Exception:
        pass

    def g(sec, key, fb):
        return _parse_rgb(data.get(sec, {}).get(key, ""), fb)

    return {
        "window_bg": g("[Colors:Window]", "BackgroundNormal", "32,35,38"),
        "view_bg": g("[Colors:View]", "BackgroundNormal", "20,22,24"),
        "header_bg": g("[Colors:Header]", "BackgroundNormal", "41,44,48"),
        "button_bg": g("[Colors:Button]", "BackgroundNormal", "41,44,48"),
        "accent": g("[Colors:Selection]", "BackgroundNormal", "61,174,233"),
        "text": g("[Colors:Window]", "ForegroundNormal", "252,252,252"),
        "text_inactive": g("[Colors:Window]", "ForegroundInactive", "161,169,177"),
        "text_active": g("[Colors:Window]", "ForegroundActive", "61,174,233"),
        "link": g("[Colors:Window]", "ForegroundLink", "29,153,243"),
        "negative": g("[Colors:Window]", "ForegroundNegative", "218,68,83"),
        "positive": g("[Colors:Window]", "ForegroundPositive", "39,174,96"),
        "wm_bg": g("[WM]", "activeBackground", "39,44,49"),
    }


THEME = load_kde_colors()


def rgb(key: str) -> str:
    r, g, b = THEME[key]
    return f"rgb({r},{g},{b})"


def rgba(key: str, a: float) -> str:
    r, g, b = THEME[key]
    return f"rgba({r},{g},{b},{a})"


def qcolor(key: str, alpha: int = 255) -> QColor:
    r, g, b = THEME[key]
    return QColor(r, g, b, alpha)

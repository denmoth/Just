"""KDE (X11): hide launcher from taskbar via xprop / wmctrl. On pure Wayland these calls do nothing."""

import shutil
import subprocess

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget


def _run_skip_taskbar(widget: QWidget) -> None:
    if QGuiApplication.platformName() != "xcb":
        return
    try:
        wid = int(widget.winId())
    except (TypeError, ValueError):
        return
    if wid <= 0:
        return
    wid_s = str(wid)
    try:
        subprocess.run(
            [
                "xprop",
                "-id",
                wid_s,
                "-f",
                "_NET_WM_STATE",
                "32a",
                "-set",
                "_NET_WM_STATE",
                "_NET_WM_STATE_SKIP_TASKBAR",
                "_NET_WM_STATE_SKIP_PAGER",
            ],
            capture_output=True,
            timeout=2,
            check=False,
        )
        subprocess.run(
            [
                "xprop",
                "-id",
                wid_s,
                "-f",
                "_NET_WM_WINDOW_TYPE",
                "32a",
                "-set",
                "_NET_WM_WINDOW_TYPE",
                "_NET_WM_WINDOW_TYPE_SPLASH",
            ],
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    wmctrl = shutil.which("wmctrl")
    if wmctrl:
        try:
            subprocess.run(
                [wmctrl, "-i", "-r", wid_s, "-b", "add,skip_taskbar,skip_pager"],
                capture_output=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass


def apply_skip_taskbar_hint(widget: QWidget, delay_ms: int = 0) -> None:
    if delay_ms > 0:
        QTimer.singleShot(delay_ms, lambda w=widget: _run_skip_taskbar(w))
    else:
        _run_skip_taskbar(widget)


def schedule_skip_taskbar_hints(widget: QWidget) -> None:
    """Re-apply a few times — KWin sometimes maps the window before hints stick."""
    for ms in (0, 50, 120, 300, 600, 1200, 2000):
        apply_skip_taskbar_hint(widget, delay_ms=ms)

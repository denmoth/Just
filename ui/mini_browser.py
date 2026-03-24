"""Small floating browser for !bang URLs (Ctrl+Space)."""

import sys

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QGuiApplication, QPainter, QPen, QPainterPath, QPaintEvent
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QLabel,
)

from core.search import _xdg_open
from core.theme import rgb, rgba, qcolor
from ui.plasma_hints import schedule_skip_taskbar_hints


class MiniBrowserWindow(QWidget):
    def __init__(self, url: str, launcher: QWidget):
        super().__init__(launcher)
        self._url = url
        self._launcher = launcher
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(780, 520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(6)

        bar = QHBoxLayout()
        tip = QLabel(url[:96] + ("…" if len(url) > 96 else ""))
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{rgb('text')};font-size:10px;")
        bar.addWidget(tip, 1)
        ob = QPushButton("Во внешнем браузере")
        ob.setStyleSheet(
            f"QPushButton{{background:{rgba('button_bg', 0.6)};color:{rgb('text')};padding:6px 10px;border-radius:4px;}}"
        )
        ob.clicked.connect(lambda: _xdg_open(url))
        bar.addWidget(ob)
        outer.addLayout(bar)

        self._web = None
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView

            self._web = QWebEngineView()
            self._web.load(QUrl(url))
            outer.addWidget(self._web, 1)
        except Exception as e:
            tb = QTextBrowser()
            tb.setPlainText(
                f"{url}\n\n"
                "Встроенный браузер недоступен.\n\n"
                f"Ошибка: {e!r}\n"
                f"Интерпретатор: {sys.executable}\n\n"
                "Если пакет уже стоит в системе, Just, скорее всего, запущен "
                "другим Python (venv, IDE). Запусти из терминала:\n"
                "  /usr/bin/python3 runner.py\n"
                "или в scripts/start-detached.sh задай PYTHON=/usr/bin/python3.\n\n"
                "Arch/CachyOS: sudo pacman -S python-pyqt6-webengine"
            )
            tb.setStyleSheet(f"background:{rgba('button_bg', 0.5)};color:{rgb('text')};")
            outer.addWidget(tb, 1)

        self._place_near_launcher()

    def _place_near_launcher(self) -> None:
        L = self._launcher
        scr = L.screen() or QGuiApplication.primaryScreen()
        if not scr:
            return
        ag = scr.availableGeometry()
        g = L.frameGeometry()
        gap = 10
        x = g.right() + gap
        y = g.top()
        if x + self.width() > ag.right():
            x = g.left() - self.width() - gap
        x = max(ag.left(), min(x, ag.right() - self.width()))
        y = max(ag.top(), min(y, ag.bottom() - self.height()))
        self.move(x, y)

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(float(r.x()), float(r.y()), float(r.width()), float(r.height()), 10, 10)
        p.fillPath(path, qcolor("window_bg"))
        p.setPen(QPen(qcolor("accent", 80), 1.5))
        p.drawPath(path)
        p.end()

    def showEvent(self, event):
        super().showEvent(event)
        schedule_skip_taskbar_hints(self)
        self.raise_()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            p = self.parent()
            if p is not None and hasattr(p, "_close_mini_browser"):
                p._close_mini_browser()
        else:
            super().keyPressEvent(event)

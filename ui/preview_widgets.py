"""Side-panel previews: text, scientific calculator, shell output."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QLineEdit, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import (
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPainterPath,
    QPaintEvent,
    QGuiApplication,
    QKeyEvent,
    QShortcut,
    QKeySequence,
)

from core.theme import rgb, rgba, qcolor
from core.config import PREVIEW_WIDTH
from core.calc_eval import calc_eval, normalize_expression
from .pty_terminal import PtyTerminalWidget


class ScientificCalcWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.expr_edit = QLineEdit()
        self.expr_edit.setFont(QFont("monospace", 12))
        self.expr_edit.setPlaceholderText("Выражение · с клавиатуры или кнопки")
        self.expr_edit.setStyleSheet(
            f"QLineEdit{{background:{rgba('button_bg', 0.6)};color:{rgb('text')};"
            "padding:10px;border-radius:6px;border:none;min-height:28px;}}"
        )
        self.expr_edit.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self.expr_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.expr_edit.returnPressed.connect(self._equals)
        self.expr_edit.installEventFilter(self)
        lay.addWidget(self.expr_edit)

        grid = QGridLayout()
        grid.setSpacing(4)

        def btn(text: str, r: int, c: int, cs: int = 1, fn=None):
            b = QPushButton(text)
            b.setFixedHeight(32)
            b.setStyleSheet(
                f"QPushButton{{background:{rgba('button_bg', 0.5)};color:{rgb('text')};"
                f"border-radius:4px;border:1px solid {rgba('text_inactive', 0.15)};}}"
                f"QPushButton:hover{{background:{rgba('accent', 0.2)};}}"
            )

            def on_click():
                if fn is not None:
                    fn()
                else:
                    self._insert_token(text)

            b.clicked.connect(on_click)
            grid.addWidget(b, r, c, 1, cs)

        rows = [
            ("C", "⌫", "(", ")"),
            ("sin(", "cos(", "tan(", "/"),
            ("asin(", "acos(", "atan(", "*"),
            ("sqrt(", "log(", "log10(", "-"),
            ("7", "8", "9", "+"),
            ("4", "5", "6", "^"),
            ("1", "2", "3", "Fraction("),
            ("0", ".", "pi", "e"),
        ]
        for ri, row in enumerate(rows):
            for ci, t in enumerate(row):
                btn(t, ri, ci)

        btn("=", len(rows), 0, 4, self._equals)
        lay.addLayout(grid)

    def _insert_token(self, t: str):
        self.expr_edit.setFocus()
        if t == "C":
            self.expr_edit.clear()
            return
        if t == "⌫":
            self.expr_edit.backspace()
            return
        ins = "**" if t == "^" else t
        self.expr_edit.insert(ins)

    def _equals(self):
        raw = self.expr_edit.text().strip()
        if not raw:
            return
        expr = normalize_expression(raw)
        disp, err = calc_eval(expr)
        if disp is not None:
            self.expr_edit.setText(disp)
        else:
            self.expr_edit.setText(err or "ошибка")

    def set_expression(self, expr: str):
        self.expr_edit.blockSignals(True)
        self.expr_edit.setText(expr.strip())
        self.expr_edit.blockSignals(False)

    def focus_expr(self) -> None:
        self.expr_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        t = self.expr_edit.text()
        self.expr_edit.setCursorPosition(len(t))

    def eventFilter(self, obj, event):
        if obj is self.expr_edit and event.type() == QEvent.Type.KeyPress:
            ke = event
            if isinstance(ke, QKeyEvent) and ke.key() == Qt.Key.Key_Escape:
                p = self.parent()
                while p is not None:
                    if hasattr(p, "_close_preview_flyout"):
                        p._close_preview_flyout()
                        return True
                    p = p.parent()
        return super().eventFilter(obj, event)


class WeatherPreviewWidget(QWidget):
    """Structured current + hourly weather (not a single QLabel blob)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.installEventFilter(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(56, 56)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(self._icon_lbl)

        col = QVBoxLayout()
        col.setSpacing(2)
        self._city_lbl = QLabel()
        self._city_lbl.setFont(QFont("", 10))
        self._city_lbl.setStyleSheet(f"color:{rgba('text_inactive', 0.88)};")
        self._temp_lbl = QLabel()
        self._temp_lbl.setFont(QFont("", 26, QFont.Weight.Bold))
        self._temp_lbl.setStyleSheet(f"color:{rgb('text')};")
        self._desc_lbl = QLabel()
        self._desc_lbl.setFont(QFont("", 11, QFont.Weight.Medium))
        self._desc_lbl.setStyleSheet(f"color:{rgb('text')};")
        self._desc_lbl.setWordWrap(True)
        col.addWidget(self._city_lbl)
        col.addWidget(self._temp_lbl)
        col.addWidget(self._desc_lbl)
        head.addLayout(col, 1)
        outer.addLayout(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self._stat_cells: list[tuple[QLabel, QLabel]] = []
        labels = [
            (0, 0, "Ощущается", "feels", "°C"),
            (0, 1, "Ветер", "wind", " км/ч"),
            (1, 0, "Влажность", "humidity", "%"),
            (1, 1, "Давление", "pressure", " гПа"),
            (2, 0, "Облачность", "clouds", "%"),
        ]
        card_style = (
            f"QFrame{{background:{rgba('button_bg', 0.55)};border-radius:8px;"
            f"border:1px solid {rgba('text_inactive', 0.12)};}}"
        )
        for gr, gc, title, key, suffix in labels:
            fr = QFrame()
            fr.setStyleSheet(card_style)
            fl = QVBoxLayout(fr)
            fl.setContentsMargins(8, 6, 8, 6)
            fl.setSpacing(2)
            t = QLabel(title)
            t.setFont(QFont("", 8))
            t.setStyleSheet(f"color:{rgba('text_inactive', 0.65)};")
            v = QLabel("—")
            v.setFont(QFont("", 11, QFont.Weight.DemiBold))
            v.setStyleSheet(f"color:{rgb('text')};")
            v.setProperty("stat_key", key)
            v.setProperty("stat_suffix", suffix)
            fl.addWidget(t)
            fl.addWidget(v)
            grid.addWidget(fr, gr, gc)
            self._stat_cells.append((t, v))
        outer.addLayout(grid)

        sep = QLabel("Ближайшие часы")
        sep.setFont(QFont("", 9, QFont.Weight.Bold))
        sep.setStyleSheet(f"color:{rgba('text_inactive', 0.75)};")
        outer.addWidget(sep)

        self._hourly_scroll = QScrollArea()
        self._hourly_scroll.setWidgetResizable(True)
        self._hourly_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._hourly_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
        )
        self._hourly_host = QWidget()
        self._hourly_lay = QVBoxLayout(self._hourly_host)
        self._hourly_lay.setContentsMargins(0, 0, 0, 0)
        self._hourly_lay.setSpacing(4)
        self._hourly_scroll.setWidget(self._hourly_host)
        outer.addWidget(self._hourly_scroll, 1)

    def set_data(self, data: dict) -> None:
        city = str(data.get("city") or "")
        temp = str(data.get("temp") or "—")
        desc = str(data.get("desc") or "")
        iname = str(data.get("icon_name") or "weather-none-available")
        ic = QIcon.fromTheme(iname, QIcon.fromTheme("weather-none-available"))
        if not ic.isNull():
            self._icon_lbl.setPixmap(ic.pixmap(56, 56))
        else:
            self._icon_lbl.setText("")

        self._city_lbl.setText(city)
        self._temp_lbl.setText(f"{temp}°")
        self._desc_lbl.setText(desc)

        feels = str(data.get("feels") or "—")
        wind = str(data.get("wind") or "—")
        hum = str(data.get("humidity") or "—")
        pres = str(data.get("pressure") or "—")
        clo = str(data.get("clouds") or "—")
        values = {"feels": feels, "wind": wind, "humidity": hum, "pressure": pres, "clouds": clo}
        suffixes = {"feels": "°C", "wind": " км/ч", "humidity": "%", "pressure": " гПа", "clouds": "%"}
        for _t, vlab in self._stat_cells:
            key = vlab.property("stat_key")
            if not key:
                continue
            k = str(key)
            suf = suffixes.get(k, "")
            vlab.setText(f"{values.get(k, '—')}{suf}")

        while (it := self._hourly_lay.takeAt(0)) is not None:
            w = it.widget()
            if w:
                w.deleteLater()

        hourly = data.get("hourly") or []
        if not isinstance(hourly, list):
            hourly = []
        for row in hourly[:24]:
            if not isinstance(row, dict):
                continue
            tm = str(row.get("time") or "")
            tp = str(row.get("temp") or "—")
            ds = str(row.get("desc") or "")
            ric = str(row.get("icon") or "weather-none-available")
            line_w = QWidget()
            line = QHBoxLayout(line_w)
            line.setContentsMargins(4, 4, 4, 4)
            il = QLabel()
            il.setFixedSize(22, 22)
            il.setAlignment(Qt.AlignmentFlag.AlignCenter)
            i2 = QIcon.fromTheme(ric, QIcon.fromTheme("weather-none-available"))
            if not i2.isNull():
                il.setPixmap(i2.pixmap(22, 22))
            t1 = QLabel(tm)
            t1.setFixedWidth(44)
            t1.setFont(QFont("monospace", 10))
            t1.setStyleSheet(f"color:{rgba('text_inactive', 0.85)};")
            t2 = QLabel(f"{tp}°")
            t2.setFixedWidth(40)
            t2.setFont(QFont("", 11, QFont.Weight.DemiBold))
            t2.setStyleSheet(f"color:{rgb('text')};")
            t3 = QLabel(ds)
            t3.setFont(QFont("", 9))
            t3.setStyleSheet(f"color:{rgba('text', 0.9)};")
            t3.setWordWrap(False)
            line.addWidget(il)
            line.addWidget(t1)
            line.addWidget(t2)
            line.addWidget(t3, 1)
            self._hourly_lay.addWidget(line_w)

        self._hourly_lay.addStretch(1)

    def eventFilter(self, obj, event):
        if obj is self and event.type() == QEvent.Type.KeyPress:
            ke = event
            if isinstance(ke, QKeyEvent) and ke.key() == Qt.Key.Key_Escape:
                p = self.parent()
                while p is not None:
                    if hasattr(p, "_close_preview_flyout"):
                        p._close_preview_flyout()
                        return True
                    p = p.parent()
        return super().eventFilter(obj, event)


class PreviewSidePanel(QWidget):
    def __init__(self, parent=None, *, compact: bool = False):
        super().__init__(parent)
        self.setFixedWidth(PREVIEW_WIDTH)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8 if compact else 52, 8, 8)
        lay.setSpacing(0)

        self.title = QLabel("")
        self.title.setFont(QFont("", 10, QFont.Weight.Bold))
        self.title.setStyleSheet(f"color:{rgb('text')};background:transparent;padding:4px;")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)

        self.text_scroll = QScrollArea()
        self.text_scroll.setWidgetResizable(True)
        self.text_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.text_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.text_body = QLabel("")
        self.text_body.setWordWrap(True)
        self.text_body.setFont(QFont("", 10))
        self.text_body.setStyleSheet(
            f"color:{rgba('text', 0.92)};background:{rgba('button_bg', 0.35)};"
            "padding:10px;border-radius:8px;"
        )
        self.text_body.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.text_scroll.setWidget(self.text_body)
        lay.addWidget(self.text_scroll, 1)

        self.calc_w = ScientificCalcWidget(self)
        self.calc_w.hide()

        self.shell_w = PtyTerminalWidget(self)
        self.shell_w.hide()

        self.weather_w = WeatherPreviewWidget(self)
        self.weather_w.hide()

        lay.addWidget(self.calc_w, 1)
        lay.addWidget(self.shell_w, 1)
        lay.addWidget(self.weather_w, 1)

        self.setStyleSheet(f"PreviewSidePanel{{background:transparent;}}")

    def clear(self):
        self.title.setText("")
        self.text_body.setText("")
        self.calc_w.hide()
        self.shell_w.stop()
        self.shell_w.hide()
        self.weather_w.hide()
        self.text_scroll.show()

    def apply_result(
        self,
        preview_kind: str,
        preview_text: str,
        title_hint: str,
        *,
        preview_data: dict | None = None,
    ):
        self.title.setText(title_hint[:120] if title_hint else "Предпросмотр")
        k = (preview_kind or "").lower()
        self.calc_w.hide()
        self.shell_w.hide()
        self.weather_w.hide()
        self.text_scroll.hide()

        if k == "calc":
            self.text_scroll.hide()
            self.calc_w.show()
            self.calc_w.set_expression(preview_text or "")
            return

        if k == "shell":
            self.shell_w.show()
            self.shell_w.start_shell(preview_text or "")
            return

        if k == "weather" and preview_data:
            self.weather_w.show()
            self.weather_w.set_data(preview_data)
            return

        if k == "weather":
            self.text_scroll.show()
            self.text_body.setText(preview_text or "—")
            return

        self.text_scroll.show()
        self.text_body.setText(preview_text or "")
        if not (preview_text or "").strip():
            self.text_body.setText("—")


class PreviewFlyoutWindow(QWidget):
    """Floating preview (same widgets as the old side panel) — like file Quick Look."""

    _RADIUS = 10

    def __init__(self, launcher: QWidget):
        super().__init__(launcher)
        self._launcher = launcher
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        w = PREVIEW_WIDTH + 40
        self.setFixedSize(w, 520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._container = QWidget()
        cl = QVBoxLayout(self._container)
        cl.setContentsMargins(10, 10, 10, 10)
        cl.setSpacing(0)

        self._panel = PreviewSidePanel(self._container, compact=True)
        cl.addWidget(self._panel, 1)
        outer.addWidget(self._container)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._escape_close)

    def _escape_close(self) -> None:
        p = self.parent()
        if p is not None and hasattr(p, "_close_preview_flyout"):
            p._close_preview_flyout()

    def show_content(
        self,
        preview_kind: str,
        preview_text: str,
        title_hint: str,
        preview_data: dict | None = None,
    ) -> None:
        pk0 = (preview_kind or "").lower()
        if pk0 == "weather":
            self.setFixedSize(PREVIEW_WIDTH + 90, 560)
            self._panel.setFixedWidth(PREVIEW_WIDTH + 50)
        else:
            self.setFixedSize(PREVIEW_WIDTH + 40, 520)
            self._panel.setFixedWidth(PREVIEW_WIDTH)

        self._panel.apply_result(
            preview_kind, preview_text, title_hint, preview_data=preview_data,
        )
        self._place_near_launcher()
        self.show()
        self.raise_()
        self.activateWindow()
        pk = (preview_kind or "").lower()
        if pk == "calc":
            QTimer.singleShot(0, self._panel.calc_w.focus_expr)
        elif pk == "shell":

            def _focus_shell() -> None:
                self.raise_()
                self.activateWindow()
                self._panel.shell_w.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

            QTimer.singleShot(0, _focus_shell)
            QTimer.singleShot(80, _focus_shell)
            QTimer.singleShot(220, _focus_shell)
        elif pk == "weather":

            def _focus_weather() -> None:
                self.raise_()
                self.activateWindow()
                self._panel.weather_w.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

            QTimer.singleShot(0, _focus_weather)
            QTimer.singleShot(50, _focus_weather)

    def hide_and_clear(self) -> None:
        self._panel.clear()
        self.hide()

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
        rect = self._container.geometry()
        path = QPainterPath()
        path.addRoundedRect(
            float(rect.x()),
            float(rect.y()),
            float(rect.width()),
            float(rect.height()),
            float(self._RADIUS),
            float(self._RADIUS),
        )
        p.fillPath(path, qcolor("window_bg"))
        p.setPen(QPen(qcolor("accent", 80), 1.5))
        p.drawPath(path)
        p.end()

    def showEvent(self, event):
        super().showEvent(event)
        from ui.plasma_hints import schedule_skip_taskbar_hints

        schedule_skip_taskbar_hints(self)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            p = self.parent()
            if p is not None and hasattr(p, "_close_preview_flyout"):
                p._close_preview_flyout()
        else:
            super().keyPressEvent(event)

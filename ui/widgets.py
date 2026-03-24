import os
import subprocess

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QPainter, QPen, QPainterPath, QGuiApplication, QPaintEvent

from core.config import home, ITEM_HEIGHT
from core.theme import rgb, rgba, qcolor
from core.search import SearchResult
from ui.plasma_hints import schedule_skip_taskbar_hints


class ResultItemWidget(QWidget):
    clicked = pyqtSignal()
    enter_hover = pyqtSignal(int)

    def __init__(self, result: SearchResult, index: int, selected: bool = False, parent=None):
        super().__init__(parent)
        self.result = result
        self.index = index
        self._selected = selected
        self.setFixedHeight(ITEM_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build()
        self._apply_style()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(12)

        icon = QLabel()
        self.icon_label = icon
        icon.setFixedSize(28, 28)
        q_icon = QIcon.fromTheme(self.result.icon_name or "application-x-executable")
        if not q_icon.isNull():
            icon.setPixmap(q_icon.pixmap(QSize(28, 28)))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        text_box.setContentsMargins(0, 0, 0, 0)

        tf = QLabel(self.result.title)
        tf.setFont(QFont("", 11))
        tf.setStyleSheet(f"color:{rgb('text')};background:transparent;")
        tf.setWordWrap(False)
        tf.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        if self.result.subtitle:
            tf.setFixedHeight(22)
            text_box.addWidget(tf)
            sf = QLabel(self.result.subtitle)
            sf.setFont(QFont("", 9))
            sf.setStyleSheet(f"color:{rgba('text_inactive', 0.6)};background:transparent;")
            sf.setWordWrap(False)
            sf.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            sf.setFixedHeight(20)
            text_box.addWidget(sf)
        else:
            tf.setFixedHeight(ITEM_HEIGHT - 4)
            text_box.addWidget(tf)

        lay.addLayout(text_box, 1)

        if self.result.category:
            badge = QLabel(self.result.category)
            bf = QFont("", 8)
            badge.setFont(bf)
            badge.setStyleSheet(
                f"color:{rgba('text_inactive', 0.6)};background:{rgba('button_bg', 0.5)};"
                "padding:2px 6px;border-radius:3px;"
            )
            lay.addWidget(badge)

        self.hint_label = QLabel("Enter ↵")
        hf = QFont("", 8)
        self.hint_label.setFont(hf)
        self.hint_label.setStyleSheet(
            f"color:{rgba('text_inactive', 0.6)};background:{rgba('button_bg', 0.5)};"
            "padding:2px 6px;border-radius:3px;"
        )
        self.hint_label.setVisible(self._selected)
        lay.addWidget(self.hint_label)

    def set_selected(self, val: bool):
        self._selected = val
        self._apply_style()
        self.hint_label.setVisible(val)
        self.update()

    def _apply_style(self):
        # Selection fill is drawn only in paintEvent so the bar matches full row width
        # (negative insets previously clipped against the scroll viewport and looked "torn").
        self.setStyleSheet("background:transparent;")

    def paintEvent(self, event: QPaintEvent):
        if not self._selected:
            super().paintEvent(event)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 1, -2, -1)
        path = QPainterPath()
        path.addRoundedRect(float(r.x()), float(r.y()), float(r.width()), float(r.height()), 6, 6)
        p.fillPath(path, qcolor("accent", 38))
        p.end()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def enterEvent(self, event):
        self.enter_hover.emit(self.index)


class QuickLookWindow(QWidget):
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(620, 440)
        self._file_path = file_path
        self._build()
        self._center()

    def _center(self):
        scr = QGuiApplication.primaryScreen()
        if scr:
            g = scr.availableGeometry()
            self.move(
                g.x() + (g.width() - 620) // 2,
                g.y() + int(g.height() * 0.18),
            )

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._container = QWidget()
        cl = QVBoxLayout(self._container)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)

        header = QLabel(os.path.basename(self._file_path))
        header.setFont(QFont("", 13, QFont.Weight.Bold))
        header.setStyleSheet(f"color:{rgb('text')};background:transparent;")
        cl.addWidget(header)

        sub = QLabel(self._file_path.replace(str(home), "~"))
        sub.setFont(QFont("", 9))
        sub.setStyleSheet(f"color:{rgba('text_inactive', 0.6)};background:transparent;")
        cl.addWidget(sub)

        content = self._load_content()
        body = QLabel(content)
        body.setWordWrap(True)
        body.setFont(QFont("Monospace", 10))
        body.setStyleSheet(f"color:{rgb('text')};background:transparent;padding:8px;")
        body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        cl.addWidget(scroll, 1)

        lay.addWidget(self._container)

    def _load_content(self) -> str:
        ext = self._file_path.rsplit(".", 1)[-1].lower() if "." in self._file_path else ""

        if ext == "pdf":
            try:
                out = subprocess.run(
                    ["pdftotext", self._file_path, "-", "-l", "2"],
                    capture_output=True, text=True, timeout=5,
                )
                return out.stdout[:3000] or "(пустой PDF)"
            except Exception:
                return "(не удалось прочитать PDF)"

        if ext in ("png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"):
            try:
                size = os.path.getsize(self._file_path)
                from PyQt6.QtGui import QImageReader
                reader = QImageReader(self._file_path)
                s = reader.size()
                return f"Изображение: {s.width()}×{s.height()} px\nРазмер: {size / 1024:.0f} KB"
            except Exception:
                return "(не удалось прочитать изображение)"

        if ext in ("mp3", "flac", "wav", "ogg", "m4a", "mp4", "mkv", "avi", "webm"):
            try:
                out = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-show_format", "-show_streams",
                     self._file_path],
                    capture_output=True, text=True, timeout=5,
                )
                lines = []
                for line in out.stdout.split("\n"):
                    if "=" in line:
                        k, _, v = line.partition("=")
                        if k.strip() in ("duration", "bit_rate", "codec_name",
                                         "width", "height", "sample_rate"):
                            lines.append(f"{k.strip()}: {v.strip()}")
                return "\n".join(lines) or "(нет метаданных)"
            except Exception:
                return "(не удалось прочитать медиа)"

        try:
            with open(self._file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(5000)
            lines = text.split("\n")[:60]
            return "\n".join(lines)
        except Exception:
            return "(не удалось прочитать файл)"

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._container.geometry()
        path = QPainterPath()
        path.addRoundedRect(
            float(rect.x()), float(rect.y()),
            float(rect.width()), float(rect.height()), 10, 10,
        )
        p.fillPath(path, qcolor("window_bg"))
        border = QPen(qcolor("accent", 80), 1.5)
        p.setPen(border)
        p.drawPath(path)
        p.end()

    def showEvent(self, event):
        super().showEvent(event)
        schedule_skip_taskbar_hints(self)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space):
            self.close()

    def focusOutEvent(self, event):
        self.close()

"""
Main window with async search, optional flyout preview (Ctrl+Shift+Space), selection history.
"""

import os
import threading
import time
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QScrollArea, QFrame, QApplication, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent, pyqtSignal
from PyQt6.QtGui import (
    QIcon, QFont, QPainter, QPen, QPainterPath,
    QGuiApplication, QKeyEvent, QPaintEvent,
)

from core.config import MAX_RESULTS, WINDOW_WIDTH, CORNER_RADIUS, ITEM_HEIGHT, home
from core.nl import normalize_for_runners
from core.last_repeat import load_last_repeat, save_last_repeat_if_eligible
from runners.weather import WeatherRunner
from runners.resource_snapshot import idle_resource_result
from core.theme import rgb, rgba, qcolor
from core.search import SearchResult
from core.history_usage import (
    load_selection_history,
    append_selection_history,
    bump_usage,
    usage_multiplier,
    usage_count,
    warmup_usage_cache,
)

from runners import discover_runners
from runners.ai import AIRunner
from ui.plasma_hints import apply_skip_taskbar_hint, schedule_skip_taskbar_hints
from ui.widgets import ResultItemWidget, QuickLookWindow
from ui.preview_widgets import PreviewFlyoutWindow
from ui.history_icons import icon_for_history_query
from ui.prefix_hints import prefix_hint
from ui.mini_browser import MiniBrowserWindow

AI_DEBOUNCE_MS = 1500
INPUT_DEBOUNCE_MS = 220

# Must match results_layout margins (4+4) and setSpacing(2).
_RESULTS_LIST_MARGIN_V = 8
_RESULTS_LIST_SPACING = 2
_WINDOW_LIST_TAIL_PAD = 16

_INSTANT_RUNNERS = {"CalcRunner", "ShellRunner", "WebRunner", "MediaRunner"}

PREFIX_TO_RUNNERS: dict[str, frozenset[str]] = {
    "app": frozenset({"AppRunner"}),
    "apps": frozenset({"AppRunner"}),
    "web": frozenset({"WebRunner"}),
    "weather": frozenset({"WeatherRunner"}),
    "погода": frozenset({"WeatherRunner"}),
    "file": frozenset({"FileRunner", "NaturalLanguageRunner"}),
    "файл": frozenset({"FileRunner", "NaturalLanguageRunner"}),
    "content": frozenset({"ContentRunner"}),
    "в": frozenset({"ContentRunner"}),
    "timer": frozenset({"TimerRunner"}),
    "таймер": frozenset({"TimerRunner"}),
    "sys": frozenset({"SystemRunner", "SystemToggleRunner"}),
    "system": frozenset({"SystemRunner", "SystemToggleRunner"}),
    "term": frozenset({"ShellRunner"}),
    "shell": frozenset({"ShellRunner"}),
    "calc": frozenset({"CalcRunner"}),
    "конвертер": frozenset({"ConverterRunner"}),
    "fx": frozenset({"ConverterRunner"}),
    "kill": frozenset({"KillRunner"}),
    "media": frozenset({"MediaRunner"}),
    "музыка": frozenset({"MediaRunner"}),
}


def parse_category_prefix(raw: str) -> tuple[str, Optional[str]]:
    s = raw.strip()
    if not s.startswith(".") or " " not in s:
        return s, None
    i = s.index(" ")
    prefix = s[:i].lower()
    body = s[i + 1 :].strip()
    if len(prefix) < 2 or not body:
        return s, None
    key = prefix[1:]
    if key in PREFIX_TO_RUNNERS:
        return body, key
    return s, None


def adapt_query_for_prefix(filt: Optional[str], q: str) -> str:
    if filt in ("content", "в"):
        return f"в: {q}"
    return q


class JustWindow(QWidget):
    _ai_results_ready = pyqtSignal(list)
    _heavy_results_ready = pyqtSignal(list, str)

    def __init__(self):
        super().__init__()
        all_runners = discover_runners()
        self._ai_runner: Optional[AIRunner] = None
        self.instant_runners = []
        self.heavy_runners = []
        for r in all_runners:
            if getattr(r, "is_ai", False):
                self._ai_runner = r
            elif type(r).__name__ in _INSTANT_RUNNERS:
                self.instant_runners.append(r)
            else:
                self.heavy_runners.append(r)

        self.results: list[SearchResult] = []
        self.selected_index = 0
        self.item_widgets: list[ResultItemWidget] = []
        self._quick_look: Optional[QuickLookWindow] = None
        self._ai_query: str = ""
        self._ai_pending = False
        self._heavy_gen: int = 0
        self._last_rendered_key: str = ""
        self._searching: bool = False
        self._cat_filt: Optional[str] = None
        self._raw_input: str = ""
        self._preview_flyout: Optional[PreviewFlyoutWindow] = None
        self._mini_browser: Optional[MiniBrowserWindow] = None

        self._setup_window()
        self._setup_ui()
        warmup_usage_cache()

        self._input_timer = QTimer()
        self._input_timer.setSingleShot(True)
        self._input_timer.timeout.connect(self._on_input_debounce)

        self._ai_timer = QTimer()
        self._ai_timer.setSingleShot(True)
        self._ai_timer.timeout.connect(self._on_ai_debounce)
        self._ai_results_ready.connect(self._on_ai_results)
        self._heavy_results_ready.connect(self._on_heavy_results)

        self._suppress_focus_hide_until = 0.0
        self._unfocus_timer = QTimer()
        self._unfocus_timer.setSingleShot(True)
        self._unfocus_timer.timeout.connect(self._deferred_hide_if_still_unfocused)

        self._layout_height_timer = QTimer(self)
        self._layout_height_timer.setSingleShot(True)
        self._layout_height_timer.timeout.connect(self._apply_window_height_from_layout)

        self._repeat_gen = 0

        self._defaults()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(WINDOW_WIDTH)
        self._center()
        self._enable_blur()

    def _center(self):
        scr = QGuiApplication.primaryScreen()
        if scr:
            g = scr.availableGeometry()
            self.move(
                g.x() + (g.width() - self.width()) // 2,
                g.y() + int(g.height() * 0.22),
            )

    def _enable_blur(self):
        try:
            import subprocess
            subprocess.Popen(
                [
                    "dbus-send", "--session", "--dest=org.kde.KWin",
                    "/org/kde/KWin", "org.kde.KWin.enableEffect",
                    "string:blur",
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _apply_blur_hint(self):
        try:
            wid = int(self.winId())
            import subprocess
            subprocess.Popen(
                [
                    "xprop", "-id", str(wid), "-f", "_KDE_NET_WM_BLUR_BEHIND_REGION",
                    "32c", "-set", "_KDE_NET_WM_BLUR_BEHIND_REGION", "0",
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _filter_runners(self, runners: list, filt: Optional[str]) -> list:
        if not filt:
            return runners
        names = PREFIX_TO_RUNNERS.get(filt)
        if not names:
            return runners
        return [r for r in runners if type(r).__name__ in names]

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        left_holder = QWidget()
        left_holder.setFixedWidth(WINDOW_WIDTH)
        cl = QVBoxLayout(left_holder)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self.container = QWidget()
        vl = QVBoxLayout(self.container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        self.search_input = QLineEdit()
        self.search_input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.search_input.setPlaceholderText(
            "Поиск · !! повтор · .app · !g · > · = · погода · Ctrl+Space превью"
        )
        self.search_input.setFont(QFont("", 14))
        self.search_input.setMinimumHeight(48)
        self.search_input.setStyleSheet(
            f"QLineEdit{{background:transparent;border:none;color:{rgb('text')};"
            f"padding:12px 14px 10px 44px;selection-background-color:{rgba('accent', 0.4)};}}"
        )
        self.search_input.textChanged.connect(self._on_input)
        self.search_input.installEventFilter(self)
        vl.addWidget(self.search_input)

        self.prefix_hint_label = QLabel()
        self.prefix_hint_label.setWordWrap(True)
        self.prefix_hint_label.setFont(QFont("", 9))
        self.prefix_hint_label.setStyleSheet(
            f"color:{rgba('text_inactive', 0.52)};"
            "padding:0 14px 6px 44px;background:transparent;"
        )
        vl.addWidget(self.prefix_hint_label)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{rgba('text', 0.06)};max-height:1px;")
        vl.addWidget(sep)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            f"QScrollArea{{background:transparent;border:none;}}"
            f"QScrollBar:vertical{{background:transparent;width:5px;margin:3px 1px;}}"
            f"QScrollBar::handle:vertical{{background:{rgba('text_inactive', 0.2)};"
            f"border-radius:2px;min-height:20px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{rgba('text_inactive', 0.4)};}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}"
            f"QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:none;}}"
        )
        self.results_widget = QWidget()
        self.results_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum,
        )
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(4, 4, 4, 4)
        self.results_layout.setSpacing(2)
        self.scroll.setWidget(self.results_widget)
        vl.addWidget(self.scroll)

        cl.addWidget(self.container)

        row.addWidget(left_holder)
        outer.addLayout(row)

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.container.geometry()
        path = QPainterPath()
        path.addRoundedRect(
            float(rect.x()), float(rect.y()),
            float(rect.width()), float(rect.height()),
            CORNER_RADIUS, CORNER_RADIUS,
        )
        bg = qcolor("window_bg", 180)
        p.fillPath(path, bg)
        border_pen = QPen(qcolor("accent", 40), 1.0)
        p.setPen(border_pen)
        p.drawPath(path)

        icon = QIcon.fromTheme("search")
        if not icon.isNull():
            p.drawPixmap(14, 14, icon.pixmap(QSize(20, 20)))
        else:
            p.setPen(QPen(qcolor("text_inactive"), 1.5))
            p.drawText(14, 30, "🔍")
        p.end()

    def _input_block_height(self) -> int:
        h = self.search_input.minimumHeight()
        if self.prefix_hint_label.isVisible() and self.prefix_hint_label.text().strip():
            h += self.prefix_hint_label.sizeHint().height()
        h += 1
        return h

    def _update_prefix_hint(self, query: str) -> None:
        t = prefix_hint(query, self._cat_filt)
        self.prefix_hint_label.setText(t)
        self.prefix_hint_label.setVisible(bool(t.strip()))
        self._layout_height_timer.start(0)

    def _effective_query(self, query: str, filt: Optional[str], body: str) -> str:
        if filt:
            return adapt_query_for_prefix(filt, normalize_for_runners(body))
        return normalize_for_runners(query)

    def _fill_repeat_results(self) -> None:
        last = load_last_repeat()
        if not last:
            self.results = [
                SearchResult(
                    title="Нечего повторять",
                    subtitle="Сначала выполните команду (строки с > и $ не сохраняются)",
                    icon_name="dialog-information",
                    score=1.0,
                    category="Повтор",
                    action=lambda: None,
                )
            ]
            return
        self.results = [
            SearchResult(
                title="Повторить последнее",
                subtitle=last[:100] + ("…" if len(last) > 100 else ""),
                icon_name="edit-redo",
                score=1.0,
                category="Повтор",
                usage_key="repeat:!!",
                action=lambda: None,
            )
        ]

    def _schedule_repeat_execute(self, expected: str) -> None:
        self._repeat_gen += 1
        gen = self._repeat_gen

        def attempt() -> None:
            if gen != self._repeat_gen:
                return
            if not self.isVisible():
                return
            if self.search_input.text().strip() != expected:
                return
            if not self.results:
                return
            self.selected_index = 0
            self._execute()

        QTimer.singleShot(320, attempt)
        QTimer.singleShot(900, attempt)

    def _do_repeat_last(self) -> None:
        last = load_last_repeat()
        if not last:
            return
        self.search_input.blockSignals(True)
        self.search_input.setText(last)
        self.search_input.blockSignals(False)
        self._on_input(last)
        self._schedule_repeat_execute(last)

    def _on_input(self, text: str):
        self.selected_index = 0
        self._ai_timer.stop()
        self._ai_pending = False
        self._raw_input = text.strip()
        query = text.strip()

        body, filt = parse_category_prefix(query)
        self._cat_filt = filt
        self._update_prefix_hint(query)
        eff = self._effective_query(query, filt, body)

        if query == "!!":
            self._input_timer.stop()
            self._heavy_gen += 1
            self._last_rendered_key = ""
            self._searching = False
            self._fill_repeat_results()
            self._render()
            return

        if not query:
            self._input_timer.stop()
            self._heavy_gen += 1
            self._last_rendered_key = ""
            self._searching = False
            self._cat_filt = None
            self._defaults()
            return

        if query.startswith("?") and self._ai_runner:
            self._input_timer.stop()
            prompt = query[1:].strip()
            if len(prompt) >= 2:
                self.results = [SearchResult(
                    title="AI думает...",
                    subtitle=prompt,
                    icon_name="dialog-question", score=0.95,
                    category="AI", action=lambda: None,
                )]
                self._render()
                self._ai_query = query
                self._ai_runner.query_async(prompt, self._emit_ai_results)
                return
            elif self._ai_runner:
                self.results = self._ai_runner.match(query)
                self._render()
                return

        instant = []
        for runner in self._filter_runners(self.instant_runners, filt):
            try:
                instant.extend(runner.match(eff))
            except Exception:
                pass

        self.results = instant
        self._last_rendered_key = ""
        self._searching = True
        self._sort_and_render()

        if query.startswith((">", "$")) or query.startswith("?"):
            return
        self._heavy_gen += 1
        self._input_timer.start(INPUT_DEBOUNCE_MS)

    def _on_input_debounce(self):
        query = self.search_input.text().strip()
        if not query or query.startswith(("?", ">", "$")):
            return
        body, filt = parse_category_prefix(query)
        eff = self._effective_query(query, filt, body)
        gen = self._heavy_gen

        def _work():
            results = []
            for runner in self._filter_runners(self.heavy_runners, filt):
                try:
                    results.extend(runner.match(eff))
                except Exception:
                    pass
            if gen == self._heavy_gen:
                self._heavy_results_ready.emit(results, query)

        threading.Thread(target=_work, daemon=True).start()

    def _on_heavy_results(self, heavy_results: list, query: str):
        if self.search_input.text().strip() != query:
            return
        existing_titles = {r.title for r in self.results}
        for r in heavy_results:
            if r.title not in existing_titles:
                self.results.append(r)
        self._searching = False
        self._last_rendered_key = ""
        self._sort_and_render()

        body, filt = parse_category_prefix(query)
        eff = body if filt else query
        if self._ai_runner and len(self.results) < 3 and len(eff) >= 4 and not filt:
            from core.config import CFG
            has_key = bool(CFG.get("groq_api_key", "") or CFG.get("grok_api_key", ""))
            auto_fb = CFG.get("ai_auto_fallback", True)
            if has_key and auto_fb:
                self._ai_query = query
                self._ai_pending = True
                self._ai_timer.start(AI_DEBOUNCE_MS)

    def _sort_and_render(self):
        def sort_key(r: SearchResult) -> tuple:
            key = r.usage_key or f"{r.category}:{r.title}"
            primary = -(r.score * usage_multiplier(key))
            tie = -usage_count(key)
            return (primary, tie)

        self.results.sort(key=sort_key)
        seen: set[str] = set()
        unique = [r for r in self.results if r.title not in seen and not seen.add(r.title)]
        self.results = unique[:MAX_RESULTS]
        key = "|".join(r.title for r in self.results)
        if key == self._last_rendered_key:
            self._sync_preview()
            return
        self._last_rendered_key = key
        self._render()

    def _on_ai_debounce(self):
        if not self._ai_pending or not self._ai_runner:
            return
        current_text = self.search_input.text().strip()
        if current_text != self._ai_query:
            return

        self.results.append(SearchResult(
            title="AI думает...",
            subtitle=current_text,
            icon_name="dialog-question", score=0.5,
            category="AI", action=lambda: None,
        ))
        self._render()

        self._ai_runner.query_async(current_text, self._emit_ai_results)

    def _emit_ai_results(self, results: list):
        self._ai_results_ready.emit(results)

    def _on_ai_results(self, ai_results: list):
        current_text = self.search_input.text().strip()
        expected = self._ai_query

        if current_text != expected and not current_text.startswith("?"):
            return

        self.results = [r for r in self.results if r.title != "AI думает..."]
        self.results.extend(ai_results)
        self.results.sort(key=lambda r: -r.score)
        self.results = self.results[:MAX_RESULTS]
        self._ai_pending = False
        self._render()

    def _defaults(self):
        self.results = []
        wr = WeatherRunner()
        wrow = wr.match("погода")
        if wrow:
            self.results.append(wrow[0])
        self.results.append(idle_resource_result())

        hist = load_selection_history()
        hint_slots = 2
        hist_cap = max(0, MAX_RESULTS - len(self.results) - hint_slots)
        for h in hist[:hist_cap]:
            self.results.append(SearchResult(
                title=h,
                subtitle="Недавний выбор",
                icon_name=icon_for_history_query(h),
                score=0.55,
                category="История",
                preview_kind="text",
                preview_text=f"Подставить в строку поиска:\n\n{h}",
                action=lambda t=h: self._fill(t),
            ))
        self.results.extend([
            SearchResult(
                title="Подсказка: .app имя",
                subtitle="Только приложения · .web · .погода · .файл",
                icon_name="dialog-information", score=0.35,
                category="Справка", action=lambda: self._fill(".app "),
            ),
            SearchResult(
                title="= и !g",
                subtitle="Калькулятор · !g запрос · > команда",
                icon_name="system-search", score=0.3,
                category="Справка", action=lambda: self._fill("!g "),
            ),
        ])
        self.results = self.results[:MAX_RESULTS]
        self.selected_index = 0
        self._last_rendered_key = ""
        self._update_prefix_hint("")
        self._render()

    def _fill(self, t: str):
        self.search_input.setText(t)

    def _nominal_list_content_height(self) -> int:
        if self.results:
            n = min(len(self.results), MAX_RESULTS)
            return (
                _RESULTS_LIST_MARGIN_V
                + n * ITEM_HEIGHT
                + (n - 1) * _RESULTS_LIST_SPACING
            )
        if self._searching:
            return _RESULTS_LIST_MARGIN_V + ITEM_HEIGHT
        return 0

    def _apply_window_height_from_layout(self) -> None:
        self.results_layout.activate()
        hint_h = self.results_widget.minimumSizeHint().height()
        content_h = max(hint_h, self._nominal_list_content_height())
        self.setFixedHeight(
            self._input_block_height() + content_h + _WINDOW_LIST_TAIL_PAD,
        )

    def _render(self):
        for w in self.item_widgets:
            self.results_layout.removeWidget(w)
            w.deleteLater()
        self.item_widgets.clear()

        while (item := self.results_layout.takeAt(0)):
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.results:
            if not self._searching:
                lbl = QLabel("Ничего не найдено")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet(
                    f"color:{rgba('text_inactive', 0.5)};padding:20px;font-size:12px;"
                )
                self.results_layout.addWidget(lbl)
            self.scroll.verticalScrollBar().setValue(0)
            self._apply_window_height_from_layout()
            self._layout_height_timer.start(0)
            self._sync_preview()
            return

        for i, res in enumerate(self.results):
            w = ResultItemWidget(res, i, selected=(i == self.selected_index))
            w.clicked.connect(lambda idx=i: self._click(idx))
            w.enter_hover.connect(self._hover)
            self.results_layout.addWidget(w)
            self.item_widgets.append(w)

        self.scroll.verticalScrollBar().setValue(0)
        self._apply_window_height_from_layout()
        self._layout_height_timer.start(0)
        self._sync_preview()

    def _result_has_preview(self, r: SearchResult) -> bool:
        pk = (r.preview_kind or "").strip().lower()
        if pk == "weather" and r.preview_data:
            return True
        return bool((r.preview_kind or "").strip() or (r.preview_text or "").strip())

    def _fallback_preview_text(self, r: SearchResult) -> str:
        lines = [r.title or "—"]
        if r.subtitle:
            lines.append(r.subtitle)
        if r.category:
            lines.append(f"Категория: {r.category}")
        if r.file_path:
            try:
                fp = r.file_path.replace(str(home), "~")
            except Exception:
                fp = r.file_path
            lines.append(fp)
        return "\n\n".join(lines)

    def _ensure_preview_flyout(self) -> PreviewFlyoutWindow:
        if self._preview_flyout is None:
            self._preview_flyout = PreviewFlyoutWindow(self)
        return self._preview_flyout

    def _close_preview_flyout(self) -> None:
        if self._preview_flyout is not None:
            self._preview_flyout.hide_and_clear()

    def _sync_preview(self) -> None:
        self._apply_window_height_from_layout()
        self._layout_height_timer.start(0)
        self.setFixedWidth(WINDOW_WIDTH)

        if not self.results or self.selected_index >= len(self.results):
            self._close_preview_flyout()
            return

        r = self.results[self.selected_index]
        if self._preview_flyout is not None and self._preview_flyout.isVisible():
            if self._result_has_preview(r):
                self._preview_flyout.show_content(
                    r.preview_kind,
                    r.preview_text,
                    r.title,
                    r.preview_data,
                )
                schedule_skip_taskbar_hints(self._preview_flyout)
            else:
                self._preview_flyout.show_content(
                    "text", self._fallback_preview_text(r), r.title, None,
                )
                schedule_skip_taskbar_hints(self._preview_flyout)

    def _hotkey_preview_flyout(self) -> None:
        if not self.results or self.selected_index >= len(self.results):
            return
        r = self.results[self.selected_index]
        if self._preview_flyout is not None and self._preview_flyout.isVisible():
            self._close_preview_flyout()
            return
        fly = self._ensure_preview_flyout()
        if self._result_has_preview(r):
            fly.show_content(r.preview_kind, r.preview_text, r.title, r.preview_data)
        else:
            fly.show_content("text", self._fallback_preview_text(r), r.title, None)
        schedule_skip_taskbar_hints(fly)

    def _close_mini_browser(self) -> None:
        if self._mini_browser is not None:
            self._mini_browser.close()
            self._mini_browser = None

    def _show_mini_browser(self, url: str) -> None:
        self._close_mini_browser()
        self._mini_browser = MiniBrowserWindow(url, self)
        self._mini_browser.show()

    def _ctrl_space_action(self) -> None:
        if not self.results or self.selected_index >= len(self.results):
            return
        r = self.results[self.selected_index]
        if r.file_path and os.path.exists(r.file_path):
            self._show_quick_look()
            return
        bu = (r.browse_url or "").strip()
        if bu.startswith(("http://", "https://")):
            self._show_mini_browser(bu)
            return
        self._hotkey_preview_flyout()

    def _update_selection(self, idx: int):
        self.selected_index = idx
        for i, w in enumerate(self.item_widgets):
            if isinstance(w, ResultItemWidget):
                w.set_selected(i == idx)
        if idx < len(self.item_widgets):
            self.scroll.ensureWidgetVisible(self.item_widgets[idx])
        self._sync_preview()

    def _hover(self, idx: int):
        self._update_selection(idx)

    def _click(self, idx: int):
        self.selected_index = idx
        self._execute()

    def _selection_history_line(self, res: SearchResult) -> str:
        u = (res.usage_key or "").strip()
        if len(u) >= 2:
            return u
        return (res.title or "").strip() or f"{res.category}:{res.title}"

    def _execute(self):
        if 0 <= self.selected_index < len(self.results):
            res = self.results[self.selected_index]
            if res.category == "Повтор":
                if res.title == "Нечего повторять":
                    return
                self._do_repeat_last()
                return
            key = res.usage_key or f"{res.category}:{res.title}"
            bump_usage(key)
            act = res.action
            if act:
                act()
            if res.category in ("История", "Справка"):
                if res.category == "История":
                    append_selection_history(self._selection_history_line(res))
                return
            save_last_repeat_if_eligible(self.search_input.text().strip())
            append_selection_history(self._selection_history_line(res))
            self._dismiss_launcher()

    def _dismiss_launcher(self):
        self._close_preview_flyout()
        self._close_mini_browser()
        if self._quick_look:
            self._quick_look.close()
            self._quick_look = None
        apply_skip_taskbar_hint(self, 0)
        apply_skip_taskbar_hint(self, 30)
        self.hide()
        schedule_skip_taskbar_hints(self)

    def eventFilter(self, obj, event):
        if obj is self.search_input and isinstance(event, QKeyEvent):
            if event.type() == QEvent.Type.KeyPress:
                k = event.key()
                if k == Qt.Key.Key_Down:
                    self._update_selection(
                        min(self.selected_index + 1, len(self.results) - 1)
                    )
                    return True
                if k == Qt.Key.Key_Up:
                    self._update_selection(max(self.selected_index - 1, 0))
                    return True
                if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._execute()
                    return True
                if k == Qt.Key.Key_Escape:
                    if self._mini_browser is not None and self._mini_browser.isVisible():
                        self._close_mini_browser()
                        return True
                    if self._preview_flyout is not None and self._preview_flyout.isVisible():
                        self._close_preview_flyout()
                        return True
                    self._dismiss_launcher()
                    return True
                if k == Qt.Key.Key_Tab:
                    if self.results and self.results[0].title.startswith("= "):
                        self._execute()
                    return True
                if k == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                    self._ctrl_space_action()
                    return True
        return super().eventFilter(obj, event)

    def _show_quick_look(self):
        if 0 <= self.selected_index < len(self.results):
            r = self.results[self.selected_index]
            if r.file_path and os.path.exists(r.file_path):
                if self._quick_look:
                    self._quick_look.close()
                self._quick_look = QuickLookWindow(r.file_path)
                self._quick_look.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents, True,
                )
                self._quick_look.show()

    def showEvent(self, event):
        super().showEvent(event)
        # Wayland often delivers active state one frame later; avoid instant "unfocus" hide.
        self._suppress_focus_hide_until = time.monotonic() + 1.2
        self._close_preview_flyout()
        self._close_mini_browser()
        self.search_input.clear()
        self._cat_filt = None
        self._center()
        self._apply_blur_hint()
        schedule_skip_taskbar_hints(self)
        self._defaults()
        self._focus_search_line()
        for ms in (0, 50, 150):
            QTimer.singleShot(ms, self._focus_search_line)

    def _focus_search_line(self) -> None:
        if not self.isVisible():
            return
        self.raise_()
        self.activateWindow()
        wh = self.windowHandle()
        if wh is not None:
            wh.requestActivate()
        self.search_input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _request_unfocus_dismiss(self):
        """Defer hide: on outside click, Qt often still reports focus inside QLineEdit
        while ActivationChange already says inactive — the old isAncestorOf(fw) guard
        skipped dismiss entirely."""
        self._unfocus_timer.stop()
        self._unfocus_timer.start(45)

    def _deferred_hide_if_still_unfocused(self):
        if time.monotonic() < self._suppress_focus_hide_until:
            return
        if not self.isVisible():
            return
        if self._quick_look and self._quick_look.isVisible():
            return
        if self._mini_browser is not None and self._mini_browser.isVisible():
            fw = QApplication.focusWidget()
            if self._mini_browser.isActiveWindow() or (
                fw is not None and self._mini_browser.isAncestorOf(fw)
            ):
                return
        if self._preview_flyout is not None and self._preview_flyout.isVisible():
            fw = QApplication.focusWidget()
            if self._preview_flyout.isActiveWindow() or (
                fw is not None and self._preview_flyout.isAncestorOf(fw)
            ):
                return
        if self.isActiveWindow():
            return
        self._dismiss_launcher()

    def changeEvent(self, event):
        et = event.type()
        if et == QEvent.Type.WindowDeactivate:
            if time.monotonic() >= self._suppress_focus_hide_until:
                self._request_unfocus_dismiss()
            return super().changeEvent(event)
        if et == QEvent.Type.ActivationChange:
            if (
                self.isVisible()
                and not self.isActiveWindow()
                and time.monotonic() >= self._suppress_focus_hide_until
            ):
                self._request_unfocus_dismiss()
            return super().changeEvent(event)
        return super().changeEvent(event)

    def event(self, event):
        if event.type() == QEvent.Type.ApplicationDeactivate:
            if self.isVisible() and time.monotonic() >= self._suppress_focus_hide_until:
                self._request_unfocus_dismiss()
        return super().event(event)

    def hideEvent(self, event):
        apply_skip_taskbar_hint(self, 0)
        self._close_preview_flyout()
        self.setFixedWidth(WINDOW_WIDTH)
        super().hideEvent(event)

    def toggle(self):
        if self.isVisible():
            self._dismiss_launcher()
        else:
            self._suppress_focus_hide_until = time.monotonic() + 1.2
            self.show()
            self._focus_search_line()
            for ms in (0, 50, 150):
                QTimer.singleShot(ms, self._focus_search_line)

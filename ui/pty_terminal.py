"""Interactive PTY terminal for preview (bash -i + pyte)."""

from __future__ import annotations

import errno
import sys
import fcntl
import os
import signal
import struct
import termios

from PyQt6.QtCore import Qt, QSocketNotifier, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QKeyEvent, QKeySequence
from PyQt6.QtWidgets import QApplication, QPlainTextEdit

try:
    from pyte import ByteStream, Screen
except ImportError:
    Screen = None  # type: ignore
    ByteStream = None  # type: ignore


def _pty_available() -> bool:
    return Screen is not None and ByteStream is not None


class PtyTerminalWidget(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("monospace", 9))
        self.setStyleSheet(
            "QPlainTextEdit{background:#1e1e2e;color:#cdd6f4;border:none;"
            "border-radius:6px;padding:4px;}"
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setUndoRedoEnabled(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._master_fd: int | None = None
        self._child_pid: int | None = None
        self._notifier: QSocketNotifier | None = None
        self._screen: Screen | None = None
        self._stream: ByteStream | None = None
        self._cols = 80
        self._rows = 24
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._apply_resize)

    def start_shell(self, initial_line: str = "") -> None:
        self.stop()
        self.clear()
        if not _pty_available():
            self.setPlainText(
                "Нет модуля pyte для этого интерпретатора Python.\n\n"
                f"Интерпретатор: {sys.executable}\n\n"
                "Если ставили через pacman, запускайте Just системным python3:\n"
                "  /usr/bin/python3 runner.py\n"
                "или PYTHON=/usr/bin/python3 в start-detached.sh.\n\n"
                "Установка: pacman -S python-pyte\n"
                "(в venv: pip install pyte)"
            )
            return

        fm = self.fontMetrics()
        cw = max(1, fm.horizontalAdvance("M"))
        rh = max(1, fm.lineSpacing())
        vp = self.viewport().geometry()
        if vp.width() > 20 and vp.height() > 20:
            self._cols = max(40, vp.width() // cw)
            self._rows = max(8, vp.height() // rh)
        else:
            self._cols, self._rows = 80, 24

        try:
            master, slave = pty.openpty()
        except OSError as e:
            self.setPlainText(f"pty.openpty: {e}")
            return

        self._reset_screen(self._cols, self._rows)

        pid = os.fork()
        if pid == 0:
            try:
                os.close(master)
                os.setsid()
                os.dup2(slave, 0)
                os.dup2(slave, 1)
                os.dup2(slave, 2)
                if slave > 2:
                    os.close(slave)
                os.environ.setdefault("TERM", "xterm-256color")
                os.environ.setdefault("COLORTERM", "truecolor")
                shell = os.environ.get("SHELL") or "/bin/bash"
                if not os.path.isfile(shell):
                    shell = "/bin/bash"
                base = os.path.basename(shell)
                os.execl(shell, base, "-i")
            except Exception:
                os._exit(127)

        os.close(slave)
        self._master_fd = master
        self._child_pid = pid

        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        self._set_winsize(self._rows, self._cols)

        self._notifier = QSocketNotifier(master, QSocketNotifier.Type.Read)
        self._notifier.activated.connect(self._on_pty_ready_read)

        self.clear()
        init = (initial_line or "").strip()
        if init:
            QTimer.singleShot(120, lambda: self._pty_write((init + "\n").encode("utf-8")))

    def _reset_screen(self, cols: int, rows: int) -> None:
        self._cols = max(40, cols)
        self._rows = max(8, rows)
        self._screen = Screen(self._cols, self._rows)
        self._stream = ByteStream(self._screen)

    def _set_winsize(self, rows: int, cols: int) -> None:
        if self._master_fd is None:
            return
        try:
            winsz = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsz)
            if self._child_pid:
                try:
                    os.kill(self._child_pid, signal.SIGWINCH)
                except ProcessLookupError:
                    pass
        except OSError:
            pass

    @pyqtSlot()
    def _on_pty_ready_read(self) -> None:
        self._read_pty()

    def stop(self) -> None:
        n = self._notifier
        if n is not None:
            self._notifier = None
            n.setEnabled(False)
            n.blockSignals(True)
            n.disconnect()
            n.deleteLater()
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        pid = self._child_pid
        if pid is not None:
            self._child_pid = None
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass
            except OSError:
                pass
        self._stream = None
        self._screen = None

    def _stop_deferred(self) -> None:
        """Never call stop() synchronously from QSocketNotifier — can crash Qt."""
        QTimer.singleShot(0, self.stop)

    def _read_pty(self) -> None:
        if self._master_fd is None or self._stream is None:
            return
        try:
            while True:
                try:
                    data = os.read(self._master_fd, 65536)
                except OSError as e:
                    if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        break
                    self.appendPlainText(f"\n[read: {e}]\n")
                    self._stop_deferred()
                    return
                if not data:
                    self.appendPlainText("\n[сессия завершена]\n")
                    self._stop_deferred()
                    return
                self._stream.feed(data)
        finally:
            self._refresh_from_screen()

    def _refresh_from_screen(self) -> None:
        if self._screen is None:
            return
        lines = [self._screen.display[i].rstrip() for i in range(self._screen.lines)]
        text = "\n".join(lines)
        self.setPlainText(text)
        c = self._screen.cursor
        cy = min(max(0, c.y), self._screen.lines - 1)
        raw = self._screen.display[cy]
        cx = min(max(0, c.x), len(raw))
        pos = 0
        for li in range(cy):
            pos += len(lines[li]) + 1
        pos += min(cx, len(lines[cy]) if cy < len(lines) else 0)
        cur = self.textCursor()
        cur.setPosition(min(pos, max(0, len(text))))
        self.setTextCursor(cur)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not _pty_available():
            return
        fm = self.fontMetrics()
        cw = max(1, fm.horizontalAdvance("M"))
        rh = max(1, fm.lineSpacing())
        vp = self.viewport().geometry()
        cols = max(40, vp.width() // cw)
        rows = max(8, vp.height() // rh)
        if cols != self._cols or rows != self._rows:
            self._cols = cols
            self._rows = rows
            self._resize_timer.start(80)

    def _apply_resize(self) -> None:
        if self._master_fd is None or self._screen is None:
            return
        self._set_winsize(self._rows, self._cols)
        self._screen.resize(self._rows, self._cols)
        self._refresh_from_screen()

    def _pty_write(self, data: bytes) -> None:
        if self._master_fd is None or not data:
            return
        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() == Qt.Key.Key_Escape
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            p = self.parent()
            while p is not None:
                if hasattr(p, "_close_preview_flyout"):
                    p._close_preview_flyout()
                    event.accept()
                    return
                p = p.parent()

        if self._master_fd is None or not _pty_available():
            super().keyPressEvent(event)
            return

        b = self._map_key(event)
        if b is not None:
            self._pty_write(b)
            QTimer.singleShot(0, self._read_pty)
            event.accept()
            return
        super().keyPressEvent(event)

    def _map_key(self, e: QKeyEvent) -> bytes | None:
        k = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        if alt:
            return None

        if e.matches(QKeySequence.StandardKey.Paste):
            clip = QApplication.clipboard().text()
            return clip.encode("utf-8", "replace")

        if ctrl and Qt.Key.Key_A <= k <= Qt.Key.Key_Z:
            return bytes([1 + (k - Qt.Key.Key_A)])

        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return b"\r"
        if k == Qt.Key.Key_Backspace:
            return b"\x7f"
        if k == Qt.Key.Key_Tab:
            return b"\t" if not shift else b"\x1b[Z"
        if k == Qt.Key.Key_Escape:
            return b"\x1b"
        if k == Qt.Key.Key_Up:
            return b"\x1b[A"
        if k == Qt.Key.Key_Down:
            return b"\x1b[B"
        if k == Qt.Key.Key_Right:
            return b"\x1b[C"
        if k == Qt.Key.Key_Left:
            return b"\x1b[D"
        if k == Qt.Key.Key_Home:
            return b"\x1b[H"
        if k == Qt.Key.Key_End:
            return b"\x1b[F"
        if k == Qt.Key.Key_PageUp:
            return b"\x1b[5~"
        if k == Qt.Key.Key_PageDown:
            return b"\x1b[6~"
        if k == Qt.Key.Key_Delete:
            return b"\x1b[3~"

        t = e.text()
        if t and not ctrl:
            return t.encode("utf-8")
        return None

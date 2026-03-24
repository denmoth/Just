#!/usr/bin/env python3
"""
Just — entry point (KDE KRunner–compatible launcher).

Usage:
  python3 runner.py                  — GUI mode (normal)
  python3 runner.py --check          — validate all modules load, exit 0/1
  python3 runner.py --query "текст"  — run query headless, print results as JSON
  python3 runner.py --interactive    — REPL: type queries, see results in terminal
  python3 runner.py --debug           — verbose logs
"""

import sys
import os
import signal
import argparse
import json
import logging
import time
from pathlib import Path


def _prepare_qt_webengine_env() -> None:
    # Chromium sandbox often fails under user systemd / Plasma (EPERM); without this,
    # QWebEngineView can raise or show a blank page. User can override via env.
    if sys.platform != "linux":
        return
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    flag = "--disable-dev-shm-usage"
    cur = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    if flag not in cur:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{cur} {flag}".strip() if cur else flag


def _cli_check():
    """Validate all modules load without GUI."""
    _prepare_qt_webengine_env()
    errors = []
    try:
        from core.config import CFG, APP_NAME, VERSION
        print(f"[OK] core.config — {APP_NAME} {VERSION}")
    except Exception as e:
        errors.append(f"core.config: {e}")
        print(f"[FAIL] core.config: {e}")

    try:
        from core.theme import THEME, rgb
        print(f"[OK] core.theme — {len(THEME)} colors")
    except Exception as e:
        errors.append(f"core.theme: {e}")
        print(f"[FAIL] core.theme: {e}")

    try:
        from core.search import smart_score, multi_layout_score
        s = smart_score("fire", "firefox")
        print(f"[OK] core.search — smart_score('fire','firefox')={s:.2f}")
    except Exception as e:
        errors.append(f"core.search: {e}")
        print(f"[FAIL] core.search: {e}")

    try:
        from runners import discover_runners
        runners = discover_runners()
        names = [type(r).__name__ for r in runners]
        print(f"[OK] runners — {len(runners)} loaded: {', '.join(names)}")
    except Exception as e:
        errors.append(f"runners: {e}")
        print(f"[FAIL] runners: {e}")

    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        _ = QWebEngineView
        print("[OK] PyQt6.QtWebEngineWidgets (mini browser)")
    except Exception as e:
        errors.append(f"QtWebEngine: {e}")
        print(f"[FAIL] PyQt6.QtWebEngineWidgets: {e}")
        print(f"      (python: {sys.executable})")

    try:
        import pyte  # noqa: F401

        print("[OK] pyte (terminal preview)")
    except Exception as e:
        errors.append(f"pyte: {e}")
        print(f"[FAIL] pyte: {e}")
        print(f"      (python: {sys.executable})")

    if errors:
        print(f"\n{len(errors)} error(s)")
        return 1
    print("\nAll modules OK")
    return 0


def _cli_query(query: str):
    """Run a query headless, print JSON results."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from core.nl import normalize_for_runners
    from runners import discover_runners
    runners = discover_runners()
    nq = normalize_for_runners(query)

    results = []
    for runner in runners:
        if getattr(runner, "is_ai", False):
            continue
        try:
            results.extend(runner.match(nq))
        except Exception as e:
            print(f"[WARN] {type(runner).__name__}: {e}", file=sys.stderr)

    results.sort(key=lambda r: -r.score)
    seen = set()
    unique = []
    for r in results:
        if r.title not in seen:
            seen.add(r.title)
            unique.append(r)
    unique = unique[:10]

    out = []
    for r in unique:
        out.append({
            "title": r.title,
            "subtitle": r.subtitle,
            "icon": r.icon_name,
            "score": round(r.score, 3),
            "category": r.category,
            "file_path": r.file_path or None,
        })
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _cli_interactive():
    """REPL mode: type queries, see results in terminal."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from core.nl import normalize_for_runners
    from runners import discover_runners
    runners = discover_runners()
    names = [type(r).__name__ for r in runners]
    print(f"Loaded {len(runners)} runners: {', '.join(names)}")
    print("Type a query (Ctrl+C to exit):\n")

    while True:
        try:
            query = input("› ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            continue

        nq = normalize_for_runners(query)
        results = []
        for runner in runners:
            if getattr(runner, "is_ai", False):
                continue
            try:
                results.extend(runner.match(nq))
            except Exception as e:
                print(f"  [ERR] {type(runner).__name__}: {e}")

        results.sort(key=lambda r: -r.score)
        seen = set()
        unique = []
        for r in results:
            if r.title not in seen:
                seen.add(r.title)
                unique.append(r)

        if not unique:
            print("  (нет результатов)\n")
            continue

        for i, r in enumerate(unique[:7]):
            cat = f" [{r.category}]" if r.category else ""
            sub = f"  {r.subtitle}" if r.subtitle else ""
            print(f"  {i+1}. {r.title}{cat}  (score={r.score:.2f})")
            if sub:
                print(f"     {sub}")
        print()


_REPO_ROOT = Path(__file__).resolve().parent


def main_gui():
    """Normal GUI mode with D-Bus integration for KDE Alt+Space."""
    _prepare_qt_webengine_env()
    from core.proc_title import set_process_title
    from core.desktop_entry import ensure_just_desktop

    set_process_title("just")
    ensure_just_desktop(repo_root=_REPO_ROOT)

    from PyQt6.QtCore import Qt, QCoreApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

        _ = QWebEngineView
    except ImportError:
        pass

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    from PyQt6.QtDBus import QDBusConnection, QDBusAbstractAdaptor
    from PyQt6.QtCore import pyqtSlot, pyqtClassInfo, QTimer
    from core.config import APP_NAME, SOCKET_NAME, DATA_DIR, spawn_content_indexer_restart
    from ui.window import JustWindow

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logging.getLogger("just").debug("Starting QApplication (Just GUI)")

    app = QApplication(sys.argv)
    app.setApplicationName("just")
    app.setApplicationDisplayName(APP_NAME)
    try:
        app.setDesktopFileName("just")
    except Exception:
        pass
    app.setQuitOnLastWindowClosed(False)

    sock = QLocalSocket()
    sock.connectToServer(SOCKET_NAME)
    if sock.waitForConnected(500):
        # Check if the other end actually responds
        sock.write(b"toggle")
        sock.flush()
        if sock.waitForBytesWritten(1000):
            sock.disconnectFromServer()
            sys.exit(0)
        sock.disconnectFromServer()
    sock.close()

    # Always clean stale sockets
    server = QLocalServer()
    QLocalServer.removeServer(SOCKET_NAME)

    spawn_content_indexer_restart()

    window = JustWindow()

    # D-Bus adaptor: KDE calls these methods via Alt+Space / Alt+F2
    @pyqtClassInfo("D-Bus Interface", "org.kde.krunner.App")
    @pyqtClassInfo("D-Bus Introspection",
        '<interface name="org.kde.krunner.App">'
        '  <method name="display"/>'
        '  <method name="toggleDisplay"/>'
        '  <method name="displaySingleRunner"><arg type="s" direction="in"/></method>'
        '  <method name="displayWithClipboardContents"/>'
        '  <method name="query"><arg type="s" direction="in"/></method>'
        '  <method name="querySingleRunner">'
        '    <arg type="s" direction="in"/><arg type="s" direction="in"/>'
        '  </method>'
        '</interface>')
    class KRunnerAdaptor(QDBusAbstractAdaptor):

        def __init__(self, win, parent):
            super().__init__(parent)
            self._win = win

        @pyqtSlot()
        def display(self):
            self._win._suppress_focus_hide_until = time.monotonic() + 1.2
            self._win.show()
            self._win._focus_search_line()
            for ms in (0, 50, 150):
                QTimer.singleShot(ms, self._win._focus_search_line)

        @pyqtSlot()
        def toggleDisplay(self):
            self._win.toggle()

        @pyqtSlot(str)
        def displaySingleRunner(self, name):
            self.display()

        @pyqtSlot()
        def displayWithClipboardContents(self):
            self.display()

        @pyqtSlot(str)
        def query(self, term):
            self.display()
            self._win.search_input.setText(term)

        @pyqtSlot(str, str)
        def querySingleRunner(self, runner, term):
            self.query(term)

    # org.freedesktop.Application — KDE uses this to activate via shortcuts
    @pyqtClassInfo("D-Bus Interface", "org.freedesktop.Application")
    @pyqtClassInfo("D-Bus Introspection",
        '<interface name="org.freedesktop.Application">'
        '  <method name="Activate"><arg type="a{sv}" direction="in"/></method>'
        '  <method name="Open">'
        '    <arg type="as" direction="in"/><arg type="a{sv}" direction="in"/>'
        '  </method>'
        '  <method name="ActivateAction">'
        '    <arg type="s" direction="in"/><arg type="av" direction="in"/>'
        '    <arg type="a{sv}" direction="in"/>'
        '  </method>'
        '</interface>')
    class FreedesktopAdaptor(QDBusAbstractAdaptor):

        def __init__(self, win, parent):
            super().__init__(parent)
            self._win = win

        @pyqtSlot("QVariantMap")
        def Activate(self, platform_data):
            self._win.toggle()

        @pyqtSlot("QStringList", "QVariantMap")
        def Open(self, uris, platform_data):
            self._win.toggle()

        @pyqtSlot(str, "QVariantList", "QVariantMap")
        def ActivateAction(self, action, parameter, platform_data):
            self._win.toggle()

    log = logging.getLogger("just")
    KRunnerAdaptor(window, window)
    FreedesktopAdaptor(window, window)

    bus = QDBusConnection.sessionBus()
    dbus_registered = bus.registerService("org.kde.krunner")
    if dbus_registered:
        # Same QObject on both paths: avoids duplicate adaptors and races on restart.
        bus.registerObject("/App", window)
        bus.registerObject("/org/kde/krunner", window)
        log.debug("D-Bus: org.kde.krunner -> /App + /org/kde/krunner (single object)")
    else:
        log.warning("Could not register org.kde.krunner — another instance may hold the name")

    def _release_dbus():
        if not dbus_registered:
            return
        try:
            bus.unregisterObject("/App")
            bus.unregisterObject("/org/kde/krunner")
            bus.unregisterService("org.kde.krunner")
            log.debug("D-Bus service released before quit")
        except Exception:
            log.debug("D-Bus release failed", exc_info=True)

    app.aboutToQuit.connect(_release_dbus)

    def _on_conn():
        c = server.nextPendingConnection()
        if c:
            c.waitForReadyRead(500)
            c.close()
            window.toggle()

    server.newConnection.connect(_on_conn)
    if not server.listen(SOCKET_NAME):
        print(f"Warning: listen failed: {server.errorString()}", file=sys.stderr)

    signal.signal(signal.SIGTERM, lambda _, __: app.quit())
    signal.signal(signal.SIGINT, lambda _, __: app.quit())

    # Start hidden — window appears only when toggled via Alt+Space / D-Bus / socket
    sys.exit(app.exec())


def main():
    parser = argparse.ArgumentParser(
        description="Just",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  runner.py --check              validate modules\n"
               "  runner.py --query 'firefox'    headless query\n"
               "  runner.py --interactive        REPL mode\n"
               "  runner.py --debug              verbose logs (+ ~/.local/share/just/just-debug.log)\n"
               "  runner.py                      GUI (default)\n",
    )
    parser.add_argument("--check", action="store_true", help="Validate all modules load correctly")
    parser.add_argument("--query", "-q", type=str, help="Run a query headless, print JSON")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive REPL mode")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Verbose logging to stderr and ~/.local/share/just/just-debug.log",
    )
    args = parser.parse_args()

    if args.debug:
        os.environ["JUST_DEBUG"] = "1"
    from core.logutil import setup_just_logging

    setup_just_logging()

    if args.check:
        sys.exit(_cli_check())
    elif args.query:
        _cli_query(args.query)
    elif args.interactive:
        _cli_interactive()
    else:
        main_gui()


if __name__ == "__main__":
    main()

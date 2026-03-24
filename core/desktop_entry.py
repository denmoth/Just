"""Install ~/.local/share/applications/just.desktop once (StartupWMClass / integration)."""

import sys
from pathlib import Path


def ensure_just_desktop(*, repo_root: Path, executable: str | None = None) -> None:
    exe = executable or sys.executable
    runner = (repo_root / "runner.py").resolve()
    if not runner.is_file():
        return
    ddir = Path.home() / ".local/share/applications"
    try:
        ddir.mkdir(parents=True, exist_ok=True)
        path = ddir / "just.desktop"
        if path.exists():
            return
        text = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Version=1.1\n"
            "Name=Just\n"
            "GenericName=Application Launcher\n"
            "Comment=Just launcher\n"
            "Icon=system-search\n"
            f"Exec={exe} {runner}\n"
            "Terminal=false\n"
            "Categories=Utility;\n"
            "StartupNotify=false\n"
            "StartupWMClass=just\n"
        )
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass

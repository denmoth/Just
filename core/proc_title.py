"""Linux: show process as 'just' in top/htop/ps instead of 'python3'."""

import sys


def set_process_title(title: str = "just") -> None:
    if sys.platform != "linux":
        return
    name = (title or "just").strip() or "just"
    try:
        import setproctitle  # type: ignore[import-untyped]

        setproctitle.setproctitle(name[:127] if len(name) > 127 else name)
        return
    except ImportError:
        pass
    try:
        import ctypes

        libc = ctypes.CDLL(None)
        PR_SET_NAME = 15
        buf = ctypes.create_string_buffer(name[:15].encode("utf-8", "replace"))
        libc.prctl(PR_SET_NAME, ctypes.c_ulong(ctypes.addressof(buf)), 0, 0, 0)
    except Exception:
        pass

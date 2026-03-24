"""Debug logging: --debug / --дебаг or env JUST_DEBUG=1."""

from __future__ import annotations

import logging
import os
import sys

from core.config import DATA_DIR


def setup_just_logging() -> None:
    debug = os.environ.get("JUST_DEBUG") == "1"
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    if not debug:
        root.setLevel(logging.WARNING)
        return

    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DATA_DIR / "just-debug.log"
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.debug("Debug logging: stderr + %s", log_path)

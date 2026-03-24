"""Persist last launcher query for `!!` repeat (excludes shell lines `>` / `$`)."""

import json
from pathlib import Path

from core.config import DATA_DIR

_FILE = DATA_DIR / "last_repeat.json"


def _read() -> dict:
    try:
        if _FILE.exists():
            with open(_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("query"), str):
                return data
    except Exception:
        pass
    return {}


def load_last_repeat() -> str | None:
    q = _read().get("query", "")
    return q.strip() or None


def save_last_repeat_if_eligible(raw: str) -> None:
    q = (raw or "").strip()
    if not q or len(q) > 500:
        return
    if q.startswith((">", "$")):
        return
    if q in ("!!", "!", "!repeat"):
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump({"query": q}, f, ensure_ascii=False)
            f.flush()
            try:
                import os

                os.fsync(f.fileno())
            except OSError:
                pass
    except Exception:
        pass

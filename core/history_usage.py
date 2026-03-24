"""Selection history and usage frequency for ranking."""

import json
import os
from pathlib import Path

from core.config import DATA_DIR

_SELECTION_HISTORY = DATA_DIR / "selection_history.json"
_USAGE = DATA_DIR / "usage_counts.json"
_MAX_HISTORY = 20
_MAX_USAGE = 500
_USAGE_BOOST_CAP = 0.22

# In-memory copy: avoids re-reading JSON on every keystroke during sort.
_usage_memory: dict[str, int] | None = None


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: Path, data) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
    except Exception:
        pass


def load_selection_history() -> list[str]:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    data = _load_json(_SELECTION_HISTORY, [])
    if isinstance(data, list):
        return [str(x) for x in data if x][: _MAX_HISTORY]
    return []


def append_selection_history(entry: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    s = entry.strip()
    if len(s) < 1 or s.startswith("."):
        return
    hist = load_selection_history()
    hist = [x for x in hist if x.lower() != s.lower()]
    hist.insert(0, s)
    hist = hist[:_MAX_HISTORY]
    _save_json(_SELECTION_HISTORY, hist)


def load_usage() -> dict[str, int]:
    data = _load_json(_USAGE, {})
    if isinstance(data, dict):
        return {str(k): int(v) for k, v in data.items() if int(v) > 0}
    return {}


def _usage_map() -> dict[str, int]:
    global _usage_memory
    if _usage_memory is None:
        _usage_memory = load_usage()
    return _usage_memory


def warmup_usage_cache() -> None:
    """Call once at GUI startup so first keystroke does not hit disk."""
    _usage_map()


def invalidate_usage_cache() -> None:
    global _usage_memory
    _usage_memory = None


def bump_usage(key: str) -> None:
    k = key.strip()
    if len(k) < 2:
        return
    u = _usage_map()
    u[k] = u.get(k, 0) + 1
    if len(u) > _MAX_USAGE:
        items = sorted(u.items(), key=lambda x: -x[1])[: _MAX_USAGE // 2]
        u.clear()
        u.update(dict(items))
    _save_json(_USAGE, dict(u))


def usage_count(key: str) -> int:
    k = key.strip()
    if not k:
        return 0
    return _usage_map().get(k, 0)


def usage_multiplier(key: str) -> float:
    k = key.strip()
    if not k:
        return 1.0
    n = _usage_map().get(k, 0)
    return 1.0 + min(n * 0.022, _USAGE_BOOST_CAP)

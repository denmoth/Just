import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

# Parent sets this on the indexer subprocess so it does not recurse or re-copy legacy twice.
SKIP_INDEXER_CHILD_ENV = "JUST_SKIP_INDEXER_SPAWN"
# When set (e.g. by scripts/start-detached.sh), runner does not spawn indexer — a separate service runs it.
NO_SPAWN_INDEXER_ENV = "JUST_NO_SPAWN_INDEXER"

APP_NAME = "Just"
SOCKET_NAME = "just-v2"

home = Path.home()
DATA_DIR = home / ".local" / "share" / "just"
TIMERS_FILE = DATA_DIR / "timers.json"

MAX_RESULTS = 7
WINDOW_WIDTH = 640
PREVIEW_WIDTH = 310
CORNER_RADIUS = 10
ITEM_HEIGHT = 48

CACHE_DIR = home / ".cache" / "just"
_LEGACY_CACHE_DIR = home / ".cache" / "krunner-enhanced"
CONFIG_DIR = home / ".config" / "just"
CONFIG_FILE = CONFIG_DIR / "config.json"

_CONTENT_DB_NAMES = ("content.db", "content.db-wal", "content.db-shm")


def sync_legacy_search_index(*, force: bool = False) -> None:
    """Copy FTS SQLite bundle from ~/.cache/krunner-enhanced into ~/.cache/just.

    With force=True, always replaces the Just index when legacy content.db exists.
    With force=False, skips if ~/.cache/just/content.db is newer or same mtime as legacy.
    """
    legacy_db = _LEGACY_CACHE_DIR / "content.db"
    if not legacy_db.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest_main = CACHE_DIR / "content.db"
    if not force:
        try:
            leg_mtime = legacy_db.stat().st_mtime
            if dest_main.exists() and dest_main.stat().st_mtime >= leg_mtime:
                return
        except OSError:
            return
    try:
        for name in _CONTENT_DB_NAMES:
            dest = CACHE_DIR / name
            if dest.exists():
                dest.unlink()
        for name in _CONTENT_DB_NAMES:
            src = _LEGACY_CACHE_DIR / name
            if src.exists():
                shutil.copy2(src, CACHE_DIR / name)
    except OSError:
        pass


_REPO_ROOT = Path(__file__).resolve().parent.parent
_INDEXER_SCRIPT = _REPO_ROOT / "indexer.py"


def spawn_content_indexer_restart() -> None:
    """Full legacy index copy (if present), then a background incremental indexer pass.

    Called only from the primary GUI instance (after single-instance socket check).
    """
    if os.environ.get(NO_SPAWN_INDEXER_ENV) == "1":
        return
    if os.environ.get(SKIP_INDEXER_CHILD_ENV) == "1":
        return
    if not _INDEXER_SCRIPT.is_file():
        return
    sync_legacy_search_index(force=True)
    env = {**os.environ, SKIP_INDEXER_CHILD_ENV: "1"}
    try:
        subprocess.Popen(
            [sys.executable, str(_INDEXER_SCRIPT)],
            cwd=str(_REPO_ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass

DESKTOP_DIRS: list[str] = [
    "/usr/share/applications",
    str(home / ".local/share/applications"),
    "/usr/local/share/applications",
    str(home / ".local/share/flatpak/exports/share/applications"),
    "/var/lib/flatpak/exports/share/applications",
]

_DEFAULT_CONFIG = {
    "index_dirs": [str(home)],
    "exclude_patterns": [
        ".cache", "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".local/share/Trash", ".thumbnails", ".cargo", ".npm", ".rustup",
        ".local/share/baloo", ".local/share/akonadi",
    ],
    "weather_cache_minutes": 60,
    "groq_api_key": "",
    "ai_auto_fallback": True,
    "ocr_enabled": False,
    "index_interval_minutes": 30,
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            return {**_DEFAULT_CONFIG, **cfg}
        except Exception:
            pass
    with open(CONFIG_FILE, "w") as f:
        json.dump(_DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    return dict(_DEFAULT_CONFIG)


CFG = load_config()


def _api_get(url: str, timeout: float = 4.0) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Just/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _cached_api(cache_file: str, url: str, max_age_seconds: int) -> Optional[dict]:
    path = CACHE_DIR / cache_file
    if path.exists():
        try:
            age = time.time() - path.stat().st_mtime
            if age < max_age_seconds:
                with open(path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
    data = _api_get(url)
    if data:
        try:
            with open(path, "w") as f:
                json.dump(data, f)
        except Exception:
            pass
        return data
    if path.exists():
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None

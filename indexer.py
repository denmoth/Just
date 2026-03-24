#!/usr/bin/env python3
"""Content indexer for Just — builds FTS5 search index."""

import os
import sys
import sqlite3
import subprocess
import time
from pathlib import Path

from core.config import (
    CACHE_DIR,
    SKIP_INDEXER_CHILD_ENV,
    load_config,
    sync_legacy_search_index,
)

home = Path.home()
DB_PATH = CACHE_DIR / "content.db"

DEFAULT_EXCLUDES = [
    ".cache", "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".local/share/Trash", ".thumbnails", ".cargo", ".npm", ".rustup",
    ".local/share/baloo", ".local/share/akonadi", ".steam",
    ".local/share/Steam", ".wine",
]

TEXT_EXTS = {
    ".txt", ".md", ".rst", ".log", ".csv", ".tsv",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".lua",
    ".sh", ".bash", ".zsh", ".fish", ".ps1",
    ".html", ".css", ".scss", ".less", ".xml", ".yaml", ".yml",
    ".json", ".toml", ".ini", ".cfg", ".conf",
    ".sql", ".graphql", ".proto",
    ".tex", ".bib",
}

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def should_skip(path: str, excludes: list[str]) -> bool:
    for ex in excludes:
        if f"/{ex}/" in path or path.endswith(f"/{ex}"):
            return True
    return False


def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        try:
            out = subprocess.run(
                ["pdftotext", path, "-"],
                capture_output=True, text=True, timeout=30,
            )
            return out.stdout[:50000]
        except Exception:
            return ""

    if ext in (".docx",):
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(path) as z:
                with z.open("word/document.xml") as f:
                    tree = ET.parse(f)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            texts = [node.text for node in tree.iter("{%s}t" % ns["w"]) if node.text]
            return " ".join(texts)[:50000]
        except Exception:
            return ""

    if ext in TEXT_EXTS:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(50000)
        except Exception:
            return ""

    return ""


def build_index():
    cfg = load_config()
    index_dirs = cfg.get("index_dirs", [str(home)])
    excludes = cfg.get("exclude_patterns", DEFAULT_EXCLUDES)
    ocr_enabled = cfg.get("ocr_enabled", False)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime REAL)")
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(path, content)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()

    existing = {}
    for row in conn.execute("SELECT path, mtime FROM files"):
        existing[row[0]] = row[1]

    indexed = 0
    skipped = 0
    errors = 0

    indexable_exts = TEXT_EXTS | {".pdf", ".docx"}
    if ocr_enabled:
        indexable_exts |= {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}

    for base_dir in index_dirs:
        for dirpath, dirnames, filenames in os.walk(base_dir):
            if should_skip(dirpath, excludes):
                dirnames.clear()
                continue

            dirnames[:] = [d for d in dirnames if not should_skip(os.path.join(dirpath, d), excludes)]

            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                ext = os.path.splitext(fn)[1].lower()
                if ext not in indexable_exts:
                    continue

                try:
                    st = os.stat(fp)
                    if st.st_size > MAX_FILE_SIZE or st.st_size == 0:
                        continue
                    mtime = st.st_mtime
                except OSError:
                    continue

                if fp in existing and existing[fp] >= mtime:
                    skipped += 1
                    continue

                if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff") and ocr_enabled:
                    try:
                        out = subprocess.run(
                            ["tesseract", fp, "stdout", "-l", "rus+eng"],
                            capture_output=True, text=True, timeout=30,
                        )
                        text = out.stdout.strip()
                    except Exception:
                        text = ""
                else:
                    text = extract_text(fp)

                if not text.strip():
                    skipped += 1
                    continue

                try:
                    conn.execute("DELETE FROM content_fts WHERE path = ?", (fp,))
                    conn.execute("INSERT INTO content_fts (path, content) VALUES (?, ?)", (fp, text))
                    conn.execute(
                        "INSERT OR REPLACE INTO files (path, mtime) VALUES (?, ?)", (fp, mtime)
                    )
                    indexed += 1
                except Exception:
                    errors += 1

                if indexed % 100 == 0:
                    conn.commit()
                    print(f"  indexed: {indexed}, skipped: {skipped}", flush=True)

    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_run', ?)",
        (str(time.time()),)
    )
    conn.commit()
    conn.close()

    print(f"Done: indexed={indexed}, skipped={skipped}, errors={errors}")


def daemon_mode():
    cfg = load_config()
    interval = cfg.get("index_interval_minutes", 30) * 60
    print(f"Content indexer daemon started (interval: {interval}s)")
    while True:
        try:
            print(f"[{time.strftime('%H:%M:%S')}] Starting index build...")
            build_index()
        except Exception as e:
            print(f"Error during indexing: {e}", file=sys.stderr)
        time.sleep(interval)


if __name__ == "__main__":
    from core.proc_title import set_process_title

    set_process_title("just-indexer")
    if os.environ.get(SKIP_INDEXER_CHILD_ENV) != "1":
        sync_legacy_search_index(force=True)
    if "--daemon" in sys.argv:
        daemon_mode()
    else:
        build_index()

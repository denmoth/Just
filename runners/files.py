import os
import re
import json
import sqlite3
import subprocess
import threading

from core.search import SearchResult, switch_layout, EN_TO_RU, RU_TO_EN, _xdg_open
from core.config import home, DATA_DIR, CACHE_DIR, CFG

_FILE_ICONS = {
    "pdf": "application-pdf", "doc": "x-office-document", "docx": "x-office-document",
    "xls": "x-office-spreadsheet", "xlsx": "x-office-spreadsheet",
    "ppt": "x-office-presentation", "pptx": "x-office-presentation",
    "txt": "text-plain", "md": "text-x-markdown",
    "py": "text-x-python", "js": "text-x-javascript", "ts": "text-x-javascript",
    "html": "text-html", "css": "text-css", "json": "text-x-json",
    "rs": "text-x-rust", "go": "text-x-go", "java": "text-x-java",
    "cpp": "text-x-c++src", "c": "text-x-csrc", "h": "text-x-chdr",
    "sh": "text-x-script", "bash": "text-x-script",
    "png": "image-png", "jpg": "image-jpeg", "jpeg": "image-jpeg",
    "gif": "image-gif", "svg": "image-svg+xml", "webp": "image-webp",
    "mp3": "audio-mp3", "flac": "audio-flac", "wav": "audio-x-wav",
    "ogg": "audio-ogg", "m4a": "audio-mp4",
    "mp4": "video-mp4", "mkv": "video-x-matroska", "avi": "video-x-msvideo",
    "webm": "video-webm", "mov": "video-quicktime",
    "zip": "application-zip", "tar": "application-x-tar",
    "gz": "application-gzip", "rar": "application-rar",
    "iso": "application-x-cd-image",
}


def _file_icon(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _FILE_ICONS.get(ext, "text-x-generic" if ext else "folder")


class FileRunner:
    def __init__(self):
        self._freq: dict[str, int] = {}
        self._load_freq()

    def _load_freq(self):
        p = DATA_DIR / "file_freq.json"
        if p.exists():
            try:
                with open(p) as f:
                    self._freq = json.load(f)
            except Exception:
                pass

    def _save_freq(self):
        try:
            with open(DATA_DIR / "file_freq.json", "w") as f:
                json.dump(self._freq, f)
        except Exception:
            pass

    def _bump(self, path: str):
        self._freq[path] = self._freq.get(path, 0) + 1
        threading.Thread(target=self._save_freq, daemon=True).start()

    def match(self, query: str) -> list[SearchResult]:
        q = query.strip()
        if len(q) < 4 or q.startswith(("!", ">", "$", "=")):
            return []
        try:
            out = subprocess.run(
                ["plocate", "-i", "-l", "15", "--", q],
                capture_output=True, text=True, timeout=1,
            )
            paths = out.stdout.strip().split("\n") if out.stdout.strip() else []
        except Exception:
            return []

        excludes = CFG.get("exclude_patterns", [])

        filtered = []
        for p in paths:
            if any(ex in p for ex in excludes):
                continue
            if not os.path.exists(p):
                continue
            filtered.append(p)

        filtered.sort(key=lambda p: -self._freq.get(p, 0))

        results = []
        for p in filtered[:5]:
            name = os.path.basename(p)
            parent = os.path.dirname(p).replace(str(home), "~")
            is_dir = os.path.isdir(p)
            icon = "folder" if is_dir else _file_icon(p)
            try:
                size = os.path.getsize(p) if not is_dir else 0
                if size > 1073741824:
                    sz = f"{size / 1073741824:.1f} GB"
                elif size > 1048576:
                    sz = f"{size / 1048576:.1f} MB"
                elif size > 1024:
                    sz = f"{size / 1024:.0f} KB"
                elif size > 0:
                    sz = f"{size} B"
                else:
                    sz = ""
            except Exception:
                sz = ""

            sub = parent + (f"  ({sz})" if sz else "")
            score = 0.7
            if name.lower().startswith(q.lower()):
                score = 0.85
            freq = self._freq.get(p, 0)
            score += min(freq * 0.02, 0.1)

            results.append(SearchResult(
                title=name, subtitle=sub,
                icon_name=icon, score=score,
                category="Файлы", file_path=p,
                action=lambda fp=p: self._open_file(fp),
            ))
        return results

    def _open_file(self, path: str):
        self._bump(path)
        _xdg_open(path)


class ContentRunner:
    _DB_PATH = CACHE_DIR / "content.db"
    _PREFIX_RE = re.compile(r"^(?:в:|content:|search:|поиск:)\s*(.+)$", re.I)

    def match(self, query: str) -> list[SearchResult]:
        m = self._PREFIX_RE.match(query.strip())
        if not m:
            return []
        q = m.group(1).strip()
        if len(q) < 3:
            return []
        if not self._DB_PATH.exists():
            return [SearchResult(
                title="Индекс не создан",
                subtitle="Запустите: python3 indexer.py для индексации файлов",
                icon_name="dialog-information", score=0.8,
                category="Поиск", action=lambda: None,
            )]
        try:
            conn = sqlite3.connect(str(self._DB_PATH), timeout=60.0)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT path, snippet(content_fts, 0, '>>>', '<<<', '...', 30) AS snip "
                "FROM content_fts WHERE content_fts MATCH ? ORDER BY rank LIMIT 7",
                (q,)
            ).fetchall()
            conn.close()
        except Exception:
            return []

        results = []
        for row in rows:
            p = row["path"]
            snip = row["snip"].replace("\n", " ").strip()
            name = os.path.basename(p)
            results.append(SearchResult(
                title=name, subtitle=snip,
                icon_name=_file_icon(p), score=0.8,
                category="Содержимое", file_path=p,
                action=lambda fp=p: _xdg_open(fp),
            ))
        return results


class NaturalLanguageRunner:
    _PATTERNS = [
        (re.compile(r"(?:файлы?|files?)\s+(?:за\s+)?(?:вчера|yesterday)", re.I),
         lambda: ("find", str(home), "-maxdepth", "4", "-type", "f",
                  "-mtime", "0", "-not", "-path", "*/.cache/*")),
        (re.compile(r"(?:файлы?|files?)\s+(?:за\s+)?(?:сегодня|today)", re.I),
         lambda: ("find", str(home), "-maxdepth", "4", "-type", "f",
                  "-mmin", "-720", "-not", "-path", "*/.cache/*")),
        (re.compile(r"(?:документы?|documents?)\s+(?:за\s+)?(?:(?:эту\s+)?неделю?|(?:this\s+)?week)", re.I),
         lambda: ("find", str(home), "-maxdepth", "4", "-type", "f",
                  "-mtime", "-7", "-not", "-path", "*/.cache/*",
                  "(", "-name", "*.pdf", "-o", "-name", "*.docx", "-o",
                  "-name", "*.txt", "-o", "-name", "*.md", "-o",
                  "-name", "*.xlsx", "-o", "-name", "*.pptx", ")")),
        (re.compile(r"(?:фото|photos?|картинки?|images?)\s+(?:за\s+)?(?:(?:эту\s+)?неделю?|(?:this\s+)?week)", re.I),
         lambda: ("find", str(home / "Pictures"), "-maxdepth", "4", "-type", "f",
                  "-mtime", "-7")),
    ]

    def match(self, query: str) -> list[SearchResult]:
        q = query.strip()
        if len(q) < 5:
            return []

        for variant in (q, switch_layout(q, EN_TO_RU), switch_layout(q, RU_TO_EN)):
            for pat, cmd_fn in self._PATTERNS:
                if pat.search(variant):
                    try:
                        cmd = cmd_fn()
                        out = subprocess.run(
                            cmd, capture_output=True, text=True, timeout=3,
                        )
                        files = [f for f in out.stdout.strip().split("\n") if f][:7]
                    except Exception:
                        files = []

                    if not files:
                        return [SearchResult(
                            title="Ничего не найдено",
                            subtitle=variant,
                            icon_name="dialog-information", score=0.7,
                            category="Файлы", action=lambda: None,
                        )]

                    results = []
                    for fp in files:
                        name = os.path.basename(fp)
                        parent = os.path.dirname(fp).replace(str(home), "~")
                        results.append(SearchResult(
                            title=name, subtitle=parent,
                            icon_name=_file_icon(fp), score=0.75,
                            category="Файлы",
                            action=lambda p=fp: _xdg_open(p),
                        ))
                    return results
        return []


RUNNERS = [FileRunner(), ContentRunner(), NaturalLanguageRunner()]

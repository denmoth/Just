"""Theme icon names for past queries shown in the idle history list."""

import os
import re


_EXT_ICONS: dict[str, str] = {
    ".pdf": "application-pdf",
    ".png": "image-x-generic",
    ".jpg": "image-x-generic",
    ".jpeg": "image-x-generic",
    ".gif": "image-x-generic",
    ".webp": "image-x-generic",
    ".svg": "image-x-generic",
    ".mp3": "audio-x-generic",
    ".flac": "audio-x-generic",
    ".ogg": "audio-x-generic",
    ".mp4": "video-x-generic",
    ".mkv": "video-x-generic",
    ".zip": "package-x-generic",
    ".tar": "package-x-generic",
    ".gz": "package-x-generic",
    ".py": "text-x-python",
    ".rs": "text-x-script",
    ".js": "text-x-script",
    ".ts": "text-x-script",
    ".json": "text-x-json",
    ".md": "text-markdown",
    ".txt": "text-plain",
    ".desktop": "application-x-desktop",
}


def icon_for_history_query(q: str) -> str:
    s = (q or "").strip()
    if not s:
        return "document-open-recent"
    low = s.lower()

    if low.startswith(">") or low.startswith("$"):
        return "utilities-terminal"
    if low.startswith("="):
        return "accessories-calculator"
    if low.startswith("!g ") or low.startswith("!w ") or low.startswith("!y "):
        return "applications-internet"
    if low.startswith(".web ") or low.startswith(".веб "):
        return "applications-internet"
    if low.startswith(".app ") or low.startswith(".апп "):
        return "preferences-desktop-apps"
    if low.startswith(".file ") or low.startswith(".файл "):
        return "folder"
    if low.startswith("погода"):
        return "weather-clear"
    if low.startswith("http://") or low.startswith("https://"):
        return "applications-internet"
    if low.startswith("?"):
        return "dialog-question"

    path_candidate = os.path.expanduser(s)
    if s.startswith(("/", "~/", "~")) or (len(s) > 1 and s[1] == ":" and s[0].isalpha()):
        ext = os.path.splitext(path_candidate)[1].lower()
        return _EXT_ICONS.get(ext, "text-x-generic")

    if re.match(r"^[a-z0-9._-]+$", low) and "." not in low and len(low) <= 48:
        return "applications-other"

    return "document-open-recent"

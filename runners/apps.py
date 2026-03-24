import os
import re
import subprocess
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from core.search import SearchResult, multi_layout_score
from core.config import DESKTOP_DIRS


@dataclass
class AppEntry:
    name: str = ""
    name_ru: str = ""
    generic_name: str = ""
    generic_name_ru: str = ""
    comment: str = ""
    comment_ru: str = ""
    exec_cmd: str = ""
    icon_name: str = ""
    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    terminal: bool = False
    desktop_file: str = ""


def parse_desktop_file(path: str) -> Optional[AppEntry]:
    entry = AppEntry()
    entry.desktop_file = path
    inside = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line == "[Desktop Entry]":
                    inside = True
                    continue
                if line.startswith("["):
                    if inside:
                        break
                    continue
                if not inside or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                if k == "Name":
                    entry.name = v
                elif k == "Name[ru]":
                    entry.name_ru = v
                elif k == "GenericName":
                    entry.generic_name = v
                elif k == "GenericName[ru]":
                    entry.generic_name_ru = v
                elif k == "Comment":
                    entry.comment = v
                elif k == "Comment[ru]":
                    entry.comment_ru = v
                elif k == "Exec":
                    entry.exec_cmd = v
                elif k == "Icon":
                    entry.icon_name = v
                elif k == "Categories":
                    entry.categories = [c for c in v.split(";") if c]
                elif k == "Keywords":
                    entry.keywords = [x.lower() for x in v.split(";") if x]
                elif k == "Terminal":
                    entry.terminal = v.lower() == "true"
                elif k in ("NoDisplay", "Hidden"):
                    if v.lower() == "true":
                        return None
    except Exception:
        return None
    return entry if entry.name else None


def load_all_apps() -> list[AppEntry]:
    apps: list[AppEntry] = []
    seen: set[str] = set()
    for d in DESKTOP_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".desktop"):
                continue
            if fn in seen:
                continue
            a = parse_desktop_file(os.path.join(d, fn))
            if a:
                seen.add(fn)
                apps.append(a)
    return sorted(apps, key=lambda a: a.name.lower())


# ── Semantic Tags ──

EXTRA_TAGS: dict[str, list[str]] = {
    "transmission": [
        "torrent", "bittorrent", "download", "seed", "magnet", "p2p",
        "торрент", "скачать", "загрузить", "раздача", "магнет", "пиринг",
        "файлы", "скачивание", "загрузка", "раздавать", "трансмишн",
    ],
    "thunderbird": [
        "mail", "email", "e-mail", "inbox", "smtp", "imap",
        "почта", "письмо", "письма", "мейл", "имейл", "электронная почта",
        "входящие", "отправить письмо", "рассылка", "ящик",
    ],
    "brave": [
        "browser", "chrome", "chromium", "web", "internet", "google",
        "браузер", "интернет", "хром", "сайт", "сайты", "поиск", "гугл",
        "браве", "страница", "вкладка", "закладки", "ссылка", "открыть сайт",
    ],
    "steam": [
        "games", "gaming", "valve", "play", "gamer", "store",
        "игры", "игра", "стим", "геймер", "магазин игр", "поиграть", "гейминг",
    ],
    "discord": [
        "chat", "voice", "voip", "community", "server",
        "чат", "дискорд", "дс", "ds", "общение", "мессенджер", "голос",
        "звонок", "голосовой", "сервер",
    ],
    "telegram": [
        "chat", "messenger", "messages",
        "чат", "мессенджер", "телеграм", "тг", "телега", "сообщения",
        "канал", "бот", "переписка",
    ],
    "dolphin": [
        "files", "explorer", "finder", "folders", "nautilus", "manager",
        "файлы", "проводник", "папки", "менеджер файлов", "дольфин",
        "каталог", "диск", "открыть", "документы", "загрузки",
    ],
    "konsole": [
        "terminal", "shell", "bash", "zsh", "cli", "command",
        "терминал", "консоль", "командная строка", "шелл", "команда",
    ],
    "alacritty": [
        "terminal", "shell", "bash", "zsh", "cli", "gpu",
        "терминал", "консоль", "алакритти",
    ],
    "kate": [
        "editor", "code", "ide", "programming", "text",
        "редактор", "код", "программирование", "текст", "блокнот",
        "писать", "написать", "набросать", "заметка",
    ],
    "cursor ai": [
        "editor", "code", "ide", "ai", "vscode", "programming",
        "редактор", "код", "программирование", "курсор", "ии",
    ],
    "kwrite": [
        "editor", "text", "notepad",
        "редактор", "текст", "блокнот", "заметка", "писать",
    ],
    "system settings": [
        "settings", "preferences", "config", "control panel",
        "настройки", "параметры", "конфигурация", "панель управления",
        "опции", "управление",
    ],
    "параметры системы": [
        "settings", "preferences", "config",
        "настройки", "параметры", "конфигурация", "опции",
    ],
    "spectacle": [
        "screenshot", "screen capture", "print screen", "snip",
        "скриншот", "снимок экрана", "скрин", "захват", "фото экрана",
        "принтскрин", "запись экрана",
    ],
    "gwenview": [
        "images", "photos", "viewer", "picture", "gallery",
        "изображения", "фото", "просмотр", "картинки", "галерея",
        "фотографии", "просмотрщик", "рисунок",
    ],
    "mpv media player": [
        "video", "movie", "player", "media", "music", "audio",
        "видео", "фильм", "плеер", "музыка", "кино", "медиа",
        "воспроизвести", "посмотреть", "смотреть",
    ],
    "haruna": [
        "video", "movie", "player", "media",
        "видео", "фильм", "плеер", "кино", "медиа", "смотреть",
    ],
    "lampa": [
        "movies", "series", "tv", "streaming", "torrent",
        "фильмы", "сериалы", "кино", "стриминг", "лампа",
        "смотреть", "торрент", "онлайн",
    ],
    "kcalc": [
        "calculator", "math", "calc",
        "калькулятор", "математика", "вычисления", "посчитать",
    ],
    "ark": [
        "archive", "zip", "tar", "rar", "extract", "compress",
        "архив", "архиватор", "распаковка", "сжатие",
        "запаковать", "распаковать",
    ],
    "filelight": [
        "disk", "space", "usage", "storage", "clean",
        "диск", "место", "хранилище", "очистка", "занято", "размер",
    ],
    "pamac": [
        "packages", "software", "install", "update", "pacman", "aur",
        "пакеты", "установка", "обновление", "программы", "магазин",
        "скачать", "загрузить", "удалить", "софт", "приложение",
        "установить", "обновить", "менеджер пакетов", "памак",
    ],
    "менеджер программ": [
        "packages", "software", "install", "update",
        "пакеты", "установка", "обновление", "программы", "магазин",
        "скачать", "загрузить", "установить", "обновить",
    ],
    "prism launcher": [
        "minecraft", "mc", "game", "mojang",
        "майнкрафт", "майн", "игра", "блоки",
    ],
    "kde connect": [
        "phone", "sync", "android", "mobile", "smartphone",
        "телефон", "синхронизация", "андроид", "мобильный", "смартфон",
        "пересылка",
    ],
    "system monitor": [
        "processes", "cpu", "ram", "memory", "task manager", "htop",
        "процессы", "нагрузка", "память", "диспетчер задач", "мониторинг",
        "температура", "управление",
    ],
    "системный монитор": [
        "processes", "cpu", "ram",
        "процессы", "нагрузка", "диспетчер задач", "температура",
    ],
    "volume control": [
        "audio", "sound", "speaker", "microphone", "headphones",
        "звук", "громкость", "динамик", "микрофон", "наушники",
        "аудио", "колонки",
    ],
    "громкость": [
        "audio", "sound", "speaker",
        "звук", "динамик", "микрофон", "наушники", "аудио", "колонки",
    ],
    "emoji selector": ["emoji", "emoticon", "эмодзи", "смайл"],
    "kde partition manager": [
        "disk", "partition", "format", "gparted",
        "диск", "раздел", "форматирование", "разметка",
    ],
    "vim": ["editor", "text", "code", "neovim", "редактор", "текст", "код", "вим"],
    "micro": ["editor", "text", "code", "редактор", "текст", "код"],
    "meld": ["diff", "compare", "merge", "git", "сравнение", "различия", "слияние"],
    "btop++": [
        "processes", "cpu", "monitor", "htop", "top",
        "процессы", "мониторинг", "нагрузка", "температура",
    ],
    "btrfs assistant": [
        "btrfs", "snapshots", "backup",
        "снапшоты", "бэкап", "восстановление", "откат",
    ],
    "cachyos hello": ["welcome", "help", "приветствие", "помощь", "гайд"],
    "cachyos kernel manager": ["kernel", "linux", "ядро", "линукс", "обновление ядра"],
    "info center": [
        "hardware", "system info", "specs",
        "оборудование", "информация", "характеристики", "железо",
    ],
    "информация о системе": [
        "hardware", "specs", "оборудование", "характеристики", "железо",
    ],
    "kwalletmanager": [
        "passwords", "wallet", "security",
        "пароли", "кошелёк", "безопасность", "ключи",
    ],
    "menu editor": ["menu", "applications", "меню", "приложения", "ярлыки"],
    "okular": [
        "pdf", "document", "reader", "ebook", "djvu", "epub",
        "документ", "читалка", "книга", "пдф", "просмотр", "чтение",
    ],
    "onlyoffice desktop editors": [
        "office", "word", "excel", "powerpoint", "document", "spreadsheet",
        "офис", "ворд", "эксель", "таблицы", "презентация", "документ",
        "текст", "написать", "редактировать", "docx", "xlsx", "pptx",
    ],
    "lutris": [
        "games", "gaming", "wine", "proton", "emulator", "gog",
        "игры", "игра", "лютрис", "эмулятор", "виндовые игры",
        "запустить игру",
    ],
    "mangohud": [
        "fps", "overlay", "monitor", "performance",
        "фпс", "оверлей", "мониторинг", "производительность",
    ],
    "kvantummanager": [
        "theme", "style", "qt", "appearance", "kvantum",
        "тема", "стиль", "оформление", "внешний вид", "квантум",
    ],
    "freetube": [
        "youtube", "video", "streaming", "watch",
        "ютуб", "видео", "стриминг", "смотреть", "подписки",
        "каналы", "ролик", "ролики",
    ],
}


CATEGORY_TAGS: dict[str, list[str]] = {
    "Audio": ["audio", "music", "sound", "аудио", "музыка", "звук"],
    "AudioVideo": ["media", "player", "медиа", "плеер"],
    "Development": ["code", "programming", "dev", "ide", "код", "разработка", "программирование"],
    "Education": ["learning", "education", "обучение", "образование"],
    "Game": ["game", "gaming", "play", "игра", "игры", "играть"],
    "Graphics": ["image", "photo", "design", "draw", "изображение", "фото", "дизайн", "рисование"],
    "Network": ["internet", "web", "интернет", "сеть"],
    "Office": ["office", "document", "spreadsheet", "офис", "документ", "таблица"],
    "Settings": ["settings", "config", "preferences", "настройки", "параметры", "конфигурация"],
    "System": ["system", "admin", "tool", "система", "администрирование", "инструмент"],
    "Utility": ["utility", "tool", "утилита", "инструмент"],
    "Video": ["video", "movie", "видео", "фильм", "кино"],
    "FileManager": ["files", "explorer", "файлы", "проводник"],
    "TextEditor": ["editor", "text", "редактор", "текст"],
    "TerminalEmulator": ["terminal", "console", "shell", "терминал", "консоль"],
    "WebBrowser": ["browser", "web", "браузер", "сайт"],
    "Email": ["email", "mail", "почта", "письмо", "мейл"],
    "InstantMessaging": ["chat", "messenger", "чат", "мессенджер"],
    "P2P": ["torrent", "download", "p2p", "торрент", "скачать", "загрузка"],
    "Photography": ["photo", "camera", "фото", "камера", "фотография"],
    "Music": ["music", "audio", "player", "музыка", "аудио", "плеер"],
    "Archiving": ["archive", "compress", "zip", "архив", "сжатие"],
    "Monitor": ["monitor", "performance", "cpu", "мониторинг", "производительность"],
    "Security": ["security", "password", "безопасность", "пароль"],
    "PackageManager": ["packages", "install", "update", "пакеты", "установка", "обновление"],
}


def get_extra_tags(app: AppEntry) -> list[str]:
    name = app.name.lower()
    tags = list(EXTRA_TAGS.get(name, []))
    for cat in app.categories:
        tags.extend(CATEGORY_TAGS.get(cat, []))
    tags.extend(app.keywords)
    if app.generic_name:
        tags.append(app.generic_name.lower())
    if app.generic_name_ru:
        tags.append(app.generic_name_ru.lower())
    return tags


class AppRunner:
    def __init__(self):
        self.apps = load_all_apps()
        self._start_refresh()

    def _start_refresh(self):
        def _loop():
            while True:
                time.sleep(120)
                try:
                    self.apps = load_all_apps()
                except Exception:
                    pass
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def match(self, query: str) -> list[SearchResult]:
        results = []
        q = query.lower().strip()
        if not q:
            return results
        for app in self.apps:
            best = 0.0
            s = multi_layout_score(q, app.name)
            best = max(best, s)
            if best >= 0.9:
                pass  # skip expensive checks
            else:
                if app.name_ru:
                    best = max(best, multi_layout_score(q, app.name_ru) * 0.97)
                if best < 0.8:
                    if app.generic_name:
                        best = max(best, multi_layout_score(q, app.generic_name) * 0.9)
                    if app.generic_name_ru:
                        best = max(best, multi_layout_score(q, app.generic_name_ru) * 0.88)
                    if best < 0.5:
                        for tag in get_extra_tags(app):
                            if q in tag or tag.startswith(q):
                                best = max(best, 0.85)
                                break
                            best = max(best, multi_layout_score(q, tag) * 0.85)
                            if best >= 0.7:
                                break

            if best > 0.35:
                t = app.name_ru or app.generic_name_ru or app.name
                results.append(SearchResult(
                    title=app.name,
                    subtitle=t if t != app.name else "",
                    icon_name=app.icon_name or "application-x-executable",
                    score=best * 0.95,
                    category="Приложения",
                    action=lambda exec_cmd=app.exec_cmd, terminal=app.terminal: self._launch(exec_cmd, terminal),
                ))
        results.sort(key=lambda r: -r.score)
        return results

    @staticmethod
    def _launch(exec_cmd: str, terminal: bool = False):
        cmd = re.sub(r"%[uUfFdDnNickvm]", "", exec_cmd).strip()
        if not terminal:
            try:
                subprocess.Popen(
                    cmd, shell=True,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        else:
            for t in ("konsole -e", "alacritty -e"):
                try:
                    subprocess.Popen(
                        f"{t} {cmd}", shell=True,
                        start_new_session=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    return
                except Exception:
                    pass


RUNNERS = [AppRunner()]

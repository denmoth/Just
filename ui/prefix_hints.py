"""One-line hint under the search field (only when relevant: text, “.”, or “!”)."""

from __future__ import annotations

from typing import Optional

_PREFIX_CHEATSHEET = (
    "Префикс: .app · .file · .web · .погода · .timer · .media · .конвертер"
)

_CAT_LABELS: dict[str, str] = {
    "app": "только приложения",
    "apps": "только приложения",
    "web": "только веб / закладки",
    "weather": "только погода",
    "погода": "только погода",
    "file": "только файлы",
    "файл": "только файлы",
    "content": "поиск по содержимому (в: …)",
    "в": "поиск по содержимому (в: …)",
    "timer": "таймеры и напоминания",
    "sys": "системные действия",
    "system": "системные действия",
    "term": "терминал",
    "shell": "терминал",
    "calc": "калькулятор",
    "конвертер": "валюта и единицы",
    "fx": "валюта и единицы",
    "kill": "завершение процессов",
    "media": "медиа-клавиши (playerctl)",
    "музыка": "медиа-клавиши (playerctl)",
}

_BANG_SHORT = "!бэнг: !g поиск · !w вики · !yt YouTube — пробел и запрос"


def prefix_hint(raw: str, cat_filt: Optional[str]) -> str:
    s = (raw or "").strip()
    low = s.lower()

    if cat_filt:
        what = _CAT_LABELS.get(cat_filt, cat_filt)
        return f".{cat_filt} — режим: {what}"

    if not s:
        return ""

    if low == "!!" or low.startswith("!! "):
        return "!! — повторить последнюю успешную команду (не сохраняются строки с > или $)"

    if s.startswith(".") and " " not in s:
        tail = s[1:].lower()
        if not tail:
            return _PREFIX_CHEATSHEET
        if tail in _CAT_LABELS:
            return f"{s} — {_CAT_LABELS[tail]} · пробел и запрос"
        return f"{s} — неизвестный префикс · примеры: .app .file .web"

    if s.startswith("!") and not s.startswith("!!"):
        if s.startswith("!g ") or s.startswith("!g\t"):
            return "!g — открыть поиск Google в браузере"
        if s.startswith("!w ") or s.startswith("!yt "):
            return "!w — Википедия · !yt — YouTube · !g — Google (см. !gh !tr !ya …)"
        if " " not in s:
            if s == "!":
                return _BANG_SHORT
            return f"{s} — пробел и запрос (!g …, !w …, !yt …)"

    if s.startswith(">"):
        return "> — команда shell: Enter — внешний терминал · Ctrl+Space — превью PTY (bash)"

    if s.startswith("$"):
        return "$ — то же, что > (shell)"

    if s.startswith("="):
        return "= — калькулятор (дроби, sin, sqrt…); Tab — часто выполняет первый результат"

    if s.startswith("?"):
        return "? — запрос к AI (нужен ключ в конфиге)"

    if s.startswith(".") and " " in s:
        dot = s.split(None, 1)[0].lower()
        key = dot[1:] if len(dot) > 1 else ""
        if key in _CAT_LABELS:
            return f"{dot} — {_CAT_LABELS[key]}"

    if low.startswith("напомни") or low.startswith("remind"):
        return "Напоминание: «напомни через 10 мин …» или «через 1ч текст» · будильник 14:30 текст"

    if "секундомер" in low or low.startswith("stopwatch"):
        return "Секундомер: Enter — старт/показать · «секундомер сброс» — обнулить"

    if low.startswith("таймер") or low.startswith("timer"):
        return "Таймер: «5 мин», «1ч 20м», «90 сек» или будильник «14:30 чай»"

    if any(
        x in low
        for x in (
            " в ",
            " во ",
            " to ",
            " -> ",
            "→",
        )
    ) and any(c.isdigit() for c in s):
        if any(
            cur in low
            for cur in (
                "usd",
                "eur",
                "rub",
                "руб",
                "долл",
                "евро",
                "₽",
                "$",
                "€",
            )
        ):
            return "Валюта: «100 usd в rub» · «50 € в руб»"
        return "Единицы: «5 миль в км» · «180 см в футы» · «25 c в f» · «2 л в мл»"

    return ""

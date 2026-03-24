import re
import subprocess
import threading
import time

from core.search import (
    SearchResult, smart_score, switch_layout,
    EN_TO_RU, RU_TO_EN, _run_cmd,
)


class SystemRunner:
    COMMANDS = [
        {
            "triggers": ["sleep", "suspend", "спящий", "сон", "спящий режим"],
            "title": "Спящий режим",
            "sub": "systemctl suspend",
            "icon": "system-suspend",
            "cmd": ["systemctl", "suspend"],
        },
        {
            "triggers": ["reboot", "restart", "перезагрузка", "перезагрузить", "ребут"],
            "title": "Перезагрузить",
            "sub": "systemctl reboot",
            "icon": "system-reboot",
            "cmd": ["systemctl", "reboot"],
        },
        {
            "triggers": ["shutdown", "poweroff", "выключить", "выключение"],
            "title": "Выключить ПК",
            "sub": "systemctl poweroff",
            "icon": "system-shutdown",
            "cmd": ["systemctl", "poweroff"],
        },
        {
            "triggers": ["lock", "блокировка", "заблокировать", "блок", "локскрин"],
            "title": "Заблокировать экран",
            "sub": "loginctl lock-session",
            "icon": "system-lock-screen",
            "cmd": ["loginctl", "lock-session"],
        },
        {
            "triggers": ["logout", "выход", "выйти", "log out"],
            "title": "Выйти из сессии",
            "sub": "Завершение сеанса",
            "icon": "system-log-out",
            "cmd": ["qdbus6", "org.kde.Shutdown", "/Shutdown", "logout"],
        },
    ]

    def match(self, query: str) -> list[SearchResult]:
        q = query.lower().strip()
        if len(q) < 2:
            return []
        results = []
        for ci in self.COMMANDS:
            best = 0.0
            for trigger in ci["triggers"]:
                for v in (q, switch_layout(q, EN_TO_RU), switch_layout(q, RU_TO_EN)):
                    best = max(best, smart_score(v, trigger))
            if best > 0.35:
                results.append(SearchResult(
                    title=ci["title"],
                    subtitle=ci["sub"],
                    icon_name=ci["icon"],
                    score=best,
                    category="Система",
                    action=lambda c=ci["cmd"]: _run_cmd(c),
                ))
        results.sort(key=lambda r: -r.score)
        return results


def _check_bluetooth() -> bool:
    try:
        out = subprocess.run(
            ["bluetoothctl", "show"], capture_output=True, text=True, timeout=2
        ).stdout
        return "yes" in out.split("Powered:")[1][:10] if "Powered:" in out else False
    except Exception:
        return False


def _check_wifi() -> bool:
    try:
        return subprocess.run(
            ["nmcli", "radio", "wifi"], capture_output=True, text=True, timeout=2
        ).stdout.strip() == "enabled"
    except Exception:
        return False


def _check_dark() -> bool:
    try:
        return "dark" in subprocess.run(
            ["kreadconfig6", "--file", "kdeglobals", "--group", "General",
             "--key", "ColorScheme"], capture_output=True, text=True, timeout=2
        ).stdout.lower()
    except Exception:
        return False


class SystemToggleRunner:
    """Toggles with background-cached state (refreshes every 10s instead of per-query)."""

    TOGGLES = [
        {
            "triggers": ["bluetooth", "блютуз", "блютус", "bt"],
            "title_on": "Bluetooth: Включить",
            "title_off": "Bluetooth: Выключить",
            "icon": "bluetooth-symbolic",
            "on": ["bluetoothctl", "power", "on"],
            "off": ["bluetoothctl", "power", "off"],
            "check_key": "bluetooth",
        },
        {
            "triggers": ["wifi", "вайфай", "wi-fi", "wireless", "беспроводная", "интернет сеть"],
            "title_on": "WiFi: Включить",
            "title_off": "WiFi: Выключить",
            "icon": "network-wireless-symbolic",
            "on": ["nmcli", "radio", "wifi", "on"],
            "off": ["nmcli", "radio", "wifi", "off"],
            "check_key": "wifi",
        },
        {
            "triggers": ["dark mode", "тёмная тема", "темная тема", "dark", "light mode",
                         "светлая тема", "тема"],
            "title_on": "Тёмная тема",
            "title_off": "Светлая тема",
            "icon": "preferences-desktop-theme-global",
            "on": ["lookandfeeltool", "--apply", "org.kde.breezedark.desktop"],
            "off": ["lookandfeeltool", "--apply", "org.kde.breeze.desktop"],
            "check_key": "dark",
        },
        {
            "triggers": ["не беспокоить", "do not disturb", "dnd", "тишина", "mute notifications"],
            "title_on": "Не беспокоить: Включить",
            "title_off": "Не беспокоить: Выключить",
            "icon": "notifications-disabled-symbolic",
            "on": ["dbus-send", "--session", "--dest=org.freedesktop.Notifications",
                   "/org/freedesktop/Notifications",
                   "org.freedesktop.Notifications.Inhibit",
                   "string:Just", "string:DND", "dict:string:string:"],
            "off": ["dbus-send", "--session", "--dest=org.freedesktop.Notifications",
                    "/org/freedesktop/Notifications",
                    "org.freedesktop.Notifications.UnInhibit", "uint32:0"],
            "check_key": "dnd",
        },
    ]

    _VOLUME_RE = re.compile(r"^(?:громкость|volume|звук|sound)\s*(\d+)\s*%?$", re.I)
    _BRIGHTNESS_RE = re.compile(r"^(?:яркость|brightness)\s*(\d+)\s*%?$", re.I)

    def __init__(self):
        self._state: dict[str, bool] = {
            "bluetooth": False, "wifi": False, "dark": False, "dnd": False,
        }
        self._start_bg_check()

    def _start_bg_check(self):
        def _loop():
            while True:
                try:
                    self._state["bluetooth"] = _check_bluetooth()
                    self._state["wifi"] = _check_wifi()
                    self._state["dark"] = _check_dark()
                except Exception:
                    pass
                time.sleep(10)
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def match(self, query: str) -> list[SearchResult]:
        q = query.lower().strip()
        if len(q) < 2:
            return []
        results = []

        for variant in (q, switch_layout(q, EN_TO_RU), switch_layout(q, RU_TO_EN)):
            m = self._VOLUME_RE.match(variant)
            if m:
                val = min(int(m.group(1)), 150)
                results.append(SearchResult(
                    title=f"Громкость: {val}%",
                    subtitle="Установить уровень громкости",
                    icon_name="audio-volume-high-symbolic", score=1.0,
                    category="Система",
                    action=lambda v=val: _run_cmd(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{v}%"]),
                ))
                return results

            m = self._BRIGHTNESS_RE.match(variant)
            if m:
                val = min(int(m.group(1)), 100)
                results.append(SearchResult(
                    title=f"Яркость: {val}%",
                    subtitle="Установить яркость экрана",
                    icon_name="display-brightness-symbolic", score=1.0,
                    category="Система",
                    action=lambda v=val: _run_cmd(
                        ["qdbus6", "org.kde.Solid.PowerManagement",
                         "/org/kde/Solid/PowerManagement/Actions/BrightnessControl",
                         "org.kde.Solid.PowerManagement.Actions.BrightnessControl.setBrightness",
                         str(v)]
                    ),
                ))
                return results

        for toggle in self.TOGGLES:
            best = 0.0
            for trigger in toggle["triggers"]:
                for v in (q, switch_layout(q, EN_TO_RU), switch_layout(q, RU_TO_EN)):
                    best = max(best, smart_score(v, trigger))
            if best > 0.4:
                is_on = self._state.get(toggle["check_key"], False)

                if is_on:
                    results.append(SearchResult(
                        title=toggle["title_off"],
                        subtitle="Сейчас включено — нажмите чтобы выключить",
                        icon_name=toggle["icon"], score=best,
                        category="Система",
                        action=lambda c=toggle["off"]: _run_cmd(c),
                    ))
                else:
                    results.append(SearchResult(
                        title=toggle["title_on"],
                        subtitle="Сейчас выключено — нажмите чтобы включить",
                        icon_name=toggle["icon"], score=best,
                        category="Система",
                        action=lambda c=toggle["on"]: _run_cmd(c),
                    ))
        results.sort(key=lambda r: -r.score)
        return results[:3]


RUNNERS = [SystemRunner(), SystemToggleRunner()]

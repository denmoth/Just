import subprocess
import urllib.parse

from core.search import (
    SearchResult, smart_score, switch_layout,
    EN_TO_RU, RU_TO_EN, _xdg_open, _kill_pids,
)


class WebRunner:
    BANGS = {
        "!g": ("Google", "https://www.google.com/search?q="),
        "!yt": ("YouTube", "https://www.youtube.com/results?search_query="),
        "!gh": ("GitHub", "https://github.com/search?q="),
        "!w": ("Wikipedia", "https://ru.wikipedia.org/wiki/Special:Search?search="),
        "!tr": ("Google Translate", "https://translate.google.com/?sl=auto&tl=ru&text="),
        "!r": ("Reddit", "https://www.reddit.com/search/?q="),
        "!ya": ("Яндекс", "https://yandex.ru/search/?text="),
        "!ali": ("AliExpress", "https://www.aliexpress.com/wholesale?SearchText="),
        "!aur": ("AUR", "https://aur.archlinux.org/packages?K="),
        "!maps": ("Google Maps", "https://www.google.com/maps/search/"),
    }

    def match(self, query: str) -> list[SearchResult]:
        q = query.strip()
        if not q.startswith("!"):
            return []
        parts = q.split(None, 1)
        bang = parts[0].lower()
        if bang in self.BANGS:
            name, url = self.BANGS[bang]
            terms = parts[1] if len(parts) > 1 else ""
            if terms:
                full = url + urllib.parse.quote(terms)
                preview = (
                    f"{name}\n\n"
                    f"Запрос: {terms}\n\n"
                    f"{full}\n\n"
                    "Enter — открыть в браузере"
                )
                return [SearchResult(
                    title=f"Искать «{terms}» в {name}",
                    subtitle=full[:72] + ("…" if len(full) > 72 else ""),
                    icon_name="internet-web-browser",
                    score=1.0,
                    category="Веб",
                    preview_kind="text",
                    preview_text=preview,
                    usage_key=f"bang:{bang}",
                    browse_url=full,
                    action=lambda u=full: _xdg_open(u),
                )]
            return [SearchResult(
                title=f"Введите запрос для {name}",
                subtitle=f"Пример: {bang} ваш запрос",
                icon_name="internet-web-browser",
                score=0.5,
                category="Веб",
                preview_kind="text",
                preview_text=f"Быстрый поиск: {name}\n\nВведите текст после {bang}",
                action=lambda: None,
            )]
        results = []
        for b, (n, _) in list(self.BANGS.items())[:6]:
            results.append(SearchResult(
                title=f"{b} — {n}",
                subtitle="Веб-поиск",
                icon_name="internet-web-browser",
                score=0.5,
                category="Веб",
                preview_kind="text",
                preview_text=f"{n}\n\nИспользование: {b} ваш запрос",
                action=lambda: None,
            ))
        return results


class KillRunner:
    _RE = __import__("re").compile(
        r"^(?:kill|убить|убей|завершить|стоп)\s+(.+)$", __import__("re").I
    )

    def match(self, query: str) -> list[SearchResult]:
        target = None
        for v in (query.strip(), switch_layout(query.strip(), EN_TO_RU),
                  switch_layout(query.strip(), RU_TO_EN)):
            m = self._RE.match(v)
            if m:
                target = m.group(1)
                break
        if not target:
            return []
        try:
            out = subprocess.check_output(
                ["ps", "-eo", "pid,comm", "--no-headers"],
                timeout=2, text=True,
            )
        except Exception:
            return []
        procs: dict[str, list[str]] = {}
        for line in out.split("\n"):
            parts = line.split()
            if len(parts) < 2:
                continue
            procs.setdefault(parts[1].lower(), []).append(parts[0])
        results = []
        tgt = target.lower()
        for pname, pids in procs.items():
            sc = smart_score(tgt, pname)
            if sc > 0.3:
                ps = ", ".join(pids[:3])
                if len(pids) > 3:
                    ps += f" (+{len(pids) - 3})"
                results.append(SearchResult(
                    title="Убить: " + pname,
                    subtitle="PID: " + ps,
                    icon_name="process-stop",
                    score=sc,
                    category="Процессы",
                    action=lambda p=list(pids): _kill_pids(p),
                ))
        results.sort(key=lambda r: -r.score)
        return results[:5]


RUNNERS = [WebRunner(), KillRunner()]

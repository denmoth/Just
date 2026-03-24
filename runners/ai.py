"""
AI Runner — async queries to Groq API with debounce.

Works WITHOUT '?' prefix. The window uses a 1.5s debounce timer:
if the user stops typing for 1.5s and other runners returned few results,
AIRunner is queried asynchronously in a background thread.

The runner can also be triggered explicitly with '?' prefix (instant, still async).
"""

import json
import urllib.request
import threading

from core.search import SearchResult, _clipboard, _xdg_open
from core.config import CFG, CONFIG_FILE


class AIRunner:
    _API_URL = "https://api.groq.com/openai/v1/chat/completions"
    is_ai = True

    def match(self, query: str) -> list[SearchResult]:
        """Synchronous match for explicit '?' queries. Returns loading placeholder."""
        q = query.strip()
        if q.startswith("?"):
            prompt = q[1:].strip()
            if len(prompt) < 2:
                return [SearchResult(
                    title="Задайте вопрос AI (Groq)",
                    subtitle="Пример: ? как узнать IP в терминале",
                    icon_name="dialog-question", score=0.5,
                    category="AI", action=lambda: None,
                )]
        return []

    def query_async(self, prompt: str, callback) -> None:
        """Run AI query in background thread. Calls callback(results) when done."""
        api_key = CFG.get("groq_api_key", "") or CFG.get("grok_api_key", "")
        if not api_key:
            callback([SearchResult(
                title="Groq API ключ не настроен",
                subtitle="Добавьте groq_api_key в ~/.config/just/config.json",
                icon_name="dialog-warning", score=0.9,
                category="AI", action=lambda: _xdg_open(str(CONFIG_FILE)),
            )])
            return

        def _do():
            try:
                body = json.dumps({
                    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    "messages": [
                        {"role": "system", "content":
                         "Ты — помощник в Linux KDE (CachyOS, Arch). Отвечай кратко, "
                         "1-3 предложения. Если нужна команда — дай только команду. "
                         "Отвечай на языке запроса."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 300,
                    "temperature": 0.3,
                }).encode()

                req = urllib.request.Request(
                    self._API_URL,
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode())

                answer = data["choices"][0]["message"]["content"].strip()
                lines = answer.split("\n")
                title = lines[0][:100]
                subtitle = " ".join(lines[1:])[:150] if len(lines) > 1 else ""

                callback([SearchResult(
                    title=title, subtitle=subtitle,
                    icon_name="dialog-information", score=0.95,
                    category="AI",
                    action=lambda a=answer: _clipboard(a),
                )])
            except Exception as e:
                callback([SearchResult(
                    title="AI: ошибка запроса",
                    subtitle=str(e)[:100],
                    icon_name="dialog-error", score=0.5,
                    category="AI", action=lambda: None,
                )])

        t = threading.Thread(target=_do, daemon=True)
        t.start()


RUNNERS = [AIRunner()]

"""One-shot RAM/uptime line for the idle (empty query) dashboard."""

import subprocess

from core.search import SearchResult


def idle_resource_result() -> SearchResult:
    body = "—"
    try:
        r = subprocess.run(
            [
                "sh",
                "-c",
                'echo "── Память ──"; free -h 2>/dev/null | head -4; echo; echo "── Загрузка ──"; uptime 2>/dev/null',
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        body = (r.stdout or "").strip() or "—"
    except Exception as e:
        body = f"(нет данных: {e})"
    return SearchResult(
        title="Память и загрузка",
        subtitle="free · uptime",
        icon_name="system-monitor",
        score=0.57,
        category="Система",
        preview_kind="text",
        preview_text=body,
        usage_key="idle:resources",
        action=lambda: None,
    )

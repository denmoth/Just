import os
import subprocess

from core.search import SearchResult


class ShellRunner:
    def match(self, query: str) -> list[SearchResult]:
        q = query.strip()
        if not q.startswith(">") and not q.startswith("$"):
            return []
        cmd = q[1:].strip()
        if not cmd:
            return [SearchResult(
                title="Введите команду",
                subtitle="Пример: > ls -la ~/Documents",
                icon_name="utilities-terminal",
                score=0.5,
                category="Терминал",
                preview_kind="text",
                preview_text=(
                    "Введите команду.\n\n"
                    "Справа — интерактивный терминал (PTY): bash -i.\n"
                    "Ctrl+Space — открыть превью; фокус сразу в терминале.\n"
                    "Shift+Esc — закрыть превью (Esc уходит в shell)."
                ),
                action=lambda: None,
            )]
        return [SearchResult(
            title="Выполнить: " + cmd,
            subtitle="Enter — внешний терминал · Ctrl+Space — PTY · Shift+Esc — закрыть превью",
            icon_name="utilities-terminal",
            score=1.0,
            category="Терминал",
            preview_kind="shell",
            preview_text=cmd,
            usage_key="shell:cmd",
            action=lambda c=cmd: self._run_in_term(c),
        )]

    @staticmethod
    def _run_in_term(cmd: str):
        for term_cmd in ("konsole", "alacritty"):
            if os.path.exists(f"/usr/bin/{term_cmd}"):
                try:
                    subprocess.Popen(
                        [term_cmd, "-e", "bash", "-c",
                         cmd + "; echo '\\n[Готово] Нажмите Enter...'; read"],
                        start_new_session=True,
                    )
                    return
                except Exception:
                    pass


RUNNERS = [ShellRunner()]

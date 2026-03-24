"""
Natural-language preprocessing for the launcher.

Strips conversational filler so existing runners (converter, timer, files, …)
match the same query with or without phrases like «сколько будет», «please».
Explicit modes (.prefix, !bang, =, >, ?, !!, $) are left unchanged.
"""

from __future__ import annotations

import re

_LEADING_FILLER = re.compile(
    r"^\s*(?:"
    r"пожалуйста|please|скажи|tell\s+me|сколько\s+будет|how\s+much\s+is|"
    r"переведи|translate|convert|позволь|можно|"
    r"найди|find|открой|open|запусти|launch|run|"
    r"напомни(?:\s+меня)?|remind\s+me"
    r")\s+",
    re.IGNORECASE,
)


def should_skip_nl_normalize(query: str) -> bool:
    q = query.lstrip()
    if not q:
        return True
    if q.startswith("!!"):
        return True
    if q[0] in ".!?>=$":
        return True
    return False


def normalize_for_runners(query: str) -> str:
    """Return text passed to runners; safe no-op for magic-prefixed lines."""
    q = query.strip()
    if not q or should_skip_nl_normalize(q):
        return q
    stripped = _LEADING_FILLER.sub("", q, count=1).strip()
    return stripped if stripped else q

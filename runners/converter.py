"""Currency and physical unit conversion (human phrases)."""

import json
import re
import time
import urllib.request

from core.config import CACHE_DIR, VERSION
from core.search import SearchResult, EN_TO_RU, RU_TO_EN, _clipboard, switch_layout
from runners.unit_convert import try_convert_units

_CACHE_FILE = CACHE_DIR / "fx_rates.json"
_CACHE_TTL = 3600 * 4


def _load_rates() -> dict | None:
    if _CACHE_FILE.exists():
        try:
            age = time.time() - _CACHE_FILE.stat().st_mtime
            if age < _CACHE_TTL:
                with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    for url in (
        "https://api.exchangerate.host/latest?base=USD",
        "https://api.frankfurter.app/v1/latest?from=USD",
    ):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": f"Just/{VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode())
            rates = None
            if data.get("success") and "rates" in data:
                rates = data["rates"]
            elif "rates" in data:
                rates = data["rates"]
            if rates:
                with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(rates, f)
                return rates
        except Exception:
            continue
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


_ALIASES = {
    "usd": "USD", "$": "USD", "долл": "USD", "доллар": "USD",
    "eur": "EUR", "€": "EUR", "евро": "EUR",
    "gbp": "GBP", "£": "GBP", "фунт": "GBP",
    "rub": "RUB", "руб": "RUB", "р": "RUB", "₽": "RUB",
    "uah": "UAH", "грн": "UAH", "₴": "UAH",
    "kzt": "KZT", "тенге": "KZT", "₸": "KZT",
    "byn": "BYN", "бел": "BYN", "br": "BYN",
    "jpy": "JPY", "¥": "JPY", "йена": "JPY",
    "cny": "CNY", "юань": "CNY", "¥c": "CNY",
    "try": "TRY", "лира": "TRY",
    "chf": "CHF", "франк": "CHF",
    "pln": "PLN", "злот": "PLN",
    "czk": "CZK", "крон": "CZK",
}


def _norm_cur(s: str) -> str | None:
    s = s.strip().lower()
    if not s:
        return None
    if s in _ALIASES:
        return _ALIASES[s]
    s2 = s.upper()
    if len(s2) == 3 and s2.isalpha():
        return s2
    return None


class ConverterRunner:
    _RE = re.compile(
        r"^(\d+(?:[.,]\d+)?)\s*([^\s]+)\s*(?:в|to|in|->|→)\s*([^\s]+)$",
        re.I,
    )

    def match(self, query: str) -> list[SearchResult]:
        q0 = query.strip()
        for variant in (q0, switch_layout(q0, EN_TO_RU), switch_layout(q0, RU_TO_EN)):
            u = try_convert_units(variant)
            if u:
                title, preview, copy_v = u
                return [SearchResult(
                    title=title,
                    subtitle="Enter — скопировать результат",
                    icon_name="accessories-calculator",
                    score=0.93,
                    category="Конвертер",
                    preview_kind="text",
                    preview_text=preview,
                    usage_key=f"unit:{title[:40]}",
                    action=lambda v=copy_v: _clipboard(str(v)),
                )]

            m = self._RE.match(variant)
            if not m:
                continue
            amt_s = m.group(1).replace(",", ".")
            try:
                amount = float(amt_s)
            except ValueError:
                return []
            fc = _norm_cur(m.group(2))
            tc = _norm_cur(m.group(3))
            if not fc or not tc:
                return []

            rates = _load_rates()
            if not rates:
                return [SearchResult(
                    title="Курсы: нет сети / кэш пуст",
                    subtitle="exchangerate.host",
                    icon_name="network-error", score=0.5,
                    category="Конвертер", action=lambda: None,
                )]

            rates = {k.upper(): float(v) for k, v in rates.items()}
            rates["USD"] = 1.0

            def to_usd(code: str, val: float) -> float | None:
                if code == "USD":
                    return val
                r = rates.get(code)
                if r is None:
                    return None
                return val / r

            def from_usd(code: str, usd: float) -> float | None:
                if code == "USD":
                    return usd
                r = rates.get(code)
                if r is None:
                    return None
                return usd * r

            usd_amt = to_usd(fc, amount)
            if usd_amt is None:
                return [SearchResult(
                    title=f"Неизвестная валюта: {fc}",
                    subtitle="Попробуйте ISO-код (USD, EUR, RUB)",
                    icon_name="dialog-warning", score=0.4,
                    category="Конвертер", action=lambda: None,
                )]
            out = from_usd(tc, usd_amt)
            if out is None:
                return [SearchResult(
                    title=f"Неизвестная валюта: {tc}",
                    subtitle="",
                    icon_name="dialog-warning", score=0.4,
                    category="Конвертер", action=lambda: None,
                )]

            if abs(out - round(out)) < 1e-6 and abs(out) < 1e14:
                disp = str(int(round(out)))
            else:
                disp = f"{out:.6g}"

            title = f"{amount:g} {fc} → {disp} {tc}"
            preview = (
                f"{amount:g} {fc} = {disp} {tc}\n\n"
                f"Источник: exchangerate.host (USD base)\n"
                f"Кэш: до {_CACHE_TTL // 3600} ч"
            )
            return [SearchResult(
                title=title,
                subtitle="Enter — скопировать число",
                icon_name="accessories-calculator",
                score=0.92,
                category="Конвертер",
                preview_kind="text",
                preview_text=preview,
                usage_key=f"convert:{fc}->{tc}",
                action=lambda v=out: _clipboard(str(v)),
            )]
        return []


RUNNERS = [ConverterRunner()]

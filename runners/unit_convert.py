"""Length / mass / volume / temperature conversion (human phrases, RU/EN)."""

from __future__ import annotations

import re

_LEN: dict[str, tuple[str, float, str]] = {
    "m": ("len", 1.0, "м"),
    "meter": ("len", 1.0, "m"),
    "meters": ("len", 1.0, "m"),
    "metre": ("len", 1.0, "m"),
    "metres": ("len", 1.0, "m"),
    "м": ("len", 1.0, "м"),
    "метр": ("len", 1.0, "м"),
    "метра": ("len", 1.0, "м"),
    "метров": ("len", 1.0, "м"),
    "km": ("len", 1000.0, "км"),
    "kilometer": ("len", 1000.0, "км"),
    "kilometers": ("len", 1000.0, "км"),
    "км": ("len", 1000.0, "км"),
    "километр": ("len", 1000.0, "км"),
    "километра": ("len", 1000.0, "км"),
    "километров": ("len", 1000.0, "км"),
    "cm": ("len", 0.01, "см"),
    "centimeter": ("len", 0.01, "см"),
    "centimeters": ("len", 0.01, "см"),
    "см": ("len", 0.01, "см"),
    "centimetre": ("len", 0.01, "см"),
    "mm": ("len", 0.001, "мм"),
    "millimeter": ("len", 0.001, "мм"),
    "мм": ("len", 0.001, "мм"),
    "millimetre": ("len", 0.001, "мм"),
    "mi": ("len", 1609.344, "мили"),
    "mile": ("len", 1609.344, "мили"),
    "miles": ("len", 1609.344, "мили"),
    "миля": ("len", 1609.344, "мили"),
    "мили": ("len", 1609.344, "мили"),
    "миль": ("len", 1609.344, "мили"),
    "ft": ("len", 0.3048, "фт"),
    "foot": ("len", 0.3048, "фт"),
    "feet": ("len", 0.3048, "фт"),
    "фут": ("len", 0.3048, "фт"),
    "фута": ("len", 0.3048, "фт"),
    "футов": ("len", 0.3048, "фт"),
    "in": ("len", 0.0254, "дюйм"),
    "inch": ("len", 0.0254, "дюйм"),
    "inches": ("len", 0.0254, "дюйм"),
    "дюйм": ("len", 0.0254, "дюйм"),
    "дюйма": ("len", 0.0254, "дюйм"),
    "дюймов": ("len", 0.0254, "дюйм"),
    "yd": ("len", 0.9144, "ярд"),
    "yard": ("len", 0.9144, "ярд"),
    "yards": ("len", 0.9144, "ярд"),
    "ярд": ("len", 0.9144, "ярд"),
    "ярда": ("len", 0.9144, "ярд"),
    "nmi": ("len", 1852.0, "м.мили"),
    "nm": ("len", 1852.0, "м.мили"),
}

_MASS: dict[str, tuple[str, float, str]] = {
    "kg": ("mass", 1.0, "кг"),
    "kilogram": ("mass", 1.0, "кг"),
    "kilograms": ("mass", 1.0, "кг"),
    "кг": ("mass", 1.0, "кг"),
    "g": ("mass", 0.001, "г"),
    "gram": ("mass", 0.001, "г"),
    "grams": ("mass", 0.001, "г"),
    "г": ("mass", 0.001, "г"),
    "грамм": ("mass", 0.001, "г"),
    "грамма": ("mass", 0.001, "г"),
    "граммов": ("mass", 0.001, "г"),
    "lb": ("mass", 0.45359237, "lb"),
    "lbs": ("mass", 0.45359237, "lb"),
    "pound": ("mass", 0.45359237, "lb"),
    "pounds": ("mass", 0.45359237, "lb"),
    "фунт": ("mass", 0.45359237, "lb"),
    "фунта": ("mass", 0.45359237, "lb"),
    "фунтов": ("mass", 0.45359237, "lb"),
    "oz": ("mass", 0.028349523125, "oz"),
    "ounce": ("mass", 0.028349523125, "oz"),
    "ounces": ("mass", 0.028349523125, "oz"),
    "унция": ("mass", 0.028349523125, "oz"),
    "тонна": ("mass", 1000.0, "т"),
    "t": ("mass", 1000.0, "т"),
    "tonne": ("mass", 1000.0, "т"),
}

_VOL: dict[str, tuple[str, float, str]] = {
    "l": ("vol", 1.0, "л"),
    "liter": ("vol", 1.0, "л"),
    "litre": ("vol", 1.0, "л"),
    "liters": ("vol", 1.0, "л"),
    "litres": ("vol", 1.0, "л"),
    "л": ("vol", 1.0, "л"),
    "литр": ("vol", 1.0, "л"),
    "литра": ("vol", 1.0, "л"),
    "литров": ("vol", 1.0, "л"),
    "ml": ("vol", 0.001, "мл"),
    "milliliter": ("vol", 0.001, "мл"),
    "millilitre": ("vol", 0.001, "мл"),
    "мл": ("vol", 0.001, "мл"),
    "gal": ("vol", 3.785411784, "гал US"),
    "gallon": ("vol", 3.785411784, "гал US"),
    "cup": ("vol", 0.2365882365, "стакан US"),
    "стакан": ("vol", 0.2365882365, "стакан US"),
}

_ALIASES: dict[str, tuple[str, float, str]] = {}
for d in (_LEN, _MASS, _VOL):
    _ALIASES.update(d)


def _norm_token(s: str) -> str:
    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"°\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _lookup_unit(token: str) -> tuple[str, float, str] | None:
    t = _norm_token(token)
    if not t:
        return None
    if t in _ALIASES:
        return _ALIASES[t]
    return None


def _temp_scale_from_suffix(s: str) -> str | None:
    t = _norm_token(s).replace(" ", "")
    if not t:
        return None
    if "цельс" in t or t in ("c", "celsius"):
        return "C"
    if "фарен" in t or t in ("f", "fahrenheit"):
        return "F"
    if "кельвин" in t or t in ("k", "kelvin"):
        return "K"
    return None


def _temp_to_c(scale: str, v: float) -> float:
    if scale == "C":
        return v
    if scale == "F":
        return (v - 32.0) * 5.0 / 9.0
    if scale == "K":
        return v - 273.15
    return v


def _c_to_scale(scale: str, c: float) -> float:
    if scale == "C":
        return c
    if scale == "F":
        return c * 9.0 / 5.0 + 32.0
    if scale == "K":
        return c + 273.15
    return c


def _split_conversion(q: str) -> tuple[str, str] | None:
    s = q.strip()
    s = re.sub(
        r"^(?:сколько\s+(?:это\s+)?(?:будет|выходит|получится)\s*|"
        r"переведи\s+|convert\s+)",
        "",
        s,
        flags=re.I,
    ).strip()
    for sep in (r"\s+в\s+", r"\s+во\s+", r"\s+to\s+", r"\s*->\s*", r"\s*→\s*", r"\s+into\s+"):
        m = re.search(sep, s, re.I)
        if m:
            left, right = s[: m.start()].strip(), s[m.end() :].strip()
            if left and right:
                return left, right
    return None


def _parse_amount_left(left: str) -> tuple[float, str] | None:
    left = left.strip()
    m = re.match(r"^(-?\d+(?:[.,]\d+)?)\s+(.+)$", left, re.S)
    if not m:
        m2 = re.match(r"^(-?\d+(?:[.,]\d+)?)([a-zа-яё°]+)$", left, re.I)
        if m2:
            return float(m2.group(1).replace(",", ".")), m2.group(2)
        return None
    return float(m.group(1).replace(",", ".")), m.group(2).strip()


def try_convert_units(q: str) -> tuple[str, str, str] | None:
    """Return (title, preview_text, clipboard_value) or None."""
    sp = _split_conversion(q.strip())
    if not sp:
        return None
    left_s, right_s = sp
    parsed = _parse_amount_left(left_s)
    if not parsed:
        return None
    amount, u_left_raw = parsed
    u_right_raw = right_s.strip()

    scale_r = _temp_scale_from_suffix(u_right_raw)
    scale_l = _temp_scale_from_suffix(u_left_raw)
    if scale_l and scale_r:
        c = _temp_to_c(scale_l, amount)
        out = _c_to_scale(scale_r, c)
        label_r = {"C": "°C", "F": "°F", "K": "K"}[scale_r]
        if abs(out - round(out)) < 1e-4 and abs(out) < 1e9:
            disp = str(int(round(out)))
        else:
            disp = f"{out:.4g}"
        title = f"{amount:g}°{scale_l} → {disp} {label_r}"
        preview = f"{title}\n\nТемпература (через °C)."
        return title, preview, disp

    lu = _lookup_unit(u_left_raw)
    ru = _lookup_unit(u_right_raw)
    if not lu or not ru:
        return None
    fam_l, mul_l, lab_l = lu
    fam_r, mul_r, lab_r = ru
    if fam_l != fam_r:
        return None

    si = amount * mul_l
    out = si / mul_r
    if abs(out - round(out)) < 1e-6 and abs(out) < 1e12:
        disp = str(int(round(out)))
    else:
        disp = f"{out:.6g}"

    title = f"{amount:g} {lab_l} → {disp} {lab_r}"
    preview = f"{amount:g} {lab_l} = {disp} {lab_r}"
    return title, preview, disp

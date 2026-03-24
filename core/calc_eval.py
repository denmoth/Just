"""Shared safe evaluation for CalcRunner and scientific preview."""

import math
import re
from fractions import Fraction

_SAFE = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sqrt": math.sqrt, "log": math.log, "log2": math.log2,
    "log10": math.log10, "exp": math.exp, "pow": math.pow,
    "pi": math.pi, "e": math.e, "int": int, "float": float,
    "Fraction": Fraction,
}


def normalize_expression(q: str) -> str:
    expr = q.strip().replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", ".")
    return expr


def calc_eval(expr: str) -> tuple[str | None, str | None]:
    """
    Returns (display_string, error_message).
    display_string is None on failure.
    """
    if not expr or not re.search(r"\d", expr):
        return None, None
    if not re.match(r"^[\d\s+\-*/().%eE,\w]+$", expr):
        return None, "Недопустимые символы"
    try:
        result = eval(expr, {"__builtins__": {}}, _SAFE)
        if isinstance(result, bool):
            return None, None
        if isinstance(result, Fraction):
            if result.denominator == 1:
                disp = str(result.numerator)
            else:
                disp = f"{result.numerator}/{result.denominator}"
            return disp, None
        result = float(result)
        if math.isinf(result) or math.isnan(result):
            return None, "∞ / NaN"
        if result == int(result) and abs(result) < 1e15:
            disp = str(int(result))
        else:
            disp = format(result, ".12g")
        return disp, None
    except ZeroDivisionError:
        return None, "Деление на ноль"
    except Exception as e:
        return None, str(e)[:80]


def calc_match_query(query: str) -> tuple[str | None, str | None]:
    """If query looks like a calculation, return (normalized_expr, None)."""
    q = query.strip()
    if not q:
        return None, None
    if q.startswith("="):
        q = q[1:].strip()
    expr = normalize_expression(q)
    if not re.search(r"\d", expr):
        return None, None
    if not re.match(r"^[\d\s+\-*/().%eE,\w]+$", expr):
        return None, None
    return expr, None

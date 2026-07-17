"""Computable questions: answered by code, never by retrieval.

Measured product failure (2026-07-16, Jeffrey's screenshot): «¿qué día es
hoy?» went through retrieval and came back with Wikiquote's tautology
("hoy es el día posterior a ayer"). The architecture principle already
says it — anything solvable with code spends neither parameters nor
searches. This layer intercepts questions whose answer lives in the
system clock or in arithmetic, before any source is queried.

Arithmetic is evaluated over a WHITELISTED ast (numbers and + - * / % **
parentheses only) — never eval() on user text.
"""

from __future__ import annotations

import ast
import operator
import re
from datetime import datetime

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_P_FECHA = re.compile(
    r"\b(qu[eé] (d[ií]a|fecha) es hoy|what (day|date) is (it|today)|fecha de hoy"
    r"|a qu[eé] (d[ií]a|fecha) estamos)\b", re.IGNORECASE)
_P_HORA = re.compile(
    r"\b(qu[eé] hora es|what time is it|hora actual)\b", re.IGNORECASE)
_P_ARITMETICA = re.compile(
    r"\b(?:cu[aá]nto (?:es|da|vale)|calcula|how much is|what is)\s+([0-9][0-9\s\.\,\+\-\*/%\(\)]*)",
    re.IGNORECASE)
_P_PORCENTAJE = re.compile(
    r"(?:cu[aá]nto es\s+)?(\d+(?:[\.,]\d+)?)\s*%\s*de\s*(\d+(?:[\.,]\d+)?)",
    re.IGNORECASE)

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _evaluar_seguro(expresion: str) -> float | None:
    """Whitelisted-ast arithmetic; None on anything outside the whitelist."""
    try:
        arbol = ast.parse(expresion, mode="eval")
    except SyntaxError:
        return None

    def _v(nodo):
        if isinstance(nodo, ast.Expression):
            return _v(nodo.body)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)):
            return nodo.value
        if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPS:
            return _OPS[type(nodo.op)](_v(nodo.left), _v(nodo.right))
        if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPS:
            return _OPS[type(nodo.op)](_v(nodo.operand))
        raise ValueError("fuera de la lista blanca")

    try:
        return float(_v(arbol))
    except Exception:
        return None


def _numero(texto: str) -> str:
    v = float(texto)
    return f"{v:g}"


def responder_computable(pregunta: str) -> str | None:
    """Deterministic answer for clock/arithmetic questions; None otherwise."""
    ahora = datetime.now()
    if _P_FECHA.search(pregunta):
        return (f"Hoy es {_DIAS[ahora.weekday()]} {ahora.day} de "
                f"{_MESES[ahora.month - 1]} de {ahora.year}. "
                "(Reloj del sistema — cálculo local, sin búsqueda.)")
    if _P_HORA.search(pregunta):
        return (f"Son las {ahora.strftime('%H:%M')} (hora local de esta máquina). "
                "(Reloj del sistema — cálculo local, sin búsqueda.)")
    m = _P_PORCENTAJE.search(pregunta)
    if m:
        pct = float(m.group(1).replace(",", "."))
        base = float(m.group(2).replace(",", "."))
        return (f"El {_numero(m.group(1).replace(',', '.'))}% de "
                f"{_numero(m.group(2).replace(',', '.'))} es {pct * base / 100:g}. "
                "(Aritmética local, verificable.)")
    m = _P_ARITMETICA.search(pregunta)
    if m:
        expresion = m.group(1).replace(",", ".").replace(" ", "").rstrip(".")
        if re.search(r"[\+\-\*/%]", expresion):
            resultado = _evaluar_seguro(expresion)
            if resultado is not None:
                return (f"{expresion} = {resultado:g}. "
                        "(Aritmética local, verificable.)")
    return None

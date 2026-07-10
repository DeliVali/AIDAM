"""Symbolic comparators (Phase 3, first brick): arithmetic wearing a
language costume gets judged by rules, not weights.

The traced case (#207, v8-500): "At independence, Nigeria had a population
of 45 million" was refuted at confidence 1.00 by evidence stating TODAY's
population — a quantity unbound from its time qualifier. Teaching this
distinction by training (v9) verified at the pair level but measured worse
at claim level, because softening numeric contradiction also loses genuine
refutations. A symbolic rule can be surgical where training can't: it fires
ONLY when both sides carry explicit, extractable time markers of different
periods AND genuinely different quantities — deterministic, auditable,
zero parameters, ~zero latency.

Scope (deliberately narrow, the v9 lesson):
- only REFUTA pairs are ever touched (SUSTENTA/NEUTRAL never change);
- the claim must carry a quantity AND a temporal marker;
- the evidence must carry a DIFFERENT-period temporal marker and a
  quantity differing >20% — then the pair downgrades to NO_CONCLUYE
  ("different period" is not "contradiction");
- anything unextractable is left to the NLI verdict untouched.
"""

from __future__ import annotations

import re

from .models import EtiquetaPar, VeredictoPar

# Quantities: "45 million", "2.4 billion", "13%", "45,000", plain integers ≥ 3 digits.
_CANTIDAD = re.compile(
    r"\b(\d[\d,.]*)\s*(million|billion|thousand|millones|mil millones|%|percent)?\b",
    re.IGNORECASE,
)
_ESCALAS = {
    "million": 1e6, "millones": 1e6, "billion": 1e9, "mil millones": 1e9,
    "thousand": 1e3, "%": 1.0, "percent": 1.0,
}

_ANIO = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
# Past-relative markers: a period pinned to a historical event, not to now.
_PASADO_RELATIVO = re.compile(
    r"\b(at independence|at its founding|at the last census|when it was founded"
    r"|en la independencia|en su fundaci[oó]n)\b",
    re.IGNORECASE,
)
# Present markers: the quantity is asserted about now.
_PRESENTE = re.compile(
    r"\b(currently|today|at present|as of now|is now|actualmente|hoy en d[ií]a)\b",
    re.IGNORECASE,
)


def _cantidades(texto: str) -> list[float]:
    valores = []
    for numero, escala in _CANTIDAD.findall(texto):
        try:
            base = float(numero.replace(",", ""))
        except ValueError:
            continue
        escala_norm = (escala or "").lower()
        if escala_norm in _ESCALAS:
            valores.append(base * _ESCALAS[escala_norm])
        elif base >= 100:  # bare small integers ("4 senators") are too noisy
            valores.append(base)
    return valores


def _periodo(texto: str) -> str | None:
    """One of: a specific year, "pasado-relativo", "presente", or None."""
    if anio := _ANIO.search(texto):
        return anio.group(1)
    if _PASADO_RELATIVO.search(texto):
        return "pasado-relativo"
    if _PRESENTE.search(texto):
        return "presente"
    return None


def _periodos_distintos(p1: str, p2: str) -> bool:
    """Different explicit periods. A relative past marker vs. a year is NOT
    provably different (independence might BE that year) — only year≠year,
    past-relative vs present, or year vs present count."""
    if p1 == p2:
        return False
    ambos = {p1, p2}
    if ambos == {"pasado-relativo", "presente"}:
        return True
    anios = [p for p in ambos if p.isdigit()]
    if len(anios) == 2:
        return True
    if len(anios) == 1 and "presente" in ambos:
        # A dated figure vs. a "currently" figure: different periods when the
        # year is clearly not current.
        return int(anios[0]) < 2020
    return False  # year vs past-relative: can't prove different


def _cantidades_distintas(a: list[float], b: list[float]) -> bool:
    """No quantity on one side is within 20% of any on the other."""
    if not a or not b:
        return False
    for x in a:
        for y in b:
            if max(x, y) > 0 and abs(x - y) / max(x, y) <= 0.20:
                return False
    return True


def ajustar_pares(pares: list[VeredictoPar]) -> list[VeredictoPar]:
    """Downgrades REFUTA pairs whose contradiction is a different-period
    quantity mismatch. Returns the same list, mutated (pairs are dataclasses
    shared with the caller)."""
    for par in pares:
        if par.etiqueta is not EtiquetaPar.REFUTA:
            continue
        claim = par.hecho.texto
        evidencia = par.evidencia.texto
        periodo_claim = _periodo(claim)
        periodo_evidencia = _periodo(evidencia)
        if not periodo_claim or not periodo_evidencia:
            continue
        if not _periodos_distintos(periodo_claim, periodo_evidencia):
            continue
        if _cantidades_distintas(_cantidades(claim), _cantidades(evidencia)):
            par.etiqueta = EtiquetaPar.NO_CONCLUYE
    return pares

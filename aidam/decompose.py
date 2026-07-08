"""Decomposer (Module 1): claim → verifiable atomic facts.

Heuristic MVP: splits by sentences and discards questions and opinion markers.
The interface is a pure function so it can be replaced by a neural
decomposer (Phase 1) without touching the rest of the pipeline.
"""

from __future__ import annotations

import re

from .models import HechoAtomico

_SEPARADOR_FRASES = re.compile(r"(?<=[.!?;])\s+")
_OPINION = re.compile(
    r"\b(creo|opino|pienso|me parece|deber[íi]a[ns]?|ojal[áa]|quiz[áa]s?|tal vez"
    r"|i think|i believe|should|maybe|perhaps)\b",
    re.IGNORECASE,
)
_MIN_CARACTERES = 8


def _es_verificable(frase: str) -> bool:
    if len(frase) < _MIN_CARACTERES:
        return False
    if frase.startswith("¿") or frase.endswith("?"):
        return False
    if _OPINION.search(frase):
        return False
    return True


def descomponer(afirmacion: str) -> list[HechoAtomico]:
    """Splits a claim into verifiable atomic facts.

    If no sentence passes the filter, returns the whole claim as the
    single fact: better to verify something imperfect than nothing.
    """
    afirmacion = afirmacion.strip()
    frases = _SEPARADOR_FRASES.split(afirmacion)
    hechos = [
        HechoAtomico(texto=f.strip().rstrip("."), origen=afirmacion)
        for f in (frase.strip() for frase in frases)
        if _es_verificable(f)
    ]
    return hechos or [HechoAtomico(texto=afirmacion, origen=afirmacion)]

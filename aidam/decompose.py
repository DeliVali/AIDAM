"""Descompositor (Módulo 1): afirmación → hechos atómicos verificables.

MVP heurístico: separa por frases y descarta preguntas y marcadores de opinión.
La interfaz es una función pura para poder sustituirla por un descompositor
neuronal (Fase 1) sin tocar el resto del pipeline.
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
    """Divide una afirmación en hechos atómicos verificables.

    Si ninguna frase pasa el filtro, devuelve la afirmación completa como
    único hecho: mejor verificar algo imperfecto que nada.
    """
    afirmacion = afirmacion.strip()
    frases = _SEPARADOR_FRASES.split(afirmacion)
    hechos = [
        HechoAtomico(texto=f.strip().rstrip("."), origen=afirmacion)
        for f in (frase.strip() for frase in frases)
        if _es_verificable(f)
    ]
    return hechos or [HechoAtomico(texto=afirmacion, origen=afirmacion)]

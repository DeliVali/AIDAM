"""Investigation angles: the diversity that decorrelates verification errors.

Condorcet's jury theorem only pays when member errors are independent — N
identical passes of a deterministic verifier over the same evidence have
correlation 1.0 and gain exactly zero. Each angle must therefore vary
something real: the query (reformulation), the polarity (negation — explicit
negation retrieves refuting evidence that affirmative search misses,
arXiv:2602.18693), or the evidence pool. The angle count is capped low on
purpose: the self-consistency literature shows the benefit plateaus at 5-10
samples and can degrade beyond (arXiv:2203.11171, arXiv:2511.00751).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import EtiquetaPar, VeredictoPar


@dataclass
class Angulo:
    nombre: str            # "negacion" | "reformulacion"
    consulta: str          # text to search for
    invertido: bool = False  # True → NLI judgements must be flipped (negation angle)


_MAX_ANGULOS = {1: 3, 2: 6}

# Insertion targets: common copulas/auxiliaries in Spanish and English.
_VERBOS_ES = r"es|era|fue|son|eran|fueron|está|estaba|están|estaban|tiene|tenía|tienen|hay|existe|existen"
_VERBOS_EN = r"is|was|are|were|has|have|had|does|do|did|can|will"

_QUITAR_NO_ES = re.compile(rf"\bno\s+({_VERBOS_ES})\b", re.IGNORECASE)
_PONER_NO_ES = re.compile(rf"\b({_VERBOS_ES})\b", re.IGNORECASE)
_QUITAR_NOT_EN = re.compile(rf"\b({_VERBOS_EN})\s+not\b", re.IGNORECASE)
_PONER_NOT_EN = re.compile(rf"\b({_VERBOS_EN})\b", re.IGNORECASE)


def negar_afirmacion(texto: str) -> str | None:
    """Heuristic negation without an LLM; None when no rule applies safely.

    Removal is tried before insertion so an already-negated claim flips back
    to its affirmative form instead of double-negating.
    """
    for patron, reemplazo in (
        (_QUITAR_NO_ES, r"\1"),
        (_QUITAR_NOT_EN, r"\1"),
        (_PONER_NO_ES, r"no \1"),
        (_PONER_NOT_EN, r"\1 not"),
    ):
        nuevo, cuantos = patron.subn(reemplazo, texto, count=1)
        if cuantos:
            return nuevo
    return None


def invertir_pares(pares: list[VeredictoPar], hecho=None) -> list[VeredictoPar]:
    """Maps judgements against the negated claim back to the original claim.

    Evidence SUPPORTING the negation REFUTES the original and vice versa;
    inconclusive stays inconclusive. `hecho` reattaches the ORIGINAL fact so
    downstream aggregation and citations always speak about the user's claim,
    never the synthetic negation. Returns new pairs — never mutates input.
    """
    volteo = {
        EtiquetaPar.SUSTENTA: EtiquetaPar.REFUTA,
        EtiquetaPar.REFUTA: EtiquetaPar.SUSTENTA,
        EtiquetaPar.NO_CONCLUYE: EtiquetaPar.NO_CONCLUYE,
    }
    return [
        VeredictoPar(hecho or par.hecho, par.evidencia, volteo[par.etiqueta], par.prob)
        for par in pares
    ]


def generar_angulos(
    hecho_texto: str, nivel: int, generador=None, lang: str = "es"
) -> list[Angulo]:
    """Angles for one fact at one escalation level; deduplicated, capped."""
    if nivel <= 0:
        return []
    angulos: list[Angulo] = []
    negacion = negar_afirmacion(hecho_texto)
    if negacion:
        angulos.append(Angulo("negacion", negacion, invertido=True))
    if generador is not None:
        try:
            reformulaciones = generador.preguntas(hecho_texto, n=2 if nivel == 1 else 4, lang=lang)
        except Exception:
            reformulaciones = []
        for consulta in reformulaciones:
            angulos.append(Angulo("reformulacion", consulta))

    vistos = {hecho_texto.casefold().strip()}
    unicos: list[Angulo] = []
    for angulo in angulos:
        clave = angulo.consulta.casefold().strip()
        if clave and clave not in vistos:
            vistos.add(clave)
            unicos.append(angulo)
    return unicos[: _MAX_ANGULOS.get(nivel, _MAX_ANGULOS[2])]

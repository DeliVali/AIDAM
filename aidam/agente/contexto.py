"""Conversational context: follow-up questions become self-contained.

Measured product failure (2026-07-16, Jeffrey's screenshot): after asking
about LoRa, the follow-up «¿y en el contexto de machine learning y
modelos?» was treated as a brand-new question and answered with generic
ML fluff. Standard conversational-RAG fix, in its LIGHTEST form: detect
the follow-up, rewrite it self-contained by carrying over the previous
turn's topic terms — pure string work, zero models, microseconds. The
optional narrator LLM may produce a finer rewrite when loaded; the
heuristic is the always-available floor (the same two-layer contract as
respuesta_concisa).

The rewritten question is always SHOWN to the user («pregunta
interpretada: …») — context resolution must be transparent, never a
silent guess.
"""

from __future__ import annotations

import re
import unicodedata

# Connector openings that mark a follow-up rather than a fresh question.
_CONECTORES = re.compile(
    r"^\s*¿?\s*(y|pero|entonces|adem[aá]s|o sea|and|but|so|also)\b"
    r"|^\s*¿?\s*(en|dentro de) (el|ese|este|dicho) (contexto|caso|sentido)\b"
    r"|^\s*¿?\s*(qu[eé] tal|y si)\b",
    re.IGNORECASE,
)
# Deictics that need an antecedent from the previous turn.
_DEICTICOS = re.compile(
    r"\b(eso|esto|aquello|ese|esa|este|esta|[eé]l|ella|ellos|ellas|ah[ií]"
    r"|that|this|it|there)\b",
    re.IGNORECASE,
)
_VACIAS = {
    "para", "como", "cómo", "donde", "dónde", "cuando", "cuándo", "cual",
    "cuál", "quien", "quién", "sobre", "entre", "hasta", "desde", "porque",
    "aunque", "según", "segun", "sirve", "funciona", "significa", "contexto",
    "what", "where", "when", "which", "about", "does", "mean", "work",
}


def _terminos_clave(texto: str, maximo: int = 4) -> list[str]:
    """Content words that name the previous turn's topic."""
    palabras = re.findall(r"[\wáéíóúñÁÉÍÓÚÑ]{4,}", texto)
    claves, vistas = [], set()
    for p in palabras:
        plano = unicodedata.normalize("NFKD", p.casefold())
        plano = "".join(c for c in plano if not unicodedata.combining(c))
        if plano in _VACIAS or plano in vistas:
            continue
        vistas.add(plano)
        claves.append(p)
        if len(claves) == maximo:
            break
    return claves


def es_seguimiento(texto: str) -> bool:
    limpio = texto.strip()
    if _CONECTORES.match(limpio):
        return True
    return len(limpio) < 60 and bool(_DEICTICOS.search(limpio))


def resolver_seguimiento(entrada: str, pregunta_previa: str | None) -> str:
    """Returns the self-contained question (or the input untouched).

    Heuristic carry-over: the previous turn's topic terms that the
    follow-up doesn't already mention are prepended, and the leading
    connector is dropped: («que es lora?», «y en el contexto de machine
    learning?») → «lora — en el contexto de machine learning?».
    """
    if not pregunta_previa or not es_seguimiento(entrada):
        return entrada
    tema = [
        t for t in _terminos_clave(pregunta_previa)
        if t.casefold() not in entrada.casefold()
    ]
    if not tema:
        return entrada
    cuerpo = _CONECTORES.sub("", entrada.strip(), count=1).strip(" ,;")
    cuerpo = cuerpo or entrada.strip()
    resuelta = f"{' '.join(tema)} — {cuerpo}"
    return resuelta if resuelta.endswith("?") or not entrada.strip().endswith("?") else resuelta + "?"

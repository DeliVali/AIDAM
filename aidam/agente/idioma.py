"""Deterministic input-language detection (the six UI languages).

Complements the six-language phrase table in sintesis.py: the websocket
client sends the UI's `lang`, but the OpenAI-compatible endpoint (and any
caller that omits `lang`) has nothing to send — there the typed message
itself is the only signal. Function-word profiles, zero models, zero
deps, microseconds. Rarity-weighted scoring: a word shared by three
languages counts a third of a word unique to one, so the heavy Romance
overlap (de/la/que…) does not drown the signal. Unclear input falls back
to the caller's default: wrong-but-asked-for beats guessed-and-wrong.
"""

from __future__ import annotations

# High-frequency function words per language. Overlapping entries are
# fine — scoring divides each word's weight by how many languages claim it.
_PERFILES: dict[str, set[str]] = {
    "es": {
        "el", "la", "los", "las", "es", "de", "que", "y", "en", "un",
        "una", "no", "se", "del", "con", "para", "por", "como", "más",
        "pero", "su", "al", "lo", "está", "son", "qué", "cuál", "dónde",
    },
    "en": {
        "the", "is", "are", "was", "were", "of", "and", "to", "in",
        "that", "it", "with", "for", "on", "this", "not", "have", "has",
        "from", "by", "an", "what", "which", "where", "who", "does",
    },
    "de": {
        "der", "die", "das", "ist", "sind", "und", "nicht", "ein",
        "eine", "mit", "von", "zu", "auf", "für", "im", "den", "dem",
        "des", "steht", "sich", "auch", "wird", "bei", "aus", "nach",
        "was", "wo", "wer", "wie",
    },
    "fr": {
        "le", "la", "les", "est", "sont", "et", "de", "des", "du", "un",
        "une", "dans", "pour", "pas", "que", "qui", "avec", "sur", "au",
        "aux", "ce", "cette", "il", "elle", "ne", "en", "où", "quoi",
    },
    "pt": {
        "o", "a", "os", "as", "é", "são", "de", "do", "da", "dos",
        "das", "e", "em", "um", "uma", "não", "que", "com", "para",
        "por", "no", "na", "se", "mais", "está", "qual", "onde",
    },
    "it": {
        "il", "lo", "la", "i", "gli", "le", "è", "sono", "di", "che",
        "e", "in", "un", "una", "non", "con", "per", "del", "della",
        "si", "più", "anche", "questo", "questa", "cosa", "dove",
    },
}

_IDIOMAS = tuple(_PERFILES)


def detectar_idioma(texto: str, por_defecto: str = "es") -> str:
    """Language of the input among the six the UI ships, else the default.

    Requires at least two matched words and a strict winner — short or
    ambiguous input keeps the caller's language rather than guessing.
    """
    palabras = [p.strip("¿?¡!.,;:«»\"'()") for p in texto.casefold().split()]
    palabras = [p for p in palabras if p]
    if len(palabras) < 2:
        return por_defecto
    puntajes = dict.fromkeys(_IDIOMAS, 0.0)
    aciertos = dict.fromkeys(_IDIOMAS, 0)
    for palabra in palabras:
        duenos = [i for i in _IDIOMAS if palabra in _PERFILES[i]]
        for i in duenos:
            puntajes[i] += 1.0 / len(duenos)
            aciertos[i] += 1
    orden = sorted(_IDIOMAS, key=puntajes.get, reverse=True)
    mejor, segundo = orden[0], orden[1]
    if aciertos[mejor] < 2 or puntajes[mejor] <= puntajes[segundo]:
        return por_defecto
    return mejor

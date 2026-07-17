"""Input spelling cleanup: conservative, transparent, questions only.

Jeffrey's ask (2026-07-16): improve the user's spelling so intent is
clearer, across as many languages as possible. The measured danger came
out in the first probe: a naive dictionary corrector turns «Pogba» into
«bomba» and «xina» into «mina» — verdict-corrupting rewrites. So the
guards ARE the design:

- QUESTIONS only, never claims (a claim's exact wording is what gets
  verified; the eval seams never come through here anyway).
- Capitalized words are untouchable (proper nouns).
- Only two correction kinds survive: diacritic restoration («ortografia»
  → «ortografía» — same word, zero risk) and edit-distance-1 fixes on
  lowercase words longer than 4 chars.
- Every applied correction is SHOWN to the user, never silent.

Dictionary languages via pyspellchecker (pure Python): es, en, fr, pt,
de, it, ru, ar, nl, lv, eu. Anything else passes through unchanged; the
narrator LLM (natively multilingual) can widen coverage when loaded.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache


# Curated accent map for Spanish: only UNAMBIGUOUS words (no como/cómo,
# esta/está — those need grammar). Auditable here on purpose: the
# pyspellchecker es dictionary is mojibake-corrupted («según» missing,
# «segün» present — measured), so diacritics come from this list alone.
_ACENTOS_ES = {
    "segun": "según", "tambien": "también", "poblacion": "población",
    "informacion": "información", "educacion": "educación",
    "atencion": "atención", "cancion": "canción", "razon": "razón",
    "corazon": "corazón", "codigo": "código", "numero": "número",
    "publico": "público", "unico": "único", "ultimo": "último",
    "proximo": "próximo", "rapido": "rápido", "facil": "fácil",
    "dificil": "difícil", "util": "útil", "movil": "móvil",
    "arbol": "árbol", "musica": "música", "matematicas": "matemáticas",
    "fisica": "física", "quimica": "química", "medico": "médico",
    "periodico": "periódico", "telefono": "teléfono", "camara": "cámara",
    "pagina": "página", "maquina": "máquina", "america": "américa",
    "africa": "áfrica", "oceano": "océano", "kilometro": "kilómetro",
    "espiritu": "espíritu", "fotosintesis": "fotosíntesis",
    "energia": "energía", "economia": "economía", "tecnologia": "tecnología",
    "biologia": "biología", "todavia": "todavía", "dia": "día",
    "dias": "días", "pais": "país", "paises": "países", "raiz": "raíz",
    "despues": "después", "adios": "adiós", "quiza": "quizá",
    "quizas": "quizás", "jamas": "jamás", "ademas": "además",
    "detras": "detrás", "traves": "través", "interes": "interés",
    "ingles": "inglés", "frances": "francés", "japones": "japonés",
    "aleman": "alemán", "champinon": "champiñón", "espanol": "español",
    "anos": "años", "nino": "niño", "ninos": "niños", "manana": "mañana",
    "pequeno": "pequeño", "senal": "señal", "sueno": "sueño",
}

_IDIOMAS = {"es", "en", "fr", "pt", "de", "it", "ru", "ar", "nl", "lv", "eu"}


def _plano(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in plano if not unicodedata.combining(c))


@lru_cache(maxsize=4)
def _corrector(lang: str):
    try:
        from spellchecker import SpellChecker

        return SpellChecker(language=lang)
    except Exception:
        return None


def _distancia1(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    corta, larga = sorted((a, b), key=len)
    for i in range(len(larga)):
        if corta == larga[:i] + larga[i + 1:]:
            return True
    return False


def corregir_pregunta(texto: str, lang: str = "es") -> tuple[str, list[str]]:
    """Returns (corrected text, list of applied «antes→después») — both
    empty-change when the language has no dictionary or nothing qualifies."""
    if lang not in _IDIOMAS:
        return texto, []
    corrector = _corrector(lang)
    if corrector is None:
        return texto, []

    cambios: list[str] = []

    def _reemplazo(m: re.Match) -> str:
        palabra = m.group(0)
        if lang == "es" and palabra.lower() in _ACENTOS_ES and palabra.islower():
            acentuada = _ACENTOS_ES[palabra]
            cambios.append(f"{palabra}→{acentuada}")
            return acentuada
        if not palabra.islower() or len(palabra) <= 4:
            return palabra  # proper nouns, acronyms, short words: untouchable
        if not corrector.unknown([palabra]):
            return palabra
        sugerida = corrector.correction(palabra)
        if not sugerida or sugerida == palabra:
            return palabra
        if _plano(sugerida) == _plano(palabra):
            return palabra  # diacritics come ONLY from the curated map
        # anti-mojibake: a suggestion must not introduce rare marks the
        # user never typed (the broken dictionary loves «ü»)
        if "ü" in sugerida and "ü" not in palabra:
            return palabra
        if _distancia1(palabra, sugerida):
            cambios.append(f"{palabra}→{sugerida}")
            return sugerida
        return palabra

    corregido = re.sub(r"[\wáéíóúüñàèìòùâêîôûäëïöçãõ]+", _reemplazo, texto)
    return corregido, cambios

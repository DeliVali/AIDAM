"""Router de categorías: decide en qué familias de fuentes buscar cada hecho.

El agente no va a Wikipedia por un error de programación ni a Stack Overflow
por una afirmación médica. Este módulo clasifica el tema del hecho y el
recuperador consulta solo las fuentes relevantes (las universales siempre).

Dos niveles:
1. Palabras clave — determinista, instantáneo, testeable sin modelo.
2. Zero-shot con el propio verificador NLI — si las palabras clave no deciden,
   el modelo compara el hecho contra descripciones de cada categoría. La misma
   habilidad (¿la premisa sustenta la hipótesis?) que usa para verificar.
"""

from __future__ import annotations

import re

CATEGORIAS = ["programacion", "matematicas", "medicina", "ciencia", "actualidad", "general"]

_PATRONES: dict[str, re.Pattern] = {
    "programacion": re.compile(
        r"\b(c[oó]digo|software|program|bug|compil|python|javascript|api|framework"
        r"|servidor|kernel|linux|windows|sql|git|funci[oó]n|variable|libre?r[ií]a"
        r"|aws|azure|gcp|kubernetes|k8s|docker|terraform|kubectl|bash|shell"
        r"|comando|command.line|deploy|devops|s3|ec2)\b",
        re.IGNORECASE,
    ),
    "matematicas": re.compile(
        r"\b(integral|derivad\w*|ecuaci[oó]n|equation|teorema|theorem|matriz|matrix"
        r"|primo?s? (number|n[uú]mero)|n[uú]mero primo|polinomio|polynomial|algebra"
        r"|c[aá]lculo|calculus|geometr[ií]a|probabilidad|probability|factorial"
        r"|logaritmo|logarithm)\b",
        re.IGNORECASE,
    ),
    "medicina": re.compile(
        r"\b(vacuna|virus|c[aá]ncer|cancer|enfermedad|s[ií]ntoma|medicamento|tratamiento"
        r"|vaccine|disease|drug|dosis|cl[ií]nic|hospital|salud|health|covid|diabetes"
        r"|heart|coraz[oó]n|infarto|cardio|aspirin|aspirina|cirug[ií]a|surgery|tumor"
        r"|terapia|therapy|s[ií]ndrome|syndrome|m[eé]dic\w*|medical|colesterol|cholesterol)\b",
        re.IGNORECASE,
    ),
    "ciencia": re.compile(
        r"\b(estudio|study|investigaci[oó]n|research|f[ií]sica|qu[ií]mica|biolog"
        r"|clima|climate|energ[ií]a|planeta|nasa|especie|gen[eé]tic|quantum|cu[aá]ntic)\b",
        re.IGNORECASE,
    ),
    "actualidad": re.compile(
        r"\b(presidente|president|gobierno|government|elecci[oó]n|election|ministr"
        r"|congreso|senador|senator|ley|pol[ií]tic|guerra|war|tratado|alcalde|partido)\b",
        re.IGNORECASE,
    ),
}

# Descripciones para el zero-shot (hipótesis que el verificador compara).
_HIPOTESIS = {
    "programacion": "Este texto trata sobre programación, software o computación.",
    "matematicas": "Este texto trata sobre matemáticas.",
    "medicina": "Este texto trata sobre medicina, salud o enfermedades.",
    "ciencia": "Este texto trata sobre ciencia o investigación científica.",
    "actualidad": "Este texto trata sobre política, noticias o sucesos de actualidad.",
    "general": "Este texto trata sobre conocimiento general.",
}


def clasificar_por_palabras(texto: str) -> str:
    """Nivel 1: la primera categoría cuyo patrón aparezca. 'general' si ninguna."""
    for categoria, patron in _PATRONES.items():
        if patron.search(texto):
            return categoria
    return "general"


def clasificar(texto: str, verificador=None) -> str:
    """Clasifica el tema del texto; con verificador refina los casos ambiguos."""
    categoria = clasificar_por_palabras(texto)
    if categoria != "general" or verificador is None:
        return categoria
    puntuaciones = verificador.puntuar_entailment(texto, list(_HIPOTESIS.values()))
    mejor = max(zip(_HIPOTESIS, puntuaciones), key=lambda par: par[1])
    # Solo abandona 'general' si el modelo está razonablemente seguro.
    return mejor[0] if mejor[1] >= 0.5 and mejor[0] != "general" else "general"

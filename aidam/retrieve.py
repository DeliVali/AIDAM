"""Recuperador multi-fuente y multilingüe (Módulo 2).

Busca evidencia para un hecho atómico en fuentes heterogéneas y la etiqueta
con su procedencia. La información es libre sin importar el idioma: además
de buscar en el idioma de la afirmación, sigue los enlaces interlingüísticos
de Wikipedia para traer el mismo artículo en otros idiomas — sin modelo de
traducción, y cada edición de Wikipedia es una comunidad editorial distinta
(una voz independiente más para el agregador). El verificador multilingüe
juzga pares cruzados (afirmación en español, evidencia en chino) sin cambios.

La independencia de fuentes se aproxima por dominio: cien páginas del mismo
dominio cuentan como una voz en el agregador.

Este módulo es ingeniería pura: cero parámetros de modelo.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from .models import Evidencia, HechoAtomico

_UA = {"User-Agent": "AIDAM/0.1 (verificador abierto; https://github.com/DeliVali/AIDAM)"}
_TIMEOUT = 15
_MAX_CHARS_PASAJE = 600

# Wikipedias grandes y diversas geográficamente, en orden de preferencia
# cuando hay que elegir un subconjunto de los idiomas disponibles.
IDIOMAS_PREFERIDOS = ["en", "es", "fr", "de", "ru", "zh", "pt", "it", "ja", "ar"]


def _dominio(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")


def _trocear(texto: str, max_chars: int = _MAX_CHARS_PASAJE) -> list[str]:
    """Divide un texto largo en pasajes de ~max_chars respetando frases."""
    frases = re.split(r"(?<=[.!?])\s+", texto)
    pasajes: list[str] = []
    actual = ""
    for frase in frases:
        if actual and len(actual) + len(frase) > max_chars:
            pasajes.append(actual.strip())
            actual = frase
        else:
            actual = f"{actual} {frase}".strip()
    if actual:
        pasajes.append(actual.strip())
    return pasajes


def _relevancia(consulta: str, pasaje: str) -> int:
    """Solape léxico simple consulta↔pasaje. Suficiente para preseleccionar."""
    palabras = {p for p in re.findall(r"\w{4,}", consulta.lower())}
    return sum(1 for p in palabras if p in pasaje.lower())


def _wiki_get(lang: str, params: dict) -> dict | None:
    try:
        r = requests.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={**params, "format": "json"},
            headers=_UA,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def _buscar_titulos(consulta: str, lang: str, max_articulos: int) -> list[str]:
    datos = _wiki_get(
        lang, {"action": "query", "list": "search", "srsearch": consulta, "srlimit": max_articulos}
    )
    try:
        return [hit["title"] for hit in datos["query"]["search"]]
    except (TypeError, KeyError):
        return []


def _pasajes_de_articulo(
    lang: str, titulo: str, max_pasajes: int, consulta: str | None = None
) -> list[Evidencia]:
    """Extrae pasajes de un artículo. Con `consulta` los ordena por relevancia
    léxica; sin ella (idiomas que no comparten vocabulario con la consulta)
    usa el orden del artículo, donde la introducción resume lo esencial."""
    datos = _wiki_get(
        lang,
        {"action": "query", "prop": "extracts", "explaintext": 1, "exchars": 6000, "titles": titulo},
    )
    try:
        extracto = next(iter(datos["query"]["pages"].values())).get("extract", "")
    except (TypeError, KeyError, StopIteration):
        return []
    url = f"https://{lang}.wikipedia.org/wiki/{titulo.replace(' ', '_')}"
    pasajes = _trocear(extracto)
    if consulta is not None:
        pasajes.sort(key=lambda p: _relevancia(consulta, p), reverse=True)
    return [
        Evidencia(
            texto=pasaje,
            url=url,
            titulo=titulo,
            dominio=f"{lang}.wikipedia.org",
            fuente="wikipedia",
            idioma=lang,
        )
        for pasaje in pasajes[:max_pasajes]
    ]


def _idiomas_disponibles(lang: str, titulo: str) -> dict[str, str]:
    """idioma → título del mismo artículo en las demás Wikipedias (langlinks)."""
    datos = _wiki_get(
        lang, {"action": "query", "prop": "langlinks", "titles": titulo, "lllimit": 500}
    )
    try:
        enlaces = next(iter(datos["query"]["pages"].values())).get("langlinks", [])
        return {e["lang"]: e["*"] for e in enlaces}
    except (TypeError, KeyError, StopIteration):
        return {}


def _priorizar_idiomas(
    disponibles: dict[str, str], excluir: str, max_idiomas: int
) -> list[tuple[str, str]]:
    """Elige qué idiomas consultar: primero los preferidos, luego el resto
    en orden alfabético (determinista), sin repetir el idioma de origen."""
    preferidos = [l for l in IDIOMAS_PREFERIDOS if l != excluir and l in disponibles]
    resto = sorted(l for l in disponibles if l != excluir and l not in IDIOMAS_PREFERIDOS)
    return [(l, disponibles[l]) for l in (preferidos + resto)[:max_idiomas]]


def buscar_wikipedia(
    consulta: str, lang: str = "es", max_articulos: int = 2, max_pasajes: int = 4
) -> list[Evidencia]:
    """Busca artículos en la Wikipedia del idioma de la afirmación."""
    evidencias: list[Evidencia] = []
    for titulo in _buscar_titulos(consulta, lang, max_articulos):
        evidencias.extend(_pasajes_de_articulo(lang, titulo, max_pasajes, consulta=consulta))
    evidencias.sort(key=lambda e: _relevancia(consulta, e.texto), reverse=True)
    return evidencias[:max_pasajes]


def buscar_wikipedia_multilingue(
    consulta: str,
    lang: str = "es",
    max_idiomas: int = 5,
    max_pasajes_por_idioma: int = 2,
) -> list[Evidencia]:
    """Trae el mejor artículo en otros idiomas vía enlaces interlingüísticos.

    `max_idiomas=0` desactiva; un valor alto (p. ej. 300) consulta todas las
    ediciones donde exista el artículo, a costa de latencia.
    """
    if max_idiomas <= 0:
        return []
    titulos = _buscar_titulos(consulta, lang, max_articulos=1)
    if not titulos:
        return []
    disponibles = _idiomas_disponibles(lang, titulos[0])
    evidencias: list[Evidencia] = []
    for idioma, titulo in _priorizar_idiomas(disponibles, excluir=lang, max_idiomas=max_idiomas):
        evidencias.extend(_pasajes_de_articulo(idioma, titulo, max_pasajes_por_idioma))
    return evidencias


def buscar_web(consulta: str, max_resultados: int = 8, lang: str = "") -> list[Evidencia]:
    """Busca en la web (DuckDuckGo) y usa los snippets como evidencia."""
    try:
        from ddgs import DDGS
    except ImportError:
        return []
    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(consulta, max_results=max_resultados))
    except Exception:
        return []

    evidencias = []
    for hit in hits:
        url = hit.get("href", "")
        cuerpo = hit.get("body", "")
        if not url or len(cuerpo) < 40:
            continue
        evidencias.append(
            Evidencia(
                texto=cuerpo,
                url=url,
                titulo=hit.get("title", url),
                dominio=_dominio(url),
                fuente="web",
                idioma=lang,
            )
        )
    return evidencias


def recuperar(
    hecho: HechoAtomico, lang: str = "es", max_web: int = 8, max_idiomas: int = 5
) -> list[Evidencia]:
    """Recupera evidencia de todas las fuentes e idiomas, deduplicada."""
    evidencias = (
        buscar_wikipedia(hecho.texto, lang=lang)
        + buscar_wikipedia_multilingue(hecho.texto, lang=lang, max_idiomas=max_idiomas)
        + buscar_web(hecho.texto, max_resultados=max_web, lang=lang)
    )
    vistas: set[tuple[str, str]] = set()
    unicas = []
    for e in evidencias:
        clave = (e.dominio, e.texto[:120])
        if clave not in vistas:
            vistas.add(clave)
            unicas.append(e)
    return unicas

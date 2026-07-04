"""Recuperador multi-fuente (Módulo 2).

Busca evidencia para un hecho atómico en fuentes heterogéneas (Wikipedia y
búsqueda web) y la etiqueta con su procedencia. La independencia de fuentes
se aproxima por dominio: cien páginas del mismo dominio cuentan como una voz
en el agregador.

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


def buscar_wikipedia(
    consulta: str, lang: str = "es", max_articulos: int = 2, max_pasajes: int = 4
) -> list[Evidencia]:
    """Busca artículos de Wikipedia y devuelve los pasajes más relevantes."""
    api = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        r = requests.get(
            api,
            params={
                "action": "query",
                "list": "search",
                "srsearch": consulta,
                "srlimit": max_articulos,
                "format": "json",
            },
            headers=_UA,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        hits = r.json()["query"]["search"]
    except (requests.RequestException, KeyError):
        return []

    evidencias: list[Evidencia] = []
    for hit in hits:
        titulo = hit["title"]
        try:
            r = requests.get(
                api,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": 1,
                    "exchars": 6000,
                    "titles": titulo,
                    "format": "json",
                },
                headers=_UA,
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            paginas = r.json()["query"]["pages"]
            extracto = next(iter(paginas.values())).get("extract", "")
        except (requests.RequestException, KeyError, StopIteration):
            continue
        url = f"https://{lang}.wikipedia.org/wiki/{titulo.replace(' ', '_')}"
        for pasaje in _trocear(extracto):
            evidencias.append(
                Evidencia(
                    texto=pasaje,
                    url=url,
                    titulo=titulo,
                    dominio=f"{lang}.wikipedia.org",
                    fuente="wikipedia",
                )
            )

    evidencias.sort(key=lambda e: _relevancia(consulta, e.texto), reverse=True)
    return evidencias[:max_pasajes]


def buscar_web(consulta: str, max_resultados: int = 8) -> list[Evidencia]:
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
            )
        )
    return evidencias


def recuperar(hecho: HechoAtomico, lang: str = "es", max_web: int = 8) -> list[Evidencia]:
    """Recupera evidencia de todas las fuentes, deduplicada por (dominio, texto)."""
    evidencias = buscar_wikipedia(hecho.texto, lang=lang) + buscar_web(
        hecho.texto, max_resultados=max_web
    )
    vistas: set[tuple[str, str]] = set()
    unicas = []
    for e in evidencias:
        clave = (e.dominio, e.texto[:120])
        if clave not in vistas:
            vistas.add(clave)
            unicas.append(e)
    return unicas

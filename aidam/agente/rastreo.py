"""Optional tier-2 web crawling (extra `rastreo`): Crawl4AI for JS-heavy pages.

The retrieval doctrine is tiered: plain HTTP + trafilatura (retrieve.py)
stays tier-1 for everything — cheap, fast, and enough for the API/wiki/feed
majority. This module is the escalation for pages that come back empty or
need a real browser. robots.txt is always honored (open project, respectful
crawler). Deliberately NOT wired into the FUENTES registry: adding it there
is a retrieval change that must be measured first, per house methodology.
"""

from __future__ import annotations

import importlib.util
import threading
from urllib.parse import urlparse

from ..models import Evidencia

_TROZO = 800  # passage size, chars — comparable to what trafilatura extraction yields


def hay_rastreador() -> bool:
    return importlib.util.find_spec("crawl4ai") is not None


def rastrear(url: str, lang: str = "es") -> list[Evidencia]:
    """Renders one URL with a headless browser and returns clean passages.

    Crawl4AI is asyncio-based; the event loop is confined to a dedicated
    thread here because the rest of this codebase is thread-based on purpose
    (repo policy: threads, never asyncio in module APIs).
    """
    if not hay_rastreador():
        raise RuntimeError(
            "crawl4ai no está instalado: instala el extra de rastreo con "
            "`pip install aidam[rastreo]`"
        )

    resultado: list = []
    error: list[BaseException] = []

    def _correr() -> None:
        import asyncio

        try:
            resultado.append(asyncio.run(_rastrear_async(url)))
        except BaseException as excepcion:  # surfaced to the caller below
            error.append(excepcion)

    hilo = threading.Thread(target=_correr, daemon=True)
    hilo.start()
    hilo.join(120.0)
    if error:
        raise RuntimeError(f"rastreo falló para {url}: {error[0]}")
    if not resultado or hilo.is_alive():
        return []

    markdown = resultado[0]
    if not markdown:
        return []
    dominio = urlparse(url).netloc
    return [
        Evidencia(texto=trozo, url=url, titulo="", dominio=dominio, fuente="web", idioma=lang)
        for trozo in _trocear(markdown)
    ]


async def _rastrear_async(url: str) -> str:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

    config = CrawlerRunConfig(check_robots_txt=True)
    async with AsyncWebCrawler() as rastreador:
        pagina = await rastreador.arun(url=url, config=config)
    if not getattr(pagina, "success", False):
        return ""
    markdown = getattr(pagina, "markdown", None)
    # Newer crawl4ai exposes .markdown.fit_markdown (noise-reduced for models).
    ajustado = getattr(markdown, "fit_markdown", None)
    return str(ajustado or markdown or "")


def _trocear(texto: str) -> list[str]:
    """Paragraph-respecting chunks of ~_TROZO chars, whitespace-normalized."""
    trozos: list[str] = []
    actual: list[str] = []
    largo = 0
    for parrafo in (p.strip() for p in texto.split("\n\n")):
        if not parrafo:
            continue
        parrafo = " ".join(parrafo.split())
        if largo + len(parrafo) > _TROZO and actual:
            trozos.append("\n".join(actual))
            actual, largo = [], 0
        actual.append(parrafo)
        largo += len(parrafo)
    if actual:
        trozos.append("\n".join(actual))
    return [t for t in trozos if len(t) >= 40]  # drop nav/boilerplate crumbs

"""Multi-source, multilingual retriever (Module 2).

Searches evidence for an atomic fact across as many sources as possible and
labels it with its provenance. Sources live in the `FUENTES` registry:
adding a new one means writing a `(consulta, lang) -> list[Evidencia]`
function and registering it — all are queried in parallel.

Current families (all with free APIs, no keys):
- Wikipedia in the claim's language, with lexical passage ranking.
- Multilingual Wikipedia: the same article in other languages via interlanguage
  links — no translation model; each edition is a distinct editorial
  community (one more independent voice).
- Wikinews: collaborative journalism, same MediaWiki API.
- Wikiquote: the certified source for attribution claims ("X said Y" is a
  top viral-misinformation genre), same MediaWiki API.
- Open web (DuckDuckGo/Bing/Yahoo rotation): thousands of domains, with a
  local cache and pacing so no engine rate-limits the machine.
- News: GDELT (global, multilingual press coverage).
- Academic: Semantic Scholar, OpenAlex, arXiv, Europe PMC and Crossref —
  paper abstracts for scientific claims (mostly English corpus).
- Technical Q&A: Stack Overflow and Math StackExchange.

Source independence is approximated by domain: a hundred pages from the same
domain count as one voice in the aggregator.

This module is pure engineering: zero model parameters.
"""

from __future__ import annotations

import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

from .models import Evidencia, HechoAtomico

_UA = {"User-Agent": "AIDAM/0.1 (verificador abierto; https://github.com/DeliVali/AIDAM)"}
_TIMEOUT = 15
_MAX_CHARS_PASAJE = 600

# Large, geographically diverse Wikipedias, in order of preference when a
# subset of the available languages must be chosen.
IDIOMAS_PREFERIDOS = ["en", "es", "fr", "de", "ru", "zh", "pt", "it", "ja", "ar"]


# ───────────────────────── shared utilities ─────────────────────────


def _dominio(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")


def _trocear(texto: str, max_chars: int = _MAX_CHARS_PASAJE) -> list[str]:
    """Splits a long text into ~max_chars passages, respecting sentences."""
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
    """Simple query↔passage lexical overlap. Enough for preselection."""
    palabras = {p for p in re.findall(r"\w{4,}", consulta.lower())}
    return sum(1 for p in palabras if p in pasaje.lower())


def _get_json(url: str, params: dict | None = None) -> dict | None:
    try:
        r = requests.get(url, params=params, headers=_UA, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


# ───────────────────────── MediaWiki (Wikipedia, Wikinews) ─────────────────


def _mediawiki_get(host: str, params: dict) -> dict | None:
    return _get_json(f"https://{host}/w/api.php", {**params, "format": "json"})


def _buscar_titulos(consulta: str, host: str, max_articulos: int) -> list[str]:
    datos = _mediawiki_get(
        host, {"action": "query", "list": "search", "srsearch": consulta, "srlimit": max_articulos}
    )
    try:
        return [hit["title"] for hit in datos["query"]["search"]]
    except (TypeError, KeyError):
        return []


def _pasajes_de_articulo(
    host: str,
    titulo: str,
    max_pasajes: int,
    fuente: str,
    idioma: str,
    consulta: str | None = None,
) -> list[Evidencia]:
    """Extracts passages from a MediaWiki article. With `consulta` it ranks
    them by lexical relevance; without it (languages that share no vocabulary
    with the query) it uses article order, where the intro sums up the essentials."""
    datos = _mediawiki_get(
        host,
        {"action": "query", "prop": "extracts", "explaintext": 1, "exchars": 6000, "titles": titulo},
    )
    try:
        extracto = next(iter(datos["query"]["pages"].values())).get("extract", "")
    except (TypeError, KeyError, StopIteration):
        return []
    url = f"https://{host}/wiki/{titulo.replace(' ', '_')}"
    pasajes = _trocear(extracto)
    if consulta is not None:
        pasajes.sort(key=lambda p: _relevancia(consulta, p), reverse=True)
    return [
        Evidencia(texto=p, url=url, titulo=titulo, dominio=host, fuente=fuente, idioma=idioma)
        for p in pasajes[:max_pasajes]
    ]


def _idiomas_disponibles(lang: str, titulo: str) -> dict[str, str]:
    """language → title of the same article on the other Wikipedias (langlinks)."""
    datos = _mediawiki_get(
        f"{lang}.wikipedia.org",
        {"action": "query", "prop": "langlinks", "titles": titulo, "lllimit": 500},
    )
    try:
        enlaces = next(iter(datos["query"]["pages"].values())).get("langlinks", [])
        return {e["lang"]: e["*"] for e in enlaces}
    except (TypeError, KeyError, StopIteration):
        return {}


def _priorizar_idiomas(
    disponibles: dict[str, str], excluir: str, max_idiomas: int
) -> list[tuple[str, str]]:
    """Chooses which languages to query: preferred ones first, then the rest
    in alphabetical order (deterministic), never repeating the source language."""
    preferidos = [l for l in IDIOMAS_PREFERIDOS if l != excluir and l in disponibles]
    resto = sorted(l for l in disponibles if l != excluir and l not in IDIOMAS_PREFERIDOS)
    return [(l, disponibles[l]) for l in (preferidos + resto)[:max_idiomas]]


def buscar_wikipedia(
    consulta: str, lang: str = "es", max_articulos: int = 2, max_pasajes: int = 4
) -> list[Evidencia]:
    """Searches articles on the Wikipedia of the claim's language."""
    host = f"{lang}.wikipedia.org"
    evidencias: list[Evidencia] = []
    for titulo in _buscar_titulos(consulta, host, max_articulos):
        evidencias.extend(
            _pasajes_de_articulo(host, titulo, max_pasajes, "wikipedia", lang, consulta=consulta)
        )
    evidencias.sort(key=lambda e: _relevancia(consulta, e.texto), reverse=True)
    return evidencias[:max_pasajes]


def buscar_wikipedia_multilingue(
    consulta: str,
    lang: str = "es",
    max_idiomas: int = 5,
    max_pasajes_por_idioma: int = 2,
) -> list[Evidencia]:
    """Fetches the best article in other languages via interlanguage links.

    `max_idiomas=0` disables it; a high value (e.g. 300) queries every
    edition where the article exists, at the cost of latency.
    """
    if max_idiomas <= 0:
        return []
    titulos = _buscar_titulos(consulta, f"{lang}.wikipedia.org", max_articulos=1)
    if not titulos:
        return []
    disponibles = _idiomas_disponibles(lang, titulos[0])
    evidencias: list[Evidencia] = []
    for idioma, titulo in _priorizar_idiomas(disponibles, excluir=lang, max_idiomas=max_idiomas):
        evidencias.extend(
            _pasajes_de_articulo(
                f"{idioma}.wikipedia.org", titulo, max_pasajes_por_idioma, "wikipedia", idioma
            )
        )
    return evidencias


def buscar_wikinews(consulta: str, lang: str = "es", max_pasajes: int = 3) -> list[Evidencia]:
    """Collaborative journalism from Wikinews (same MediaWiki API)."""
    host = f"{lang}.wikinews.org"
    evidencias: list[Evidencia] = []
    for titulo in _buscar_titulos(consulta, host, max_articulos=2):
        evidencias.extend(
            _pasajes_de_articulo(host, titulo, 2, "wikinews", lang, consulta=consulta)
        )
    return evidencias[:max_pasajes]


def buscar_wikiquote(consulta: str, lang: str = "es", max_pasajes: int = 3) -> list[Evidencia]:
    """Curated quotes with sourcing (same MediaWiki API).

    Misattributed quotes ("X said Y") are one of the most common viral-claim
    genres; Wikiquote pages document both the sourced quotes and the
    'misattributed' sections.
    """
    host = f"{lang}.wikiquote.org"
    evidencias: list[Evidencia] = []
    for titulo in _buscar_titulos(consulta, host, max_articulos=2):
        evidencias.extend(
            _pasajes_de_articulo(host, titulo, 2, "wikiquote", lang, consulta=consulta)
        )
    return evidencias[:max_pasajes]


# ───────────────────────── open web ─────────────────────────


# libxml2 (inside trafilatura/lxml) is NOT thread-safe: extracting in
# parallel corrupts the heap (measured: SIGABRT in xmlFreeDoc, core dump in
# the 500-claim eval). Network stays parallel; extraction is serialized —
# ~30 ms per page, nothing next to the fetch.
_CANDADO_EXTRACCION = threading.Lock()


def _texto_de_pagina(url: str) -> str:
    """Downloads a page and extracts its main text (no menus or ads).

    Truncated search-engine snippets repeat headlines; an article's verdict
    lives in its body. Measured on AVeriTeC: judging snippets was the
    system's bottleneck.
    """
    try:
        import trafilatura

        r = requests.get(url, headers=_UA, timeout=8)
        r.raise_for_status()
        with _CANDADO_EXTRACCION:
            return trafilatura.extract(r.text) or ""
    except Exception:
        return ""


# Search engine rotation: DuckDuckGo blocked our connection after a day of
# evaluations (measured: 73/100 claims with no evidence). No single engine
# can be a point of failure for the retriever.
_BACKENDS_BUSQUEDA = ("duckduckgo", "bing", "yahoo")

# Cache + pacing (measured 2026-07-07: after days of evals, EVERY engine
# rate-limited this IP mid-run — 75/100 claims with zero evidence). The cache
# makes repeated queries free (and lets A/B evals reuse identical evidence:
# the substrate stops changing under the experiment); the pacing keeps live
# queries below the rate that gets an IP banned.
_RUTA_CACHE = Path("data/local/search_cache.sqlite")
_TTL_CACHE = float(os.environ.get("AIDAM_CACHE_TTL", 7 * 24 * 3600))
_PAUSA_BUSQUEDA = float(os.environ.get("AIDAM_PAUSA_BUSQUEDA", 1.0))
_FALLOS_PARA_ENFRIAR = 3
_SEGUNDOS_ENFRIAMIENTO = 300.0

_CANDADO_BUSQUEDA = threading.Lock()
_ultima_busqueda = 0.0
_fallos_seguidos: dict[str, int] = {}
_enfriado_hasta: dict[str, float] = {}


def _cache_conexion():
    import sqlite3

    _RUTA_CACHE.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(_RUTA_CACHE, timeout=10)
    conexion.execute(
        "CREATE TABLE IF NOT EXISTS busquedas (clave TEXT PRIMARY KEY, ts REAL, hits TEXT)"
    )
    return conexion


def _cache_leer(clave: str) -> list[dict] | None:
    import json as _json

    if os.environ.get("AIDAM_CACHE_BUSQUEDA") == "0":
        return None
    try:
        with _cache_conexion() as conexion:
            fila = conexion.execute(
                "SELECT ts, hits FROM busquedas WHERE clave = ?", (clave,)
            ).fetchone()
        if fila and time.time() - fila[0] < _TTL_CACHE:
            return _json.loads(fila[1])
    except Exception:
        pass
    return None


def _cache_guardar(clave: str, hits: list[dict]) -> None:
    import json as _json

    if os.environ.get("AIDAM_CACHE_BUSQUEDA") == "0":
        return
    try:
        with _cache_conexion() as conexion:
            conexion.execute(
                "INSERT OR REPLACE INTO busquedas VALUES (?, ?, ?)",
                (clave, time.time(), _json.dumps(hits, ensure_ascii=False)),
            )
    except Exception:
        pass


def _esperar_turno() -> None:
    """Global pacing: at most one engine query per _PAUSA_BUSQUEDA seconds."""
    global _ultima_busqueda
    with _CANDADO_BUSQUEDA:
        espera = _ultima_busqueda + _PAUSA_BUSQUEDA - time.time()
        if espera > 0:
            time.sleep(espera)
        _ultima_busqueda = time.time()


def _backend_disponible(backend: str) -> bool:
    return time.time() >= _enfriado_hasta.get(backend, 0.0)


def _registrar_resultado(backend: str, exito: bool) -> None:
    """Cooldown bookkeeping: N consecutive failures rest the engine a while.

    One empty result can be a legitimately rare query; three in a row is the
    profile of an engine that started refusing us.
    """
    if exito:
        _fallos_seguidos[backend] = 0
        return
    _fallos_seguidos[backend] = _fallos_seguidos.get(backend, 0) + 1
    if _fallos_seguidos[backend] >= _FALLOS_PARA_ENFRIAR:
        _enfriado_hasta[backend] = time.time() + _SEGUNDOS_ENFRIAMIENTO
        _fallos_seguidos[backend] = 0


def _buscar_ddg(consulta: str, max_resultados: int) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        return []
    clave = f"{consulta}|{max_resultados}"
    if (cacheado := _cache_leer(clave)) is not None:
        return cacheado
    for backend in _BACKENDS_BUSQUEDA:
        if not _backend_disponible(backend):
            continue
        _esperar_turno()
        try:
            hits = list(
                DDGS(timeout=6).text(consulta, max_results=max_resultados, backend=backend)
            )
        except Exception:
            hits = []
        _registrar_resultado(backend, bool(hits))
        if hits:
            _cache_guardar(clave, hits)
            return hits
    return []


def _evidencias_de_paginas(
    hits: list[dict],
    consulta: str,
    fuente: str,
    lang: str,
    max_paginas: int,
    max_pasajes_por_pagina: int = 3,
) -> list[Evidencia]:
    """Full text of the best results, in parallel, with lexical ranking."""
    candidatos = [h for h in hits if h.get("href")][:max_paginas]
    with ThreadPoolExecutor(max_workers=max(1, len(candidatos))) as ejecutor:
        textos = list(ejecutor.map(lambda h: _texto_de_pagina(h["href"]), candidatos))
    evidencias: list[Evidencia] = []
    for hit, texto in zip(candidatos, textos):
        pasajes = _trocear(texto)
        pasajes.sort(key=lambda p: _relevancia(consulta, p), reverse=True)
        for pasaje in pasajes[:max_pasajes_por_pagina]:
            if len(pasaje) < 40:
                continue
            evidencias.append(
                Evidencia(
                    texto=pasaje,
                    url=hit["href"],
                    titulo=hit.get("title", hit["href"]),
                    dominio=_dominio(hit["href"]),
                    fuente=fuente,
                    idioma=lang,
                )
            )
    return evidencias


def buscar_web(
    consulta: str, max_resultados: int = 8, lang: str = "", paginas_completas: int = 3
) -> list[Evidencia]:
    """Web search (DuckDuckGo): full text of the top results, snippets for
    the rest."""
    hits = _buscar_ddg(consulta, max_resultados)
    evidencias = _evidencias_de_paginas(hits, consulta, "web", lang, paginas_completas)
    for hit in hits[paginas_completas:]:
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


# Official documentation per technical domain: the professional fact-checker's
# equivalent for code, commands and infrastructure. For a claim about AWS,
# the certified source is docs.aws.amazon.com, not a blog.
DOCS_CERTIFICADAS: dict[str, list[str]] = {
    "programacion": [
        "docs.python.org", "developer.mozilla.org", "docs.aws.amazon.com",
        "learn.microsoft.com", "kubernetes.io", "man7.org", "docs.docker.com",
        "en.cppreference.com", "doc.rust-lang.org", "nodejs.org", "pkg.go.dev",
    ],
    "matematicas": [
        "mathworld.wolfram.com", "encyclopediaofmath.org", "proofwiki.org",
        "oeis.org", "dlmf.nist.gov",
    ],
}


def buscar_docs_certificadas(
    consulta: str, categoria: str, lang: str = "", max_resultados: int = 6
) -> list[Evidencia]:
    """Searches only the domain's official documentation (DDG site: filter),
    reading full pages."""
    dominios = DOCS_CERTIFICADAS.get(categoria, [])
    if not dominios:
        return []
    filtro = " OR ".join(f"site:{d}" for d in dominios[:6])
    hits = _buscar_ddg(f"{consulta} ({filtro})", max_resultados)
    return _evidencias_de_paginas(hits, consulta, "docs-oficiales", lang, max_paginas=3)


def buscar_desmentidos(consulta: str, lang: str = "es") -> list[Evidencia]:
    """Search aimed at fact-checks: brings the fact-checkers to the table.

    Measured on AVeriTeC: in most of the lies that passed as supported, the
    fact-checker didn't even appear in the evidence. This reformulated query
    looks for it explicitly, and reads the full article (the verdict doesn't
    fit in a snippet).
    """
    sufijo = "fact check" if lang == "en" else "verificación bulo fact check"
    hits = _buscar_ddg(f"{consulta} {sufijo}", max_resultados=5)
    return _evidencias_de_paginas(hits, consulta, "desmentidos", lang, max_paginas=3)


# ───────────────────────── technical / programming ─────────────────────────


def buscar_stackexchange(
    consulta: str, lang: str = "", max_resultados: int = 4, site: str = "stackoverflow"
) -> list[Evidencia]:
    """Questions and answers from the Stack Exchange network (free API, no key).

    For programming claims: nobody goes to Wikipedia for a bug. `site` picks
    the community: "stackoverflow" for code, "math" for mathematics.
    """
    dominio = "stackoverflow.com" if site == "stackoverflow" else f"{site}.stackexchange.com"
    datos = _get_json(
        "https://api.stackexchange.com/2.3/search/excerpts",
        {
            "order": "desc",
            "sort": "relevance",
            "q": consulta,
            "site": site,
            "pagesize": max_resultados,
        },
    )
    evidencias: list[Evidencia] = []
    for item in (datos or {}).get("items", []):
        extracto = re.sub(r"<[^>]+>", " ", item.get("excerpt", "")).strip()
        qid = item.get("question_id")
        if len(extracto) < 40 or not qid:
            continue
        evidencias.append(
            Evidencia(
                texto=extracto,
                url=f"https://{dominio}/q/{qid}",
                titulo=item.get("title", ""),
                dominio=dominio,
                fuente="stackexchange",
                idioma="en",
            )
        )
    return evidencias


_CANDADO_GDELT = threading.Lock()
_ultimo_gdelt = 0.0
_PAUSA_GDELT = 5.1  # GDELT's stated limit: one query every 5 seconds


def buscar_gdelt(consulta: str, lang: str = "", max_articulos: int = 6) -> list[Evidencia]:
    """Global press coverage via GDELT DOC 2.0 (free API, no key, multilingual).

    For current-affairs claims: GDELT indexes news in dozens of languages in
    near real time. The article list only carries titles, so the top pages
    are read in full (an article's verdict lives in its body).
    """
    global _ultimo_gdelt
    with _CANDADO_GDELT:
        espera = _ultimo_gdelt + _PAUSA_GDELT - time.time()
        if espera > 0:
            time.sleep(espera)
        _ultimo_gdelt = time.time()
    datos = _get_json(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        {
            "query": consulta,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": max_articulos,
            "sort": "HybridRel",
        },
    )
    hits = [
        {"href": a.get("url", ""), "title": a.get("title", "")}
        for a in (datos or {}).get("articles", [])
        if a.get("url")
    ]
    return _evidencias_de_paginas(hits, consulta, "gdelt", lang, max_paginas=2)


# ───────────────────────── academic sources ─────────────────────────


def _evidencias_de_resumen(
    resumen: str, url: str, titulo: str, dominio: str, fuente: str, max_pasajes: int = 2
) -> list[Evidencia]:
    if not resumen or len(resumen) < 40:
        return []
    return [
        Evidencia(texto=p, url=url, titulo=titulo, dominio=dominio, fuente=fuente, idioma="")
        for p in _trocear(resumen)[:max_pasajes]
    ]


def buscar_semantic_scholar(consulta: str, lang: str = "", max_papers: int = 4) -> list[Evidencia]:
    """Paper abstracts via Semantic Scholar (free API, no key)."""
    datos = _get_json(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        {"query": consulta, "limit": max_papers, "fields": "title,abstract,url"},
    )
    evidencias: list[Evidencia] = []
    for paper in (datos or {}).get("data", []):
        evidencias.extend(
            _evidencias_de_resumen(
                paper.get("abstract") or "",
                paper.get("url") or "https://www.semanticscholar.org",
                paper.get("title", ""),
                "semanticscholar.org",
                "academica",
            )
        )
    return evidencias


def _reconstruir_resumen_openalex(indice_invertido: dict[str, list[int]]) -> str:
    """OpenAlex publishes abstracts as an inverted word→positions index;
    we rebuild it by sorting the positions."""
    posiciones: list[tuple[int, str]] = []
    for palabra, sitios in indice_invertido.items():
        posiciones.extend((sitio, palabra) for sitio in sitios)
    return " ".join(palabra for _, palabra in sorted(posiciones))


def buscar_openalex(consulta: str, lang: str = "", max_papers: int = 4) -> list[Evidencia]:
    """Paper abstracts via OpenAlex (free API, no key)."""
    datos = _get_json(
        "https://api.openalex.org/works",
        {"search": consulta, "per-page": max_papers, "select": "title,doi,abstract_inverted_index"},
    )
    evidencias: list[Evidencia] = []
    for obra in (datos or {}).get("results", []):
        indice = obra.get("abstract_inverted_index")
        if not indice:
            continue
        evidencias.extend(
            _evidencias_de_resumen(
                _reconstruir_resumen_openalex(indice),
                obra.get("doi") or "https://openalex.org",
                obra.get("title", ""),
                "openalex.org",
                "academica",
            )
        )
    return evidencias


def buscar_arxiv(consulta: str, lang: str = "", max_papers: int = 3) -> list[Evidencia]:
    """Preprint abstracts from arXiv (free API, no key)."""
    try:
        r = requests.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": f"all:{consulta}", "max_results": max_papers},
            headers=_UA,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        raiz = ET.fromstring(r.text)
    except (requests.RequestException, ET.ParseError):
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    evidencias: list[Evidencia] = []
    for entrada in raiz.findall("a:entry", ns):
        resumen = (entrada.findtext("a:summary", "", ns) or "").strip()
        evidencias.extend(
            _evidencias_de_resumen(
                re.sub(r"\s+", " ", resumen),
                (entrada.findtext("a:id", "", ns) or "").strip() or "https://arxiv.org",
                (entrada.findtext("a:title", "", ns) or "").strip(),
                "arxiv.org",
                "academica",
            )
        )
    return evidencias


def buscar_crossref(consulta: str, lang: str = "", max_papers: int = 4) -> list[Evidencia]:
    """Scholarly metadata via Crossref (free API, no key).

    Complements Semantic Scholar/OpenAlex: Crossref indexes publisher
    metadata directly, so it sometimes has abstracts the others miss.
    Records without an abstract are skipped (a bare title proves nothing).
    """
    datos = _get_json(
        "https://api.crossref.org/works",
        {
            "query": consulta,
            "rows": max_papers,
            "select": "title,abstract,DOI",
            "filter": "has-abstract:true",
        },
    )
    evidencias: list[Evidencia] = []
    for obra in ((datos or {}).get("message") or {}).get("items", []):
        resumen = re.sub(r"<[^>]+>", " ", obra.get("abstract") or "")
        resumen = re.sub(r"\s+", " ", resumen).strip()
        titulos = obra.get("title") or [""]
        doi = obra.get("DOI", "")
        evidencias.extend(
            _evidencias_de_resumen(
                resumen,
                f"https://doi.org/{doi}" if doi else "https://www.crossref.org",
                titulos[0],
                "crossref.org",
                "academica",
            )
        )
    return evidencias


def buscar_europepmc(consulta: str, lang: str = "", max_papers: int = 4) -> list[Evidencia]:
    """Biomedical abstracts from Europe PMC (free API, no key)."""
    datos = _get_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        {"query": consulta, "format": "json", "pageSize": max_papers, "resultType": "core"},
    )
    resultados = ((datos or {}).get("resultList") or {}).get("result", [])
    evidencias: list[Evidencia] = []
    for articulo in resultados:
        pmid = articulo.get("id", "")
        evidencias.extend(
            _evidencias_de_resumen(
                articulo.get("abstractText") or "",
                f"https://europepmc.org/article/{articulo.get('source', 'MED')}/{pmid}",
                articulo.get("title", ""),
                "europepmc.org",
                "academica",
            )
        )
    return evidencias


# ───────────────────────── registry and orchestration ─────────────────────────

# name → (description, categories it serves or None = universal,
#         function (consulta, lang, max_idiomas) -> list[Evidencia]).
# To add a source: write a function with that signature and register it here.
# Categories come from the router (aidam/router.py): the agent doesn't go to
# Wikipedia for a bug or to Stack Overflow for a medical claim.
FUENTES: dict[str, tuple[str, set[str] | None, object]] = {
    "wikipedia": (
        "Wikipedia en el idioma de la afirmación (pasajes por relevancia)",
        None,
        lambda c, lang, mi: buscar_wikipedia(c, lang=lang),
    ),
    "wikipedia-multilingue": (
        "El mismo artículo en otros idiomas vía enlaces interlingüísticos",
        None,
        lambda c, lang, mi: buscar_wikipedia_multilingue(c, lang=lang, max_idiomas=mi),
    ),
    "wikinews": (
        "Periodismo colaborativo de Wikinews",
        {"actualidad", "general"},
        lambda c, lang, mi: buscar_wikinews(c, lang=lang),
    ),
    "wikiquote": (
        "Citas con fuente de Wikiquote (atribuciones «X dijo Y»)",
        {"actualidad", "general"},
        lambda c, lang, mi: buscar_wikiquote(c, lang=lang),
    ),
    "gdelt": (
        "Prensa global multilingüe vía GDELT (páginas completas)",
        {"actualidad"},
        lambda c, lang, mi: buscar_gdelt(c, lang=lang),
    ),
    "web": (
        "Web abierta vía DuckDuckGo (páginas completas + snippets)",
        None,
        lambda c, lang, mi: buscar_web(c, lang=lang),
    ),
    "desmentidos": (
        "Búsqueda dirigida a fact-checkers (artículo completo)",
        None,
        lambda c, lang, mi: buscar_desmentidos(c, lang=lang),
    ),
    "docs-programacion": (
        "Documentación oficial de lenguajes, clouds y herramientas",
        {"programacion"},
        lambda c, lang, mi: buscar_docs_certificadas(c, "programacion", lang=lang),
    ),
    "docs-matematicas": (
        "Referencias matemáticas certificadas (MathWorld, OEIS, DLMF…)",
        {"matematicas"},
        lambda c, lang, mi: buscar_docs_certificadas(c, "matematicas", lang=lang),
    ),
    "stackexchange": (
        "Preguntas y respuestas de Stack Overflow",
        {"programacion"},
        lambda c, lang, mi: buscar_stackexchange(c),
    ),
    "stackexchange-matematicas": (
        "Preguntas y respuestas de Math StackExchange",
        {"matematicas"},
        lambda c, lang, mi: buscar_stackexchange(c, site="math"),
    ),
    # Universal: a router misroute must ADD noise, never REMOVE signal
    # (measured: a medical claim routed to "general" lost its papers).
    "semantic-scholar": (
        "Resúmenes académicos de Semantic Scholar",
        None,
        lambda c, lang, mi: buscar_semantic_scholar(c, lang=lang),
    ),
    "openalex": (
        "Resúmenes académicos de OpenAlex",
        None,
        lambda c, lang, mi: buscar_openalex(c, lang=lang),
    ),
    "arxiv": (
        "Preprints científicos de arXiv",
        {"ciencia", "programacion", "matematicas"},
        lambda c, lang, mi: buscar_arxiv(c, lang=lang),
    ),
    "crossref": (
        "Metadatos y resúmenes de editoriales vía Crossref",
        {"ciencia", "medicina", "matematicas"},
        lambda c, lang, mi: buscar_crossref(c, lang=lang),
    ),
    "europepmc": (
        "Literatura biomédica de Europe PMC",
        {"medicina", "ciencia"},
        lambda c, lang, mi: buscar_europepmc(c, lang=lang),
    ),
}


def _es_probatoria(hecho_texto: str, evidencia: Evidencia, lang: str) -> bool:
    """Does the passage address what the fact asserts, or just the general topic?

    A passage in the claim's language sharing <2 of its content words can't
    prove or refute anything specific (measured: generic Wikipedia intros
    were judged as contradiction). Evidence in other languages is exempt —
    lexical overlap means nothing across languages; its cross-lingual
    ranking will come with multilingual embeddings.
    """
    if evidencia.idioma and evidencia.idioma != lang:
        return True
    palabras = set(re.findall(r"\w{4,}", hecho_texto.lower()))
    if len(palabras) < 3:
        return True
    presentes = sum(1 for p in palabras if p in evidencia.texto.lower())
    return presentes >= 2


def recuperar(
    hecho: HechoAtomico,
    lang: str = "es",
    max_idiomas: int = 5,
    categoria: str | None = None,
) -> list[Evidencia]:
    """Queries the sources relevant to the category in parallel and dedupes.

    Without a category, all are queried. Each source fails silently (returns
    an empty list): an external API outage never takes verification down,
    it only reduces the available evidence.
    """
    activas = [
        (descripcion, funcion)
        for descripcion, categorias, funcion in FUENTES.values()
        if categoria is None or categorias is None or categoria in categorias
    ]

    def _segura(nombre_y_fuente) -> list[Evidencia]:
        _descripcion, funcion = nombre_y_fuente
        try:
            return funcion(hecho.texto, lang, max_idiomas)
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=len(activas)) as ejecutor:
        lotes = ejecutor.map(_segura, activas)

    vistas: set[tuple[str, str]] = set()
    unicas: list[Evidencia] = []
    for lote in lotes:
        for e in lote:
            clave = (e.dominio, e.texto[:120])
            if clave not in vistas and _es_probatoria(hecho.texto, e, lang):
                vistas.add(clave)
                unicas.append(e)
    return unicas

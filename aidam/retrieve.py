"""Recuperador multi-fuente y multilingüe (Módulo 2).

Busca evidencia para un hecho atómico en la mayor cantidad de fuentes posible
y la etiqueta con su procedencia. Las fuentes viven en el registro `FUENTES`:
añadir una nueva es escribir una función `(consulta, lang) -> list[Evidencia]`
y registrarla — todas se consultan en paralelo.

Familias actuales (todas con APIs libres, sin llaves):
- Wikipedia en el idioma de la afirmación, con ranking léxico de pasajes.
- Wikipedia multilingüe: el mismo artículo en otros idiomas vía enlaces
  interlingüísticos — sin modelo de traducción; cada edición es una comunidad
  editorial distinta (una voz independiente más).
- Wikinews: periodismo colaborativo, mismo API de MediaWiki.
- Web abierta (DuckDuckGo): miles de dominios vía snippets.
- Académicas: Semantic Scholar, OpenAlex, arXiv y Europe PMC — resúmenes de
  papers para afirmaciones científicas (corpus mayormente en inglés).

La independencia de fuentes se aproxima por dominio: cien páginas del mismo
dominio cuentan como una voz en el agregador.

Este módulo es ingeniería pura: cero parámetros de modelo.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

from .models import Evidencia, HechoAtomico

_UA = {"User-Agent": "AIDAM/0.1 (verificador abierto; https://github.com/DeliVali/AIDAM)"}
_TIMEOUT = 15
_MAX_CHARS_PASAJE = 600

# Wikipedias grandes y diversas geográficamente, en orden de preferencia
# cuando hay que elegir un subconjunto de los idiomas disponibles.
IDIOMAS_PREFERIDOS = ["en", "es", "fr", "de", "ru", "zh", "pt", "it", "ja", "ar"]


# ───────────────────────── utilidades compartidas ─────────────────────────


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
    """Extrae pasajes de un artículo MediaWiki. Con `consulta` los ordena por
    relevancia léxica; sin ella (idiomas que no comparten vocabulario con la
    consulta) usa el orden del artículo, donde la introducción resume lo esencial."""
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
    """idioma → título del mismo artículo en las demás Wikipedias (langlinks)."""
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
    """Elige qué idiomas consultar: primero los preferidos, luego el resto
    en orden alfabético (determinista), sin repetir el idioma de origen."""
    preferidos = [l for l in IDIOMAS_PREFERIDOS if l != excluir and l in disponibles]
    resto = sorted(l for l in disponibles if l != excluir and l not in IDIOMAS_PREFERIDOS)
    return [(l, disponibles[l]) for l in (preferidos + resto)[:max_idiomas]]


def buscar_wikipedia(
    consulta: str, lang: str = "es", max_articulos: int = 2, max_pasajes: int = 4
) -> list[Evidencia]:
    """Busca artículos en la Wikipedia del idioma de la afirmación."""
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
    """Trae el mejor artículo en otros idiomas vía enlaces interlingüísticos.

    `max_idiomas=0` desactiva; un valor alto (p. ej. 300) consulta todas las
    ediciones donde exista el artículo, a costa de latencia.
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
    """Periodismo colaborativo de Wikinews (mismo API de MediaWiki)."""
    host = f"{lang}.wikinews.org"
    evidencias: list[Evidencia] = []
    for titulo in _buscar_titulos(consulta, host, max_articulos=2):
        evidencias.extend(
            _pasajes_de_articulo(host, titulo, 2, "wikinews", lang, consulta=consulta)
        )
    return evidencias[:max_pasajes]


# ───────────────────────── web abierta ─────────────────────────


def _texto_de_pagina(url: str) -> str:
    """Descarga una página y extrae su texto principal (sin menús ni anuncios).

    Los snippets truncados de un buscador repiten titulares; el veredicto de un
    artículo vive en su cuerpo. Medido en AVeriTeC: juzgar snippets era el
    cuello de botella del sistema.
    """
    try:
        import trafilatura

        r = requests.get(url, headers=_UA, timeout=8)
        r.raise_for_status()
        return trafilatura.extract(r.text) or ""
    except Exception:
        return ""


def _buscar_ddg(consulta: str, max_resultados: int) -> list[dict]:
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            return list(ddgs.text(consulta, max_results=max_resultados))
    except Exception:
        return []


def _evidencias_de_paginas(
    hits: list[dict],
    consulta: str,
    fuente: str,
    lang: str,
    max_paginas: int,
    max_pasajes_por_pagina: int = 3,
) -> list[Evidencia]:
    """Texto completo de los mejores resultados, en paralelo, con ranking léxico."""
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
    """Busca en la web (DuckDuckGo): texto completo de los mejores resultados,
    snippets del resto."""
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


def buscar_desmentidos(consulta: str, lang: str = "es") -> list[Evidencia]:
    """Búsqueda dirigida a verificaciones: trae a los fact-checkers a la mesa.

    Medido en AVeriTeC: en la mayoría de las mentiras que pasaban como
    sustentadas, el fact-checker ni aparecía en la evidencia. Esta consulta
    reformulada lo busca explícitamente, y lee el artículo completo (el
    veredicto no cabe en un snippet).
    """
    sufijo = "fact check" if lang == "en" else "verificación bulo fact check"
    hits = _buscar_ddg(f"{consulta} {sufijo}", max_resultados=5)
    return _evidencias_de_paginas(hits, consulta, "desmentidos", lang, max_paginas=3)


# ───────────────────────── técnicas / programación ─────────────────────────


def buscar_stackexchange(consulta: str, lang: str = "", max_resultados: int = 4) -> list[Evidencia]:
    """Preguntas y respuestas de Stack Overflow (API libre, sin llave).

    Para afirmaciones de programación: nadie va a Wikipedia por un bug.
    """
    datos = _get_json(
        "https://api.stackexchange.com/2.3/search/excerpts",
        {
            "order": "desc",
            "sort": "relevance",
            "q": consulta,
            "site": "stackoverflow",
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
                url=f"https://stackoverflow.com/q/{qid}",
                titulo=item.get("title", ""),
                dominio="stackoverflow.com",
                fuente="stackexchange",
                idioma="en",
            )
        )
    return evidencias


# ───────────────────────── fuentes académicas ─────────────────────────


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
    """Resúmenes de papers vía Semantic Scholar (API libre, sin llave)."""
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
    """OpenAlex publica los resúmenes como índice invertido palabra→posiciones;
    lo reconstruimos ordenando las posiciones."""
    posiciones: list[tuple[int, str]] = []
    for palabra, sitios in indice_invertido.items():
        posiciones.extend((sitio, palabra) for sitio in sitios)
    return " ".join(palabra for _, palabra in sorted(posiciones))


def buscar_openalex(consulta: str, lang: str = "", max_papers: int = 4) -> list[Evidencia]:
    """Resúmenes de papers vía OpenAlex (API libre, sin llave)."""
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
    """Resúmenes de preprints de arXiv (API libre, sin llave)."""
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


def buscar_europepmc(consulta: str, lang: str = "", max_papers: int = 4) -> list[Evidencia]:
    """Resúmenes biomédicos de Europe PMC (API libre, sin llave)."""
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


# ───────────────────────── registro y orquestación ─────────────────────────

# nombre → (descripción, categorías que atiende o None = universal,
#           función (consulta, lang, max_idiomas) -> list[Evidencia]).
# Para añadir una fuente: escribe una función con esa firma y regístrala aquí.
# Las categorías vienen del router (aidam/router.py): el agente no va a
# Wikipedia por un bug ni a Stack Overflow por una afirmación médica.
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
    "stackexchange": (
        "Preguntas y respuestas de Stack Overflow",
        {"programacion"},
        lambda c, lang, mi: buscar_stackexchange(c),
    ),
    # Universales: un misroute del router debe AÑADIR ruido, nunca QUITAR señal
    # (medido: una afirmación médica enrutada a "general" perdía sus papers).
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
        {"ciencia", "programacion"},
        lambda c, lang, mi: buscar_arxiv(c, lang=lang),
    ),
    "europepmc": (
        "Literatura biomédica de Europe PMC",
        {"medicina", "ciencia"},
        lambda c, lang, mi: buscar_europepmc(c, lang=lang),
    ),
}


def _es_probatoria(hecho_texto: str, evidencia: Evidencia, lang: str) -> bool:
    """¿El pasaje habla de lo que afirma el hecho, o solo del tema en general?

    Un pasaje en el idioma de la afirmación que comparte <2 de sus palabras de
    contenido no puede probar ni refutar nada específico (medido: las
    introducciones genéricas de Wikipedia se juzgaban como contradicción).
    La evidencia en otros idiomas queda exenta — el solape léxico no significa
    nada entre idiomas; su ranking cruzado llegará con embeddings multilingües.
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
    """Consulta en paralelo las fuentes relevantes a la categoría y deduplica.

    Sin categoría se consultan todas. Cada fuente falla en silencio (devuelve
    lista vacía): la caída de un API externo nunca tumba la verificación,
    solo reduce la evidencia disponible.
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

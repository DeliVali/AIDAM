"""Tests for the retriever's pure logic (no network)."""

from aidam.retrieve import (
    FUENTES,
    IDIOMAS_PREFERIDOS,
    _priorizar_idiomas,
    _reconstruir_resumen_openalex,
    _trocear,
)


def test_prioriza_idiomas_preferidos_primero():
    disponibles = {"zh": "长城", "eo": "Ĉina murego", "en": "Great Wall", "fr": "Grande Muraille"}
    elegidos = _priorizar_idiomas(disponibles, excluir="es", max_idiomas=3)
    assert [idioma for idioma, _ in elegidos] == ["en", "fr", "zh"]


def test_excluye_el_idioma_de_origen():
    disponibles = {"es": "Gran Muralla", "en": "Great Wall"}
    elegidos = _priorizar_idiomas(disponibles, excluir="es", max_idiomas=5)
    assert [idioma for idioma, _ in elegidos] == ["en"]


def test_resto_de_idiomas_en_orden_estable():
    disponibles = {"eo": "x", "ca": "x", "nl": "x"}  # none of them preferred
    elegidos = _priorizar_idiomas(disponibles, excluir="es", max_idiomas=2)
    assert [idioma for idioma, _ in elegidos] == ["ca", "eo"]  # alphabetical, deterministic


def test_max_idiomas_cero_no_elige_nada():
    assert _priorizar_idiomas({"en": "x"}, excluir="es", max_idiomas=0) == []


def test_devuelve_el_titulo_traducido():
    disponibles = {"en": "Great Wall of China"}
    assert _priorizar_idiomas(disponibles, excluir="es", max_idiomas=1) == [
        ("en", "Great Wall of China")
    ]


def test_preferidos_cubren_alfabetos_diversos():
    # Design guard: the preferred list must include non-Latin scripts
    assert {"zh", "ru", "ar", "ja"} <= set(IDIOMAS_PREFERIDOS)


def test_trocear_respeta_frases():
    texto = "Primera frase. " * 30
    pasajes = _trocear(texto, max_chars=100)
    assert all(len(p) <= 115 for p in pasajes)  # margin for the last sentence
    assert all(p.endswith(".") for p in pasajes)


def test_gate_probatorio_descarta_intro_generica():
    """Regression measured in /verify: the generic intro of the Python
    article (which doesn't mention lists) was judged as contradicting the fact."""
    from aidam.models import Evidencia
    from aidam.retrieve import _es_probatoria

    intro = Evidencia(
        texto="Python is a high-level, general-purpose programming language that "
        "emphasizes code readability and simplicity",
        url="https://en.wikipedia.org/wiki/Python",
        titulo="Python",
        dominio="en.wikipedia.org",
        fuente="wikipedia",
        idioma="en",
    )
    assert not _es_probatoria("Python lists are mutable", intro, lang="en")

    especifica = Evidencia(
        texto="Lists in Python are mutable sequences: elements can be changed in place",
        url="https://en.wikipedia.org/wiki/Python",
        titulo="Python",
        dominio="en.wikipedia.org",
        fuente="wikipedia",
        idioma="en",
    )
    assert _es_probatoria("Python lists are mutable", especifica, lang="en")


def test_gate_probatorio_exime_otros_idiomas():
    """Lexical overlap means nothing across languages: cross-language
    evidence is not filtered (its ranking will come with multilingual embeddings)."""
    from aidam.models import Evidencia
    from aidam.retrieve import _es_probatoria

    zh = Evidencia(
        texto="富士山是日本最高的山峰",
        url="https://zh.wikipedia.org/wiki/富士山",
        titulo="富士山",
        dominio="zh.wikipedia.org",
        fuente="wikipedia",
        idioma="zh",
    )
    assert _es_probatoria("El Monte Fuji es la montaña más alta de Japón", zh, lang="es")


def test_reconstruir_resumen_openalex():
    indice = {"hierve": [1], "El": [0], "a": [2], "100": [3], "grados.": [4]}
    assert _reconstruir_resumen_openalex(indice) == "El hierve a 100 grados."


def test_reconstruir_resumen_con_palabra_repetida():
    indice = {"la": [0, 2], "de": [1], "casa": [3]}
    assert _reconstruir_resumen_openalex(indice) == "la de la casa"


def test_registro_de_fuentes_completo():
    """Design guard: the promised source families are registered and described."""
    assert {
        "wikipedia",
        "wikipedia-multilingue",
        "wikinews",
        "wikiquote",
        "web",
        "desmentidos",
        "gdelt",
        "stackexchange",
        "stackexchange-matematicas",
        "semantic-scholar",
        "openalex",
        "arxiv",
        "crossref",
        "europepmc",
    } <= set(FUENTES)
    from aidam.router import CATEGORIAS

    for nombre, (descripcion, categorias, funcion) in FUENTES.items():
        assert descripcion, f"source without description: {nombre}"
        assert callable(funcion), f"source without function: {nombre}"
        if categorias is not None:
            assert categorias <= set(CATEGORIAS), f"unknown category in {nombre}"


def test_categorias_enrutan_fuentes():
    """Programming reaches Stack Overflow; medicine doesn't; universals always."""
    def activas(categoria):
        return {
            nombre
            for nombre, (_d, cats, _f) in FUENTES.items()
            if cats is None or categoria in cats
        }

    assert "stackexchange" in activas("programacion")
    assert "stackexchange" not in activas("medicina")
    assert "europepmc" in activas("medicina")
    assert {"wikipedia", "web", "desmentidos"} <= activas("general")
    assert "docs-programacion" in activas("programacion")
    assert "docs-matematicas" in activas("matematicas")
    assert "docs-programacion" not in activas("general")
    assert "stackexchange-matematicas" in activas("matematicas")
    assert "stackexchange-matematicas" not in activas("programacion")
    assert "gdelt" in activas("actualidad")
    assert "gdelt" not in activas("medicina")
    assert "wikiquote" in activas("general")
    assert "crossref" in activas("ciencia")


def test_docs_oficiales_pesan_como_verificador():
    """Official documentation is the fact-checker of technical matters."""
    from aidam.aggregate import PESO_DOCS_OFICIALES, PESO_VERIFICADOR, peso_fuente
    from aidam.models import Evidencia

    doc = Evidencia(
        texto="aws s3 cp copies files to a bucket",
        url="https://docs.aws.amazon.com/cli/s3.html",
        titulo="AWS CLI",
        dominio="docs.aws.amazon.com",
        fuente="docs-oficiales",
        idioma="en",
    )
    assert peso_fuente(doc) == PESO_DOCS_OFICIALES == PESO_VERIFICADOR


def test_cache_de_busquedas_ida_y_vuelta(tmp_path, monkeypatch):
    """The search cache returns exactly what was stored, and respects TTL."""
    from aidam import retrieve

    monkeypatch.setattr(retrieve, "_RUTA_CACHE", tmp_path / "cache.sqlite")
    hits = [{"href": "https://x.org/a", "title": "A", "body": "b" * 50}]
    retrieve._cache_guardar("consulta|8", hits)
    assert retrieve._cache_leer("consulta|8") == hits
    assert retrieve._cache_leer("otra|8") is None
    monkeypatch.setattr(retrieve, "_TTL_CACHE", -1.0)  # everything expired
    assert retrieve._cache_leer("consulta|8") is None


def test_enfriamiento_de_motores(monkeypatch):
    """Three consecutive failures rest an engine; one success resets the count."""
    from aidam import retrieve

    monkeypatch.setattr(retrieve, "_fallos_seguidos", {})
    monkeypatch.setattr(retrieve, "_enfriado_hasta", {})
    retrieve._registrar_resultado("bing", exito=False)
    retrieve._registrar_resultado("bing", exito=False)
    assert retrieve._backend_disponible("bing")  # two failures: still in play
    retrieve._registrar_resultado("bing", exito=True)  # success resets
    retrieve._registrar_resultado("bing", exito=False)
    retrieve._registrar_resultado("bing", exito=False)
    retrieve._registrar_resultado("bing", exito=False)
    assert not retrieve._backend_disponible("bing")  # third in a row: cooling

def test_wikiquote_pesa_como_enciclopedia():
    from aidam.aggregate import PESO_ENCICLOPEDIA, peso_fuente
    from aidam.models import Evidencia

    cita = Evidencia(
        texto="The misattributed section lists this quote as unsourced",
        url="https://en.wikiquote.org/wiki/Albert_Einstein",
        titulo="Albert Einstein",
        dominio="en.wikiquote.org",
        fuente="wikiquote",
        idioma="en",
    )
    assert peso_fuente(cita) == PESO_ENCICLOPEDIA

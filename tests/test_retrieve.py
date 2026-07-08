"""Tests de la lógica pura del recuperador (sin red)."""

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
    disponibles = {"eo": "x", "ca": "x", "nl": "x"}  # ninguno preferido
    elegidos = _priorizar_idiomas(disponibles, excluir="es", max_idiomas=2)
    assert [idioma for idioma, _ in elegidos] == ["ca", "eo"]  # alfabético, determinista


def test_max_idiomas_cero_no_elige_nada():
    assert _priorizar_idiomas({"en": "x"}, excluir="es", max_idiomas=0) == []


def test_devuelve_el_titulo_traducido():
    disponibles = {"en": "Great Wall of China"}
    assert _priorizar_idiomas(disponibles, excluir="es", max_idiomas=1) == [
        ("en", "Great Wall of China")
    ]


def test_preferidos_cubren_alfabetos_diversos():
    # Guardia del diseño: la lista preferida debe incluir escrituras no latinas
    assert {"zh", "ru", "ar", "ja"} <= set(IDIOMAS_PREFERIDOS)


def test_trocear_respeta_frases():
    texto = "Primera frase. " * 30
    pasajes = _trocear(texto, max_chars=100)
    assert all(len(p) <= 115 for p in pasajes)  # margen por la última frase
    assert all(p.endswith(".") for p in pasajes)


def test_gate_probatorio_descarta_intro_generica():
    """Regresión medida en /verify: la intro genérica del artículo de Python
    (que no menciona listas) se juzgaba como contradicción del hecho."""
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
    """El solape léxico no significa nada entre idiomas: la evidencia
    cruzada no se filtra (su ranking llegará con embeddings multilingües)."""
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
    """Guardia del diseño: las familias prometidas están registradas y descritas."""
    assert {
        "wikipedia",
        "wikipedia-multilingue",
        "wikinews",
        "web",
        "desmentidos",
        "stackexchange",
        "semantic-scholar",
        "openalex",
        "arxiv",
        "europepmc",
    } <= set(FUENTES)
    from aidam.router import CATEGORIAS

    for nombre, (descripcion, categorias, funcion) in FUENTES.items():
        assert descripcion, f"fuente sin descripción: {nombre}"
        assert callable(funcion), f"fuente sin función: {nombre}"
        if categorias is not None:
            assert categorias <= set(CATEGORIAS), f"categoría desconocida en {nombre}"


def test_categorias_enrutan_fuentes():
    """Programación llega a Stack Overflow; medicina no; universales siempre."""
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


def test_docs_oficiales_pesan_como_verificador():
    """La documentación oficial es el fact-checker de lo técnico."""
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

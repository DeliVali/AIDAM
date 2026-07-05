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
        "semantic-scholar",
        "openalex",
        "arxiv",
        "europepmc",
    } <= set(FUENTES)
    for nombre, (descripcion, funcion) in FUENTES.items():
        assert descripcion, f"fuente sin descripción: {nombre}"
        assert callable(funcion), f"fuente sin función: {nombre}"

"""Tests del descompositor heurístico."""

from aidam.decompose import descomponer


def test_frase_simple_es_un_hecho():
    hechos = descomponer("La Torre Eiffel está en París.")
    assert len(hechos) == 1
    assert hechos[0].texto == "La Torre Eiffel está en París"


def test_varias_frases_varios_hechos():
    hechos = descomponer("El agua hierve a 100 °C a nivel del mar. El sol es una estrella.")
    assert [h.texto for h in hechos] == [
        "El agua hierve a 100 °C a nivel del mar",
        "El sol es una estrella",
    ]


def test_preguntas_se_descartan():
    hechos = descomponer("¿Cuánto mide la Torre Eiffel? La Torre Eiffel mide 330 metros.")
    assert [h.texto for h in hechos] == ["La Torre Eiffel mide 330 metros"]


def test_opiniones_se_descartan():
    hechos = descomponer("Creo que lloverá mañana. París es la capital de Francia.")
    assert [h.texto for h in hechos] == ["París es la capital de Francia"]


def test_nunca_devuelve_vacio():
    hechos = descomponer("¿Todo esto es una pregunta?")
    assert len(hechos) == 1  # devuelve la afirmación completa como último recurso


def test_origen_se_conserva():
    texto = "El sol es una estrella. La luna es un satélite."
    for hecho in descomponer(texto):
        assert hecho.origen == texto

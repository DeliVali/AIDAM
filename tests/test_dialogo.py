"""Dialogue-act routing and input-language detection.

Both born from measured screenshot failures (2026-07-17): «tienes un
ejemplo de codigo» was verified as a claim (SUSTENTADO 100% against an
OOP tutorial) instead of inheriting the code topic from the previous
turn, and answers ignored the language the user typed in. No network,
no models: the embedding path is stubbed out so only the deterministic
floor is under test.
"""

from aidam.agente.contexto import (
    ContextoConversacion,
    es_seguimiento,
    resolver_seguimiento,
)
from aidam.agente.idioma import detectar_idioma
from aidam.agente.sintesis import _FRASES, es_pregunta


# -- input-language detection ---------------------------------------------------

def test_detecta_aleman():
    assert detectar_idioma("Der Eiffelturm steht in Paris") == "de"


def test_detecta_ingles():
    assert detectar_idioma("The Eiffel Tower is located in Paris") == "en"


def test_detecta_espanol():
    assert detectar_idioma("La muralla china no es visible desde el espacio") == "es"


def test_corto_o_ambiguo_cae_al_idioma_pedido():
    assert detectar_idioma("hola") == "es"
    assert detectar_idioma("ok entonces", por_defecto="en") == "en"


def test_tabla_de_frases_completa_en_todos_los_idiomas():
    claves = set(_FRASES["es"])
    for lang, tabla in _FRASES.items():
        assert set(tabla) == claves, f"idioma {lang} incompleto"


# -- requests to the agent are questions, never claims --------------------------

def test_peticion_sin_signo_es_pregunta():
    assert es_pregunta("tienes un ejemplo de codigo")
    assert es_pregunta("dame un ejemplo en python")
    assert es_pregunta("can you show me an example")


def test_afirmacion_sigue_siendo_afirmacion():
    assert not es_pregunta("El muro de Berlín cayó en 1989.")
    assert not es_pregunta("WHO approved the malaria vaccine in 2021")


# -- elliptical requests are follow-ups -----------------------------------------

def test_peticion_eliptica_es_seguimiento():
    assert es_seguimiento("tienes un ejemplo de codigo")
    assert es_seguimiento("muéstrame el código")
    assert es_seguimiento("dame otro ejemplo")


def test_peticion_con_tema_propio_es_autonoma():
    assert not es_seguimiento("dame la capital de Francia")
    assert not es_seguimiento("puedes verificar la altura del Everest")


def test_reescrito_de_peticion_cierra_como_pregunta():
    resuelta = resolver_seguimiento(
        "tienes un ejemplo de codigo", "iterar un array en python"
    )
    assert resuelta.endswith("?")


# -- the screenshot scenario, end to end at routing level -----------------------

def _sin_embedder(monkeypatch):
    monkeypatch.setattr(
        ContextoConversacion, "_codificar",
        lambda self, textos: (_ for _ in ()).throw(RuntimeError("sin modelo")),
    )


def test_ejemplo_de_codigo_hereda_el_tema_anterior(monkeypatch):
    _sin_embedder(monkeypatch)
    contexto = ContextoConversacion()
    contexto.agregar("iterar un array, en el contexto de codigo")
    resuelta = contexto.resolver("tienes un ejemplo de codigo")
    assert "iterar" in resuelta and "array" in resuelta
    assert resuelta.endswith("?")
    assert es_pregunta(resuelta)

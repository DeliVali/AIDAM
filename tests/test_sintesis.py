"""Synthesis: the LLM narrates the table and may never contradict verdicts."""

from __future__ import annotations

from aidam.agente.sintesis import sintetizar, tabla_evidencia
from aidam.models import (
    EtiquetaPar,
    Evidencia,
    HechoAtomico,
    Informe,
    Veredicto,
    VeredictoHecho,
    VeredictoPar,
)


def _informe(veredicto=Veredicto.SUSTENTADO):
    hecho = HechoAtomico("la torre está en París", "test")
    par = VeredictoPar(
        hecho,
        Evidencia("la torre se alza en París", "https://a.org/x", "t", "a.org", "wikipedia"),
        EtiquetaPar.SUSTENTA,
        0.9,
    )
    vh = VeredictoHecho(hecho, veredicto, 0.9, a_favor=[par])
    return Informe("la torre está en París", veredicto, 0.9, [vh])


class _Generador:
    def __init__(self, respuesta):
        self.respuesta = respuesta

    def completar(self, prompt, max_tokens, temperature, stop=None):
        self.prompt = prompt
        return self.respuesta


def test_tabla_contiene_hechos_urls_y_veredictos():
    tabla = tabla_evidencia(_informe())
    assert "la torre está en París" in tabla
    assert "https://a.org/x" in tabla
    assert "SUPPORTED" in tabla


def test_sin_generador_devuelve_none():
    assert sintetizar(_informe(), None) is None


def test_limpia_bloque_de_pensamiento():
    generador = _Generador("<think>elucubración larga</think>La afirmación está sustentada.")
    assert sintetizar(_informe(), generador) == "La afirmación está sustentada."


def test_salvaguarda_anti_contradiccion():
    # The verdict is SUPPORTED; a synthesis calling it refuted must be dropped.
    generador = _Generador("La afirmación fue refutada por la evidencia.")
    assert sintetizar(_informe(Veredicto.SUSTENTADO), generador) is None
    generador = _Generador("La afirmación es cierta y está sustentada.")
    assert sintetizar(_informe(Veredicto.REFUTADO), generador) is None


def test_respuesta_vacia_o_error_devuelve_none():
    assert sintetizar(_informe(), _Generador("")) is None

    class _Roto:
        def completar(self, *a, **kw):
            raise RuntimeError("worker muerto")

    assert sintetizar(_informe(), _Roto()) is None


def test_el_generador_solo_ve_la_tabla():
    generador = _Generador("Resumen correcto.")
    sintetizar(_informe(), generador)
    assert "CLAIM:" in generador.prompt and "VERDICT:" in generador.prompt

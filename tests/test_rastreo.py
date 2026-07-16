"""Crawler module: capability probe, degradation, and pure chunking."""

from __future__ import annotations

import pytest

from aidam.agente import rastreo


def test_probe_devuelve_bool_sin_lanzar():
    assert isinstance(rastreo.hay_rastreador(), bool)


@pytest.mark.skipif(rastreo.hay_rastreador(), reason="crawl4ai instalado: no aplica")
def test_rastrear_sin_dependencia_lanza_con_instruccion():
    with pytest.raises(RuntimeError, match=r"aidam\[rastreo\]"):
        rastreo.rastrear("https://example.org")


def test_trocear_respeta_parrafos_y_descarta_migas():
    parrafo_a = "palabra " * 90   # ~700 chars
    parrafo_b = "otra " * 90
    texto = f"{parrafo_a}\n\n{parrafo_b}\n\nok"
    trozos = rastreo._trocear(texto)
    assert len(trozos) == 2                      # "ok" (crumb) dropped
    assert all(len(t) >= 40 for t in trozos)
    assert "\n" not in trozos[0]                 # whitespace normalized per paragraph

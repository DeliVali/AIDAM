"""Voice module: capability probes and graceful degradation without the extra."""

from __future__ import annotations

import pytest

from aidam.agente import voz


def test_probes_devuelven_bool_sin_lanzar():
    assert isinstance(voz.hay_voz(), bool)
    assert isinstance(voz.hay_tts(), bool)


@pytest.mark.skipif(voz.hay_voz(), reason="faster-whisper instalado: no aplica la degradación")
def test_transcribir_sin_dependencia_lanza_con_instruccion(tmp_path):
    with pytest.raises(RuntimeError, match=r"aidam\[voz\]"):
        voz.transcribir(tmp_path / "audio.wav")


@pytest.mark.skipif(voz._hay_escucha(), reason="RealtimeSTT instalado: no aplica la degradación")
def test_escuchar_sin_dependencia_lanza_con_instruccion():
    with pytest.raises(RuntimeError, match=r"aidam\[voz\]"):
        voz.escuchar_una_vez()


def test_hablar_sin_tts_es_noop():
    # Missing OUTPUT capability degrades silently (the text is on screen).
    voz.hablar("hola")  # must not raise, installed or not

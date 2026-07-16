"""Vision module: capability probes, degradation, and provenance honesty."""

from __future__ import annotations

import shutil

import pytest

from aidam.agente import vision


def test_probe_devuelve_bool_sin_lanzar():
    assert isinstance(vision.hay_ocr(), bool)


@pytest.mark.skipif(vision.hay_ocr(), reason="OCR instalado: no aplica la degradación")
def test_extraer_texto_sin_ocr_lanza_con_instruccion(tmp_path):
    with pytest.raises(RuntimeError, match=r"aidam\[imagen\]"):
        vision.extraer_texto(tmp_path / "img.png")


def test_procedencia_sin_c2patool_devuelve_none(tmp_path, monkeypatch):
    # Absence of the tool (like absence of a manifest) is None — NEVER "fake".
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    assert vision.procedencia(tmp_path / "img.png") is None

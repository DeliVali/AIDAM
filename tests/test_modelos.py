"""Tests of first-run model acquisition (no network: only the decision logic)."""

from __future__ import annotations

import importlib.util

from aidam import modelos


def test_base_respeta_variable_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDAM_MODELOS", str(tmp_path))
    assert modelos._base_modelos() == tmp_path


def test_modelo_presente_no_descarga(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDAM_MODELOS", str(tmp_path))
    (tmp_path / "verificador-onnx-mini").mkdir()
    (tmp_path / "verificador-onnx-mini" / "config.json").write_text("{}")

    llamadas = []
    assert modelos.asegurar_verificador(progreso=llamadas.append) is True
    assert llamadas == []  # ni un mensaje: no hizo falta descargar


def test_con_torch_no_descarga(tmp_path, monkeypatch):
    if importlib.util.find_spec("torch") is None:
        import pytest

        pytest.skip("requiere torch instalado")
    monkeypatch.setenv("AIDAM_MODELOS", str(tmp_path))  # base vacía
    monkeypatch.delenv("AIDAM_BACKEND", raising=False)

    llamadas = []
    # Sin modelo ONNX pero con torch: el backend torch se resuelve solo.
    assert modelos.asegurar_verificador(progreso=llamadas.append) is True
    assert llamadas == []


def test_forzado_onnx_sin_modelo_ni_red_devuelve_false(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDAM_MODELOS", str(tmp_path))
    monkeypatch.setenv("AIDAM_BACKEND", "onnx-mini")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")  # bloquea la red del hub

    llamadas = []
    assert modelos.asegurar_verificador(progreso=llamadas.append) is False
    assert any("Descargando" in m for m in llamadas)
    assert any("No se pudo" in m for m in llamadas)
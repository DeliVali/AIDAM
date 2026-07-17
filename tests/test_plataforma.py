"""Tests of per-OS data locations (aidam/plataforma.py)."""

from __future__ import annotations

from pathlib import Path

from aidam import plataforma


def test_override_por_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDAM_DATOS", str(tmp_path))
    assert plataforma.directorio_datos() == tmp_path


def test_windows_usa_appdata(tmp_path, monkeypatch):
    monkeypatch.delenv("AIDAM_DATOS", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(plataforma.platform, "system", lambda: "Windows")
    assert plataforma.directorio_datos() == tmp_path / "aidam"


def test_macos_usa_application_support(monkeypatch):
    monkeypatch.delenv("AIDAM_DATOS", raising=False)
    monkeypatch.setattr(plataforma.platform, "system", lambda: "Darwin")
    esperado = Path("~/Library/Application Support").expanduser() / "aidam"
    assert plataforma.directorio_datos() == esperado


def test_linux_respeta_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("AIDAM_DATOS", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(plataforma.platform, "system", lambda: "Linux")
    assert plataforma.directorio_datos() == tmp_path / "aidam"


def test_carpeta_general_se_crea(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDAM_DATOS", str(tmp_path))
    carpeta = plataforma.carpeta_general()
    assert carpeta == tmp_path / "general"
    assert carpeta.is_dir()  # creada al pedirla: siempre existe

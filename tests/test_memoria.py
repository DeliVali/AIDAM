"""Tests of agent memory: schema migration, conversations and workspaces."""

from __future__ import annotations

import sqlite3

from aidam.memoria import MemoriaAgente
from aidam.models import Informe, Veredicto

_ESQUEMA_V0 = """
CREATE TABLE sesiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT NOT NULL
);
CREATE TABLE verificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sesion_id INTEGER REFERENCES sesiones(id),
    afirmacion TEXT NOT NULL,
    afirmacion_normal TEXT NOT NULL,
    veredicto TEXT NOT NULL,
    confianza REAL NOT NULL,
    fecha TEXT NOT NULL,
    informe_json TEXT NOT NULL
);
"""


def _informe(afirmacion: str) -> Informe:
    return Informe(afirmacion, Veredicto.SUSTENTADO, 0.9, [])


def test_migracion_v0_a_v1_conserva_datos(tmp_path):
    ruta = tmp_path / "memoria.db"
    vieja = sqlite3.connect(ruta)
    vieja.executescript(_ESQUEMA_V0)
    vieja.execute("INSERT INTO sesiones (inicio) VALUES ('2026-07-01T00:00:00')")
    vieja.execute(
        "INSERT INTO verificaciones (sesion_id, afirmacion, afirmacion_normal,"
        " veredicto, confianza, fecha, informe_json)"
        " VALUES (1, 'Vieja', 'vieja', 'refutado', 0.8, '2026-07-01T00:01:00', '{}')"
    )
    vieja.commit()
    vieja.close()

    memoria = MemoriaAgente(ruta)
    # columnas nuevas presentes, versión sellada, datos intactos en General ('')
    # y el backfill titula la conversación migrada con su primera afirmación
    version = memoria._db.execute("PRAGMA user_version").fetchone()[0]
    assert version == 1
    fila = memoria._db.execute(
        "SELECT carpeta, titulo FROM sesiones WHERE id = 1"
    ).fetchone()
    assert fila == ("", "Vieja")
    assert memoria.conversaciones("")[0]["turnos"] == 1
    memoria.cerrar()

    # reabrir una BD ya migrada no re-aplica nada
    memoria2 = MemoriaAgente(ruta)
    assert memoria2._db.execute("PRAGMA user_version").fetchone()[0] == 1
    memoria2.cerrar()


def test_sesion_perezosa_no_deja_filas_basura(tmp_path):
    memoria = MemoriaAgente(tmp_path / "m.db")
    assert memoria._db.execute("SELECT COUNT(*) FROM sesiones").fetchone()[0] == 0
    memoria.guardar(_informe("Algo"))  # primer uso la crea
    assert memoria._db.execute("SELECT COUNT(*) FROM sesiones").fetchone()[0] == 1
    memoria.cerrar()


def test_conversaciones_por_carpeta_y_titulo_automatico(tmp_path):
    memoria = MemoriaAgente(tmp_path / "m.db")
    general = memoria.nueva_sesion()
    proyecto = memoria.nueva_sesion(carpeta="/tmp/proyecto")

    memoria.guardar(_informe("Primera afirmación del hilo general"), sesion_id=general)
    memoria.guardar(_informe("Segunda del mismo hilo"), sesion_id=general)
    memoria.guardar(_informe("La del proyecto"), sesion_id=proyecto)

    del_general = memoria.conversaciones("")
    assert len(del_general) == 1
    assert del_general[0]["turnos"] == 2
    assert del_general[0]["titulo"] == "Primera afirmación del hilo general"

    del_proyecto = memoria.conversaciones("/tmp/proyecto")
    assert len(del_proyecto) == 1
    assert del_proyecto[0]["titulo"] == "La del proyecto"

    hilo = memoria.hilo(general)
    assert [t["afirmacion"] for t in hilo] == [
        "Primera afirmación del hilo general",
        "Segunda del mismo hilo",
    ]
    assert hilo[0]["informe"]["veredicto"] == "sustentado"

    carpetas = memoria.carpetas()
    assert len(carpetas) == 1  # General ('') es implícito, no se lista
    assert carpetas[0]["carpeta"] == "/tmp/proyecto"
    memoria.cerrar()


def test_conversacion_vacia_es_invisible(tmp_path):
    memoria = MemoriaAgente(tmp_path / "m.db")
    memoria.nueva_sesion()  # sin verificaciones: ruido, no historia
    assert memoria.conversaciones("") == []
    memoria.cerrar()

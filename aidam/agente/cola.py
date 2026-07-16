"""Resumable SQLite work queue (extends the house --reanudar pattern).

A single connection guarded by an internal lock makes every operation —
including the PENDIENTE→EN_CURSO claim in `tomar` — atomic across threads.
On disk it uses WAL so a crashed process leaves a consistent file; orphaned
in-progress tasks are recovered with `reanudar_huerfanas` on restart.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class EstadoTarea(str, Enum):
    """Lifecycle state of a task in the queue."""

    PENDIENTE = "pendiente"
    EN_CURSO = "en_curso"
    HECHA = "hecha"
    FALLIDA = "fallida"


@dataclass
class Tarea:
    """A unit of work stored in the queue."""

    id: int
    tipo: str
    carga: dict
    estado: EstadoTarea
    resultado: dict | None = None
    error: str | None = None


_ESQUEMA = """
CREATE TABLE IF NOT EXISTS tareas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    carga TEXT NOT NULL,
    estado TEXT NOT NULL,
    resultado TEXT,
    error TEXT,
    creada REAL NOT NULL,
    actualizada REAL NOT NULL
)
"""


class ColaTrabajo:
    """SQLite-backed work queue that survives process restarts."""

    def __init__(self, ruta: Path | str = ":memory:") -> None:
        self._ruta = str(ruta)
        self._candado = threading.Lock()
        self._conexion = sqlite3.connect(self._ruta, check_same_thread=False)
        with self._candado:
            if self._ruta != ":memory:":
                self._conexion.execute("PRAGMA journal_mode=WAL")
            self._conexion.execute(_ESQUEMA)
            self._conexion.commit()

    # ───────── ciclo de vida de tareas ─────────

    def encolar(self, tipo: str, carga: dict) -> int:
        """Adds a pending task and returns its id."""
        ahora = time.time()
        with self._candado:
            cursor = self._conexion.execute(
                "INSERT INTO tareas (tipo, carga, estado, creada, actualizada)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    tipo,
                    json.dumps(carga, ensure_ascii=False),
                    EstadoTarea.PENDIENTE.value,
                    ahora,
                    ahora,
                ),
            )
            self._conexion.commit()
            return int(cursor.lastrowid)

    def tomar(self, tipo: str | None = None) -> Tarea | None:
        """Atomically claims the oldest pending task (PENDIENTE→EN_CURSO).

        The SELECT and the UPDATE run under the internal lock, so two
        threads can never claim the same task. Returns None when there is
        nothing pending (of the given type, if any).
        """
        with self._candado:
            consulta = "SELECT id, tipo, carga FROM tareas WHERE estado = ?"
            parametros: list[str] = [EstadoTarea.PENDIENTE.value]
            if tipo is not None:
                consulta += " AND tipo = ?"
                parametros.append(tipo)
            consulta += " ORDER BY id LIMIT 1"
            fila = self._conexion.execute(consulta, parametros).fetchone()
            if fila is None:
                return None
            id_tarea, tipo_tarea, carga = fila
            self._conexion.execute(
                "UPDATE tareas SET estado = ?, actualizada = ? WHERE id = ?",
                (EstadoTarea.EN_CURSO.value, time.time(), id_tarea),
            )
            self._conexion.commit()
            return Tarea(
                id=int(id_tarea),
                tipo=tipo_tarea,
                carga=json.loads(carga),
                estado=EstadoTarea.EN_CURSO,
            )

    def completar(self, id_tarea: int, resultado: dict) -> None:
        """Marks a task as done, storing its result."""
        self._rematar(
            id_tarea,
            EstadoTarea.HECHA,
            resultado=json.dumps(resultado, ensure_ascii=False),
        )

    def fallar(self, id_tarea: int, error: str) -> None:
        """Marks a task as failed, storing the error message."""
        self._rematar(id_tarea, EstadoTarea.FALLIDA, error=error)

    def _rematar(
        self,
        id_tarea: int,
        estado: EstadoTarea,
        resultado: str | None = None,
        error: str | None = None,
    ) -> None:
        """Moves a task to a terminal state."""
        with self._candado:
            self._conexion.execute(
                "UPDATE tareas SET estado = ?, resultado = ?, error = ?, actualizada = ?"
                " WHERE id = ?",
                (estado.value, resultado, error, time.time(), id_tarea),
            )
            self._conexion.commit()

    # ───────── inspección y recuperación ─────────

    def pendientes(self, tipo: str | None = None) -> int:
        """Counts pending tasks, optionally filtered by type."""
        with self._candado:
            consulta = "SELECT COUNT(*) FROM tareas WHERE estado = ?"
            parametros: list[str] = [EstadoTarea.PENDIENTE.value]
            if tipo is not None:
                consulta += " AND tipo = ?"
                parametros.append(tipo)
            (cuantas,) = self._conexion.execute(consulta, parametros).fetchone()
            return int(cuantas)

    def reanudar_huerfanas(self) -> int:
        """Requeues tasks left EN_CURSO by a dead process; returns how many."""
        with self._candado:
            cursor = self._conexion.execute(
                "UPDATE tareas SET estado = ?, actualizada = ? WHERE estado = ?",
                (EstadoTarea.PENDIENTE.value, time.time(), EstadoTarea.EN_CURSO.value),
            )
            self._conexion.commit()
            return int(cursor.rowcount)

    def cerrar(self) -> None:
        """Closes the underlying connection. Safe to call more than once."""
        with self._candado:
            self._conexion.close()

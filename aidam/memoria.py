"""Agent memory: sessions and verification history, model-independent.

Jeffrey's design request (2026-07-13): the agent should keep its context
and sessions in open-source storage that lives with the agent, not with
the model. SQLite over a database server on purpose — it is a single
file, ships with Python, needs no daemon or Docker, and therefore runs
on every machine AIDAM targets (the accessibility principle). If the
project ever outgrows it, the schema is one table away from Postgres.

Honesty boundary, stated where the code lives: a remembered verdict is
CONTEXT, never a substitute for re-verification — facts change and
evidence rots. `buscar()` returns past reports with their dates so the
caller can say "already verified on <date>: <verdict>"; it must not be
used to skip the pipeline silently.

Everything is stored as the JSON of the dataclasses in models.py, so the
memory survives model swaps (it records what was concluded and from
which evidence, not how the model computed it).
"""

from __future__ import annotations

import json
import os
import sqlite3
import unicodedata
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import Informe

def ruta_defecto() -> Path:
    """Read AIDAM_MEMORIA at call time, not import time — frozen-at-import
    made test isolation impossible (the env override arrived too late) and
    would ignore any runtime reconfiguration."""
    return Path(os.environ.get("AIDAM_MEMORIA", "~/.aidam/memoria.db"))


# Backwards-compatible alias for existing imports; prefer ruta_defecto().
RUTA_DEFECTO = ruta_defecto()

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS sesiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT NOT NULL,
    carpeta TEXT NOT NULL DEFAULT '',
    titulo TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS verificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sesion_id INTEGER REFERENCES sesiones(id),
    afirmacion TEXT NOT NULL,
    afirmacion_normal TEXT NOT NULL,
    veredicto TEXT NOT NULL,
    confianza REAL NOT NULL,
    fecha TEXT NOT NULL,
    informe_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verif_normal
    ON verificaciones(afirmacion_normal);
"""

# Schema history (PRAGMA user_version):
#   0 → 1: sesiones gains carpeta ('' = the General workspace) and titulo —
#          a session becomes a CONVERSATION in a workspace. Existing rows
#          land in General, so prior history stays visible.
_VERSION_ESQUEMA = 1

_MIGRACIONES = {
    1: [
        "ALTER TABLE sesiones ADD COLUMN carpeta TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sesiones ADD COLUMN titulo TEXT NOT NULL DEFAULT ''",
    ],
}


def _normalizar(texto: str) -> str:
    """Case/accent/whitespace-insensitive key for lookups."""
    plano = unicodedata.normalize("NFKD", texto.casefold())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return " ".join(plano.split())


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoriaAgente:
    """Session + verification store shared by CLI and pipeline."""

    def __init__(self, ruta: Path | str | None = None) -> None:
        self.ruta = Path(ruta or ruta_defecto()).expanduser()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.ruta)
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if self._tabla_existe("sesiones"):
            # Existing database: walk pending migrations (fresh ones skip
            # this — executescript below already creates the current shape).
            for destino in range(version + 1, _VERSION_ESQUEMA + 1):
                for sentencia in _MIGRACIONES.get(destino, []):
                    self._db.execute(sentencia)
        self._db.executescript(_ESQUEMA)
        self._db.execute(f"PRAGMA user_version = {_VERSION_ESQUEMA}")
        # Idempotent backfill: conversations from before titles existed get
        # named by their first claim (cheap; touches only untitled rows).
        self._db.execute(
            "UPDATE sesiones SET titulo = COALESCE((SELECT v.afirmacion"
            " FROM verificaciones v WHERE v.sesion_id = sesiones.id"
            " ORDER BY v.fecha, v.id LIMIT 1), '') WHERE titulo = ''"
        )
        self._db.commit()
        self._sesion_id: int | None = None  # lazy: no junk rows per startup

    def _tabla_existe(self, nombre: str) -> bool:
        return (
            self._db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (nombre,),
            ).fetchone()
            is not None
        )

    @property
    def sesion_id(self) -> int:
        """The instance's own conversation, created on first use (the CLI's
        one-shot flow); the server manages explicit ids via nueva_sesion()."""
        if self._sesion_id is None:
            self._sesion_id = self.nueva_sesion()
        return self._sesion_id

    def nueva_sesion(self, carpeta: str = "", titulo: str = "") -> int:
        """New conversation in a workspace ('' = General). Returns its id."""
        id_nueva = self._db.execute(
            "INSERT INTO sesiones (inicio, carpeta, titulo) VALUES (?, ?, ?)",
            (_ahora(), carpeta, titulo),
        ).lastrowid
        self._db.commit()
        return id_nueva

    def guardar(self, informe: Informe, sesion_id: int | None = None) -> None:
        destino = sesion_id if sesion_id is not None else self.sesion_id
        fecha = _ahora()
        self._db.execute(
            "INSERT INTO verificaciones (sesion_id, afirmacion,"
            " afirmacion_normal, veredicto, confianza, fecha, informe_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                destino,
                informe.afirmacion,
                _normalizar(informe.afirmacion),
                informe.veredicto.value,
                informe.confianza,
                fecha,
                json.dumps(asdict(informe), ensure_ascii=False, default=str),
            ),
        )
        # A conversation is titled by its first claim.
        self._db.execute(
            "UPDATE sesiones SET titulo = ? WHERE id = ? AND titulo = ''",
            (informe.afirmacion[:80], destino),
        )
        self._db.commit()
        self._indexar_evidencia(informe, fecha)

    def _indexar_evidencia(self, informe: Informe, fecha: str) -> None:
        """Phase 2: every passage embedded once, searchable by meaning.

        Best effort on purpose: the semantic index needs the embedder
        (transformers+torch); when unavailable, plain memory still works.
        """
        try:
            from .vectores import IndiceEvidencia

            indice = IndiceEvidencia(self.ruta)
            pares = [
                p for h in informe.hechos for p in (h.a_favor + h.en_contra)
            ]
            indice.indexar([p.evidencia for p in pares], fecha)
        except Exception:
            pass

    def buscar(self, afirmacion: str, limite: int = 3) -> list[dict]:
        """Past reports for this exact claim (normalized), newest first.

        Returns dicts {veredicto, confianza, fecha, informe} — context for
        the user, never a silent replacement for re-verification.
        """
        filas = self._db.execute(
            "SELECT veredicto, confianza, fecha, informe_json"
            " FROM verificaciones WHERE afirmacion_normal = ?"
            " ORDER BY fecha DESC LIMIT ?",
            (_normalizar(afirmacion), limite),
        ).fetchall()
        return [
            {"veredicto": v, "confianza": c, "fecha": f,
             "informe": json.loads(j)}
            for v, c, f, j in filas
        ]

    def historial(self, limite: int = 20) -> list[dict]:
        """Most recent verifications across all sessions."""
        filas = self._db.execute(
            "SELECT id, afirmacion, veredicto, confianza, fecha"
            " FROM verificaciones ORDER BY fecha DESC LIMIT ?",
            (limite,),
        ).fetchall()
        return [
            {"id": i, "afirmacion": a, "veredicto": v, "confianza": c, "fecha": f}
            for i, a, v, c, f in filas
        ]

    def conversaciones(self, carpeta: str = "", limite: int = 30) -> list[dict]:
        """Conversations of one workspace ('' = General), most recent first.

        Only conversations that got at least one verification are listed —
        empty ones are invisible noise, not history.
        """
        filas = self._db.execute(
            "SELECT s.id, s.titulo, s.inicio, MAX(v.fecha), COUNT(v.id)"
            " FROM sesiones s JOIN verificaciones v ON v.sesion_id = s.id"
            " WHERE s.carpeta = ?"
            " GROUP BY s.id ORDER BY MAX(v.fecha) DESC LIMIT ?",
            (carpeta, limite),
        ).fetchall()
        return [
            {"id": i, "titulo": t, "inicio": ini, "ultima": u, "turnos": n}
            for i, t, ini, u, n in filas
        ]

    def hilo(self, sesion_id: int) -> list[dict]:
        """Full thread of one conversation, oldest first (reopen & continue)."""
        filas = self._db.execute(
            "SELECT id, afirmacion, veredicto, confianza, fecha, informe_json"
            " FROM verificaciones WHERE sesion_id = ? ORDER BY fecha, id",
            (sesion_id,),
        ).fetchall()
        return [
            {
                "id": i,
                "afirmacion": a,
                "veredicto": v,
                "confianza": c,
                "fecha": f,
                "informe": json.loads(j),
            }
            for i, a, v, c, f, j in filas
        ]

    def carpetas(self) -> list[dict]:
        """Workspaces with activity, newest first. General ('') is implicit
        and always exists, so it is excluded here."""
        filas = self._db.execute(
            "SELECT s.carpeta, COUNT(DISTINCT s.id), MAX(v.fecha)"
            " FROM sesiones s JOIN verificaciones v ON v.sesion_id = s.id"
            " WHERE s.carpeta != ''"
            " GROUP BY s.carpeta ORDER BY MAX(v.fecha) DESC",
        ).fetchall()
        return [
            {"carpeta": c, "conversaciones": n, "ultima": u} for c, n, u in filas
        ]

    def informe_por_id(self, id_verificacion: int) -> dict | None:
        """Full stored report for one verification (reopens a past
        conversation in the interface); None if the id doesn't exist."""
        fila = self._db.execute(
            "SELECT afirmacion, fecha, informe_json"
            " FROM verificaciones WHERE id = ?",
            (id_verificacion,),
        ).fetchone()
        if fila is None:
            return None
        return {"afirmacion": fila[0], "fecha": fila[1], "informe": json.loads(fila[2])}

    def cerrar(self) -> None:
        self._db.close()

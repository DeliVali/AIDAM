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

RUTA_DEFECTO = Path(os.environ.get("AIDAM_MEMORIA", "~/.aidam/memoria.db"))

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS sesiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT NOT NULL
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
        self.ruta = Path(ruta or RUTA_DEFECTO).expanduser()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.ruta)
        self._db.executescript(_ESQUEMA)
        self._db.commit()
        self.sesion_id = self._db.execute(
            "INSERT INTO sesiones (inicio) VALUES (?)", (_ahora(),)
        ).lastrowid
        self._db.commit()

    def guardar(self, informe: Informe) -> None:
        fecha = _ahora()
        self._db.execute(
            "INSERT INTO verificaciones (sesion_id, afirmacion,"
            " afirmacion_normal, veredicto, confianza, fecha, informe_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.sesion_id,
                informe.afirmacion,
                _normalizar(informe.afirmacion),
                informe.veredicto.value,
                informe.confianza,
                fecha,
                json.dumps(asdict(informe), ensure_ascii=False, default=str),
            ),
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
            "SELECT afirmacion, veredicto, confianza, fecha"
            " FROM verificaciones ORDER BY fecha DESC LIMIT ?",
            (limite,),
        ).fetchall()
        return [
            {"afirmacion": a, "veredicto": v, "confianza": c, "fecha": f}
            for a, v, c, f in filas
        ]

    def cerrar(self) -> None:
        self._db.close()

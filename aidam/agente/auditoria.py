"""JSONL audit log for agent tool calls.

Same philosophy as the aggregator: every decision must be reconstructible
after the fact. One JSON object per line, flushed immediately so a crash
never loses the record of what was already done.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_RUTA_DEFECTO = Path("data/local/auditoria.jsonl")


def hash_contenido(texto: str) -> str:
    """Stable short fingerprint for logged inputs/outputs (sha256, 16 hex chars)."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


class RegistroAuditoria:
    """Append-only JSONL log, thread-safe, flushed per record."""

    def __init__(self, ruta: Path | str | None = None) -> None:
        entorno = os.environ.get("AIDAM_AUDITORIA")
        self.ruta = Path(ruta or entorno or _RUTA_DEFECTO)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._candado = threading.Lock()

    def registrar(
        self,
        herramienta: str,
        argumento: str,
        decision: str,
        modo: str,
        aprobado_por: str,
        exito: bool | None = None,
        hash_resultado: str | None = None,
    ) -> None:
        evento = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "herramienta": herramienta,
            "argumento": argumento,
            "decision": decision,
            "modo": modo,
            "aprobado_por": aprobado_por,
            "exito": exito,
            "hash_resultado": hash_resultado,
        }
        linea = json.dumps(evento, ensure_ascii=False)
        with self._candado:
            with open(self.ruta, "a", encoding="utf-8") as archivo:
                archivo.write(linea + "\n")
                archivo.flush()

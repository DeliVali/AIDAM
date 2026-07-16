"""Semantic index over remembered evidence (agent memory, phase 2).

Jeffrey's insight (2026-07-13), made precise: the model cannot skip
tokenization — tokens are its native input — but the expensive part can
be computed ONCE and stored in the machine's own representation:
vectors. Every evidence passage the agent has ever retrieved gets
embedded and kept next to the session memory; later searches compare
meanings directly (cosine over stored vectors) instead of re-processing
text. Same measured principle that turned aggregation sweeps from hours
into seconds (pares_cache).

Embedder: intfloat/multilingual-e5-small — open weights, 118M params,
loads through the transformers dependency the verifier already requires
(no new package), multilingual like the rest of AIDAM, and runs on CPU
so it never competes with the verifier for VRAM. Swappable via
$AIDAM_MODELO_VECTORES, replaceable like every model in the agent.

Storage: a table inside the same SQLite memory file. Vectors are
float32 BLOBs; search loads them into one numpy matrix (fine up to
~10^5 passages — revisit with a real vector index beyond that).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from functools import lru_cache
from pathlib import Path

import numpy as np

from .models import Evidencia

MODELO_VECTORES = os.environ.get(
    "AIDAM_MODELO_VECTORES", "intfloat/multilingual-e5-small"
)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS evidencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    huella TEXT UNIQUE NOT NULL,
    texto TEXT NOT NULL,
    url TEXT NOT NULL,
    dominio TEXT NOT NULL,
    fuente TEXT NOT NULL,
    idioma TEXT NOT NULL,
    fecha TEXT NOT NULL,
    vector BLOB NOT NULL
);
"""


@lru_cache(maxsize=1)
def _codificador():
    """Loads the embedder once per process, on CPU on purpose."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODELO_VECTORES)
    modelo = AutoModel.from_pretrained(MODELO_VECTORES)
    modelo.eval()

    def codificar(textos: list[str]) -> np.ndarray:
        with torch.inference_mode():
            lote = tokenizer(
                textos, padding=True, truncation=True, max_length=512,
                return_tensors="pt",
            )
            estados = modelo(**lote).last_hidden_state
            mascara = lote["attention_mask"].unsqueeze(-1)
            media = (estados * mascara).sum(1) / mascara.sum(1)
            media = torch.nn.functional.normalize(media, dim=-1)
        return media.cpu().numpy().astype(np.float32)

    return codificar


def _huella(texto: str, url: str) -> str:
    return hashlib.sha256(f"{url}|{texto}".encode()).hexdigest()[:24]


class IndiceEvidencia:
    """Evidence passages embedded once, searchable by meaning."""

    def __init__(self, ruta: Path | str) -> None:
        self._db = sqlite3.connect(Path(ruta).expanduser())
        self._db.executescript(_ESQUEMA)
        self._db.commit()

    def indexar(self, evidencias: list[Evidencia], fecha: str) -> int:
        """Embed and store passages not seen before. Returns how many."""
        nuevas = []
        for e in evidencias:
            if not e.texto.strip():
                continue
            huella = _huella(e.texto, e.url)
            existe = self._db.execute(
                "SELECT 1 FROM evidencias WHERE huella = ?", (huella,)
            ).fetchone()
            if not existe:
                nuevas.append((huella, e))
        if not nuevas:
            return 0
        # e5 expects the "passage: " prefix on indexed text
        vectores = _codificador()([f"passage: {e.texto}" for _, e in nuevas])
        for (huella, e), vector in zip(nuevas, vectores):
            self._db.execute(
                "INSERT OR IGNORE INTO evidencias"
                " (huella, texto, url, dominio, fuente, idioma, fecha, vector)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (huella, e.texto, e.url, e.dominio, e.fuente, e.idioma,
                 fecha, vector.tobytes()),
            )
        self._db.commit()
        return len(nuevas)

    def buscar(self, consulta: str, limite: int = 5) -> list[dict]:
        """Top passages by meaning (cosine), newest data included free."""
        filas = self._db.execute(
            "SELECT texto, url, dominio, fuente, idioma, fecha, vector"
            " FROM evidencias"
        ).fetchall()
        if not filas:
            return []
        matriz = np.frombuffer(
            b"".join(f[6] for f in filas), dtype=np.float32
        ).reshape(len(filas), -1)
        consulta_v = _codificador()([f"query: {consulta}"])[0]
        puntajes = matriz @ consulta_v
        orden = np.argsort(-puntajes)[:limite]
        return [
            {"puntaje": float(puntajes[i]), "texto": filas[i][0],
             "url": filas[i][1], "dominio": filas[i][2],
             "fuente": filas[i][3], "idioma": filas[i][4],
             "fecha": filas[i][5]}
            for i in orden
        ]

    def total(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0]

    def cerrar(self) -> None:
        self._db.close()

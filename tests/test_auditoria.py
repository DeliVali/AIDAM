"""Audit log: parseable JSONL, immediate flush, stable hashing."""

from __future__ import annotations

import json

from aidam.agente.auditoria import RegistroAuditoria, hash_contenido


def test_escribe_jsonl_parseable_y_con_flush(tmp_path):
    ruta = tmp_path / "auditoria.jsonl"
    registro = RegistroAuditoria(ruta)
    registro.registrar("Ejecutar", "ls", "permitir", "preguntar", "regla:Ejecutar(ls)")
    registro.registrar(
        "Escribir", "/x", "denegar", "plan", "modo:plan", exito=False, hash_resultado="abc"
    )
    # Flushed per record: readable right away, one JSON object per line.
    lineas = ruta.read_text(encoding="utf-8").strip().splitlines()
    assert len(lineas) == 2
    primero, segundo = (json.loads(linea) for linea in lineas)
    assert primero["herramienta"] == "Ejecutar"
    assert primero["decision"] == "permitir"
    assert "ts" in primero
    assert segundo["exito"] is False
    assert segundo["hash_resultado"] == "abc"


def test_hash_contenido_estable_y_corto():
    assert hash_contenido("hola") == hash_contenido("hola")
    assert hash_contenido("hola") != hash_contenido("adios")
    assert len(hash_contenido("hola")) == 16


def test_respeta_variable_de_entorno(tmp_path, monkeypatch):
    destino = tmp_path / "otra" / "ruta.jsonl"
    monkeypatch.setenv("AIDAM_AUDITORIA", str(destino))
    registro = RegistroAuditoria()
    registro.registrar("Leer", "/x", "permitir", "plan", "modo:plan")
    assert destino.exists()

"""Tests for the offline AVeriTeC knowledge-store reader (no network, no zip)."""

import json

from aidam.models import HechoAtomico
from evaluation.knowledge_store import _cargar_documentos, _dominio, crear_recuperador_offline


def _escribir_claim(tmp_path, indice, registros):
    ruta = tmp_path / f"{indice}.json"
    ruta.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in registros), encoding="utf-8"
    )
    return ruta


def test_dominio_extrae_host_sin_www():
    assert _dominio("https://www.politifact.com/x") == "politifact.com"
    assert _dominio("") == "knowledge-store"


def test_cargar_documentos_aplana_url2text(tmp_path):
    ruta = _escribir_claim(
        tmp_path, 0,
        [
            {"url": "https://a.org/x", "url2text": ["Frase uno.", "Frase dos."]},
            {"url": "https://b.org/y", "url2text": ["Otra frase."]},
        ],
    )
    pares = _cargar_documentos(ruta)
    assert pares == [
        ("Frase uno.", "https://a.org/x"),
        ("Frase dos.", "https://a.org/x"),
        ("Otra frase.", "https://b.org/y"),
    ]


def test_cargar_documentos_archivo_inexistente(tmp_path):
    assert _cargar_documentos(tmp_path / "999.json") == []


def test_recuperador_offline_rankea_por_relevancia(tmp_path):
    _escribir_claim(
        tmp_path, 5,
        [
            {
                "url": "https://noticias.com/a",
                "url2text": [
                    "The weather today is sunny with a light breeze.",
                    "Amy Coney Barrett was confirmed to the Supreme Court on October 26 2020.",
                ],
            },
        ],
    )
    buscar = crear_recuperador_offline(5, tmp_path)
    hecho = HechoAtomico(texto="Amy Coney Barrett Supreme Court confirmation", origen="…")
    evidencias = buscar(hecho, lang="en")
    assert evidencias
    assert "Barrett" in evidencias[0].texto
    assert evidencias[0].fuente == "knowledge-store"
    assert evidencias[0].dominio == "noticias.com"


def test_recuperador_offline_claim_sin_datos_devuelve_vacio(tmp_path):
    buscar = crear_recuperador_offline(42, tmp_path)
    hecho = HechoAtomico(texto="cualquier afirmación", origen="…")
    assert buscar(hecho, lang="en") == []


def test_recuperador_offline_deduplica_pasajes_repetidos(tmp_path):
    _escribir_claim(
        tmp_path, 1,
        [
            {"url": "https://a.org/x", "url2text": ["El mismo dato repetido varias veces."]},
            {"url": "https://b.org/y", "url2text": ["El mismo dato repetido varias veces."]},
        ],
    )
    buscar = crear_recuperador_offline(1, tmp_path)
    hecho = HechoAtomico(texto="el mismo dato repetido", origen="…")
    evidencias = buscar(hecho, lang="es")
    assert len(evidencias) == 1

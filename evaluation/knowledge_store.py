"""Offline evidence from the AVeriTeC organizers' knowledge store.

The shared task ships a pre-scraped document collection per claim
(up to 1000 URLs each) specifically so systems don't need live web search —
"guaranteed to contain the right evidence" (2nd AVeriTeC Shared Task
overview, FEVER 2025). Using it instead of live `recuperar()` sidesteps
search-engine throttling entirely and gives a reproducible number, comparable
run to run and to the published baseline — unlike live retrieval, which
measured session-cumulative degradation this project ran into directly
(five AVeriTeC-100 runs in one session: 45%→41%→38%→39%→22%, tracking
exhausted search quota, not verifier quality; see docs/ROADMAP.md Phase 2).

Source: https://huggingface.co/chenxwh/AVeriTeC (model repo, despite the
name — `data_store/knowledge_store/dev_knowledge_store.zip`). One JSON-lines
file per claim index (`{indice}.json`), each line `{"url": ..., "url2text":
[sentence, ...]}`.

Usage:
  python evaluation/knowledge_store.py --extraer --hasta 100   # unzip once
  python evaluation/eval_averitec.py --limite 100 --knowledge-store \\
      data/local/knowledge_store/dev
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from aidam.models import Evidencia, HechoAtomico
from aidam.retrieve import _relevancia, _trocear

RUTA_ZIP = Path("data/local/knowledge_store/dev_knowledge_store.zip")
RUTA_EXTRAIDO = Path("data/local/knowledge_store/dev")


def extraer(hasta: int, zip_path: Path = RUTA_ZIP, salida: Path = RUTA_EXTRAIDO) -> int:
    """Pulls just the claim files needed (`0.json`..`{hasta-1}.json`) out of
    the archive — the full dev store covers all 500 claims; eval runs
    typically use the first 100."""
    salida.mkdir(parents=True, exist_ok=True)
    objetivo = {f"{i}.json" for i in range(hasta)}
    extraidos = 0
    with zipfile.ZipFile(zip_path) as zf:
        nombres = {Path(n).name: n for n in zf.namelist() if Path(n).name in objetivo}
        for nombre_corto, nombre_completo in nombres.items():
            (salida / nombre_corto).write_bytes(zf.read(nombre_completo))
            extraidos += 1
    return extraidos


def _dominio(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.") or "knowledge-store"


def _cargar_documentos(ruta_claim: Path) -> list[tuple[str, str]]:
    """(pasaje, url) pairs from a claim's knowledge-store file.

    Not real JSON-lines despite appearances: the scraped text embeds literal,
    unescaped newlines inside string values, so splitting on `\\n` cuts
    records mid-string (measured: "Unterminated string" on claim 0's 49 MB
    file, which naive line-splitting saw as 825 "lines" for far fewer actual
    records). A streaming decoder that walks JSON object boundaries instead
    of newline boundaries handles this correctly.
    """
    pares: list[tuple[str, str]] = []
    if not ruta_claim.exists():
        return pares
    texto = ruta_claim.read_text(encoding="utf-8")
    decodificador = json.JSONDecoder()
    posicion = 0
    longitud = len(texto)
    while posicion < longitud:
        while posicion < longitud and texto[posicion].isspace():
            posicion += 1
        if posicion >= longitud:
            break
        try:
            registro, fin = decodificador.raw_decode(texto, posicion)
        except json.JSONDecodeError:
            break  # truncated tail record: keep what parsed cleanly
        posicion = fin
        url = registro.get("url", "")
        for oracion in registro.get("url2text", []):
            oracion = oracion.strip()
            if oracion:
                pares.append((oracion, url))
    return pares


def crear_recuperador_offline(indice: int, ruta_dir: Path, max_pasajes: int = 12):
    """Builds a `(hecho, lang, max_idiomas, categoria) -> list[Evidencia]`
    callable — same shape as `aidam.retrieve.recuperar` — over one claim's
    pre-scraped documents, lexically ranked (same `_relevancia` scoring the
    live pipeline already uses for passage selection within a page)."""
    documentos = _cargar_documentos(ruta_dir / f"{indice}.json")

    def _buscar(hecho: HechoAtomico, lang: str = "", max_idiomas: int = 0, categoria=None):
        candidatos = [(p, u) for p, u in documentos if len(p) >= 20]
        candidatos.sort(key=lambda pu: _relevancia(hecho.texto, pu[0]), reverse=True)
        vistas: set[str] = set()
        evidencias: list[Evidencia] = []
        for pasaje, url in candidatos:
            if len(evidencias) >= max_pasajes:
                break
            clave = pasaje[:120]
            if clave in vistas:
                continue
            vistas.add(clave)
            evidencias.append(
                Evidencia(
                    texto=pasaje, url=url or "https://knowledge-store.local",
                    titulo="", dominio=_dominio(url), fuente="knowledge-store", idioma=lang,
                )
            )
        return evidencias

    return _buscar


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraer", action="store_true", help="unzip the needed claim files")
    parser.add_argument("--hasta", type=int, default=100, help="claim indices 0..hasta-1")
    parser.add_argument("--zip", type=Path, default=RUTA_ZIP)
    parser.add_argument("--salida", type=Path, default=RUTA_EXTRAIDO)
    args = parser.parse_args()

    if args.extraer:
        n = extraer(args.hasta, args.zip, args.salida)
        print(f"[knowledge-store] {n} archivos de claim extraídos → {args.salida}")


if __name__ == "__main__":
    main()

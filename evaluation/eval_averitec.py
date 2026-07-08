"""AIDAM evaluation on the AVeriTeC dev set (500 real-world claims).

AVeriTeC annotates real-world claims (2020–2021, in English) with four
verdicts that map one to one onto ours. This script runs the full pipeline
— live multi-source retrieval included — and reports accuracy, macro F1 and
the confusion matrix.

Honest note: live retrieval may find the fact-checking articles the claims
came from (the shared task uses a closed knowledge store to prevent that).
We measure the system end-to-end under real conditions; we don't compete on
the official track — comparing against the shared-task table would require
using its knowledge store.

Usage:
  python evaluation/eval_averitec.py --limite 100
  python evaluation/eval_averitec.py            # all 500 (≈1.5 h)

Progress is saved incrementally: relaunching resumes where it left off.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import requests

from aidam.models import Veredicto
from aidam.pipeline import verificar
from aidam.verify import VerificadorNLI

URL_DEV = "https://raw.githubusercontent.com/MichSchli/AVeriTeC/main/data/dev.json"
RUTA_DEV = Path("data/local/averitec_dev.json")
RUTA_RESULTADOS = Path("data/local/averitec_results.jsonl")

# Our verdicts → AVeriTeC classes (one-to-one mapping by design)
A_AVERITEC = {
    Veredicto.SUSTENTADO.value: "Supported",
    Veredicto.REFUTADO.value: "Refuted",
    Veredicto.INSUFICIENTE.value: "Not Enough Evidence",
    Veredicto.CONTRADICTORIO.value: "Conflicting Evidence/Cherrypicking",
}


def _cargar_dev() -> list[dict]:
    if not RUTA_DEV.exists():
        RUTA_DEV.parent.mkdir(parents=True, exist_ok=True)
        RUTA_DEV.write_bytes(requests.get(URL_DEV, timeout=60).content)
    return json.loads(RUTA_DEV.read_text())


def _cargar_previos(ruta: Path) -> dict[int, dict]:
    """Previous records for resuming. ERROR entries don't count as done:
    they are retried on relaunch (a transient OOM is not a verdict)."""
    if not ruta.exists():
        return {}
    previos = {}
    for linea in ruta.read_text().splitlines():
        if linea.strip():
            registro = json.loads(linea)
            if registro.get("prediccion") != "ERROR":
                previos[registro["indice"]] = registro
    return previos


def _f1_por_clase(registros: list[dict], clase: str) -> float:
    tp = sum(1 for r in registros if r["prediccion"] == clase and r["oro"] == clase)
    fp = sum(1 for r in registros if r["prediccion"] == clase and r["oro"] != clase)
    fn = sum(1 for r in registros if r["prediccion"] != clase and r["oro"] == clase)
    precision = tp / (tp + fp) if tp + fp else 0.0
    cobertura = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * cobertura / (precision + cobertura) if precision + cobertura else 0.0


def _reporte(registros: list[dict]) -> None:
    n = len(registros)
    aciertos = sum(1 for r in registros if r["prediccion"] == r["oro"])
    clases = sorted(A_AVERITEC.values())
    f1s = {c: _f1_por_clase(registros, c) for c in clases}
    print(f"\n=== AVeriTeC dev ({n} afirmaciones) ===")
    print(f"exactitud: {aciertos / n:.1%}   (baseline mayoritario del dev completo: 61.0%)")
    print(f"F1 macro:  {sum(f1s.values()) / len(f1s):.3f}")
    for clase in clases:
        oro = sum(1 for r in registros if r["oro"] == clase)
        pred = sum(1 for r in registros if r["prediccion"] == clase)
        print(f"  {clase:38s} F1={f1s[clase]:.3f}  (oro {oro}, predichas {pred})")
    confusion = Counter((r["oro"], r["prediccion"]) for r in registros)
    print("confusión (oro → predicción):")
    for (oro, pred), veces in confusion.most_common(8):
        marca = "✓" if oro == pred else "✗"
        print(f"  {marca} {oro} → {pred}: {veces}")
    tiempo_medio = sum(r["segundos"] for r in registros) / n
    print(f"tiempo medio por afirmación: {tiempo_medio:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limite", type=int, default=500)
    parser.add_argument("--max-idiomas", type=int, default=3)
    parser.add_argument(
        "--preguntas", action="store_true", help="question generation with the local LLM"
    )
    parser.add_argument("--pausa", type=float, default=2.0, help="seconds between claims")
    parser.add_argument("--salida", type=Path, default=RUTA_RESULTADOS)
    args = parser.parse_args()

    datos = _cargar_dev()[: args.limite]
    previos = _cargar_previos(args.salida)
    print(f"[eval] {len(datos)} afirmaciones; {len(previos)} ya evaluadas (se retoman)")

    verificador = VerificadorNLI()
    args.salida.parent.mkdir(parents=True, exist_ok=True)

    with args.salida.open("a") as salida:
        for indice, ejemplo in enumerate(datos):
            if indice in previos:
                continue
            inicio = time.time()
            try:
                informe = verificar(
                    ejemplo["claim"],
                    lang="en",
                    max_idiomas=args.max_idiomas,
                    preguntas=args.preguntas,
                    verificador=verificador,
                )
                prediccion = A_AVERITEC[informe.veredicto.value]
                confianza = informe.confianza
                voces = sum(len(h.a_favor) + len(h.en_contra) for h in informe.hechos)
            except Exception as error:  # one failed claim doesn't kill the run
                prediccion, confianza, voces = "ERROR", 0.0, 0
                print(f"[eval] #{indice} error: {error}")
            registro = {
                "indice": indice,
                "afirmacion": ejemplo["claim"],
                "oro": ejemplo["label"],
                "prediccion": prediccion,
                "confianza": confianza,
                "voces": voces,
                "segundos": round(time.time() - inicio, 1),
            }
            salida.write(json.dumps(registro, ensure_ascii=False) + "\n")
            salida.flush()
            acierto = "✓" if registro["prediccion"] == registro["oro"] else "✗"
            print(f"[eval] {indice + 1}/{len(datos)} {acierto} {registro['segundos']}s")
            time.sleep(args.pausa)

    registros = [r for r in _cargar_previos(args.salida).values() if r["prediccion"] != "ERROR"]
    if registros:
        _reporte(registros)


if __name__ == "__main__":
    main()

"""Baseline: a current (2026) reasoning LLM without retrieval.

AIDAM's thesis: comparing live evidence beats parametric knowledge. This
script puts it to the test — MiMo-7B-RL judges the same AVeriTeC claims
with only its memory and reasoning (thinking is allowed), without any
retrieved evidence. It's the same model AIDAM uses as a tool, acting here
as the opponent.

Usage:
  python evaluation/eval_baseline_llm.py --limite 100 [--gpu]
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from aidam.preguntas import GeneradorPreguntas, _BLOQUE_PENSAMIENTO
from evaluacion.eval_averitec import A_AVERITEC, _cargar_dev, _cargar_previos, _reporte

RUTA_RESULTADOS = Path("data/local/averitec_baseline_llm.jsonl")

_ETIQUETAS = {
    "SUPPORTED": "Supported",
    "REFUTED": "Refuted",
    "NOT ENOUGH EVIDENCE": "Not Enough Evidence",
    "CONFLICTING": "Conflicting Evidence/Cherrypicking",
}

_PROMPT = (
    "You are a fact-checker. Using your own knowledge and reasoning, classify "
    "this real-world claim (from 2020-2021) as exactly one of: SUPPORTED, "
    "REFUTED, NOT ENOUGH EVIDENCE, or CONFLICTING.\n"
    "Claim: {claim}\n"
    "End your answer with just the label."
)


def _parsear(texto: str) -> str | None:
    texto = _BLOQUE_PENSAMIENTO.sub("", texto).upper()
    # the last label mentioned is the final answer
    encontrada = None
    for etiqueta, clase in _ETIQUETAS.items():
        posicion = texto.rfind(etiqueta)
        if posicion >= 0 and (encontrada is None or posicion > encontrada[0]):
            encontrada = (posicion, clase)
    return encontrada[1] if encontrada else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limite", type=int, default=100)
    parser.add_argument("--gpu", action="store_true", help="use GPU (CPU by default)")
    parser.add_argument("--salida", type=Path, default=RUTA_RESULTADOS)
    args = parser.parse_args()

    datos = _cargar_dev()[: args.limite]
    previos = _cargar_previos(args.salida)
    print(f"[baseline] {len(datos)} afirmaciones; {len(previos)} ya evaluadas")

    generador = GeneradorPreguntas(n_gpu_layers=-1 if args.gpu else 0)
    args.salida.parent.mkdir(parents=True, exist_ok=True)

    with args.salida.open("a") as salida:
        for indice, ejemplo in enumerate(datos):
            if indice in previos:
                continue
            inicio = time.time()
            # No empty prefill: the baseline HAS the right to reason — that's
            # the fair comparison against a 2026 reasoning model.
            plantilla = (
                f"<|im_start|>user\n{_PROMPT.format(claim=ejemplo['claim'])}<|im_end|>\n"
                "<|im_start|>assistant\n"
            )
            respuesta = generador.completar(
                plantilla, max_tokens=900, temperature=0.0, stop=["<|im_end|>"]
            )
            prediccion = _parsear(respuesta) or "Not Enough Evidence"
            registro = {
                "indice": indice,
                "afirmacion": ejemplo["claim"],
                "oro": ejemplo["label"],
                "prediccion": prediccion,
                "confianza": 0.0,
                "segundos": round(time.time() - inicio, 1),
            }
            salida.write(json.dumps(registro, ensure_ascii=False) + "\n")
            salida.flush()
            acierto = "✓" if registro["prediccion"] == registro["oro"] else "✗"
            print(f"[baseline] {indice + 1}/{len(datos)} {acierto} {registro['segundos']}s")

    registros = list(_cargar_previos(args.salida).values())
    if registros:
        print("\n=== BASELINE LLM sin recuperación (MiMo-7B-RL, razonamiento libre) ===")
        _reporte(registros)


if __name__ == "__main__":
    main()

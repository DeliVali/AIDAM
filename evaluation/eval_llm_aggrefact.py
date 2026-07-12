"""Verifier evaluation on LLM-AggreFact (the MiniCheck benchmark).

Measures the core directly: given (document, claim), does the document
support the claim? This is the Phase 1 criterion: reach MiniCheck-FT5's
level (~74-75% average balanced accuracy).

Long documents: they are split into windows and the maximum p(supports)
over them is taken (the standard approach of pairwise verifiers). The
metric is balanced accuracy (mean of sensitivity and specificity) per
dataset and its average, as in the MiniCheck paper.

Usage:
  python evaluation/eval_llm_aggrefact.py [--umbral 0.5] [--max-ejemplos N]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from datasets import load_dataset

from aidam.retrieve import _trocear
from aidam.verify import VerificadorNLI


MAX_LEN_EVAL = 512  # overridden by --max-len (long-context backbones: 4096)
TROCEAR = True


def _p_sustenta(verificador, documentos: list[str], afirmaciones: list[str]) -> list[float]:
    """Maximum p(entailment) over each document's windows — or the whole
    document in one pass when --sin-trocear (long-context backbones)."""
    indice_sustenta = next(
        i for i, nombre in verificador.modelo.config.id2label.items()
        if nombre.lower() == "entailment"
    )
    probs: list[float] = []
    for doc, afirmacion in zip(documentos, afirmaciones):
        ventanas = (_trocear(doc, max_chars=1500) or [doc]) if TROCEAR else [doc]
        entradas = verificador.tokenizer(
            ventanas,
            [afirmacion] * len(ventanas),
            truncation=True,
            max_length=MAX_LEN_EVAL,
            padding=True,
            return_tensors="pt",
        ).to(verificador.device)
        with torch.inference_mode():
            logits = verificador.modelo(**entradas).logits / verificador._temperatura
        p = torch.softmax(logits, dim=-1)[:, indice_sustenta]
        probs.append(float(p.max()))
    return probs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--umbral", type=float, default=0.5)
    parser.add_argument("--max-ejemplos", type=int, default=0, help="0 = all")
    parser.add_argument("--max-len", type=int, default=512)
    parser.add_argument("--sin-trocear", action="store_true",
                        help="whole document in one pass (8k-context backbones)")
    parser.add_argument("--guardar", type=Path, default=None,
                        help="dump one jsonl row per example (dataset, label, "
                        "p_sustenta) — the raw material for calibration and "
                        "cascade-router analysis without re-running the model")
    args = parser.parse_args()
    global MAX_LEN_EVAL, TROCEAR
    MAX_LEN_EVAL = args.max_len
    TROCEAR = not args.sin_trocear

    datos = load_dataset("lytang/LLM-AggreFact", split="test")
    if args.max_ejemplos:
        datos = datos.shuffle(seed=42).select(range(args.max_ejemplos))
    print(f"[aggrefact] {len(datos)} pares")

    verificador = VerificadorNLI()
    lote = 256
    por_dataset: dict[str, list[tuple[int, int]]] = defaultdict(list)
    salida_filas = args.guardar.open("w") if args.guardar else None
    for inicio in range(0, len(datos), lote):
        parte = datos.select(range(inicio, min(inicio + lote, len(datos))))
        probs = _p_sustenta(verificador, list(parte["doc"]), list(parte["claim"]))
        for nombre, etiqueta, p in zip(parte["dataset"], parte["label"], probs):
            por_dataset[nombre].append((int(etiqueta), int(p >= args.umbral)))
            if salida_filas:
                salida_filas.write(json.dumps(
                    {"dataset": nombre, "label": int(etiqueta),
                     "p_sustenta": round(p, 4)}) + "\n")
        if inicio % (lote * 10) == 0:
            print(f"[aggrefact] {inicio}/{len(datos)}")
    if salida_filas:
        salida_filas.close()
        print(f"[aggrefact] confianzas → {args.guardar}")

    baccs = []
    for nombre in sorted(por_dataset):
        pares = np.array(por_dataset[nombre])
        oro, pred = pares[:, 0], pares[:, 1]
        tpr = (pred[oro == 1] == 1).mean() if (oro == 1).any() else 0.0
        tnr = (pred[oro == 0] == 0).mean() if (oro == 0).any() else 0.0
        bacc = (tpr + tnr) / 2
        baccs.append(bacc)
        print(f"[aggrefact] {nombre:24s} BAcc {bacc:.1%}  (n={len(pares)})")
    print(f"[aggrefact] PROMEDIO BAcc: {np.mean(baccs):.1%}  "
          "(MiniCheck-FT5 ≈ 74-75%; roberta-large NLI ≈ 64%)")


if __name__ == "__main__":
    main()

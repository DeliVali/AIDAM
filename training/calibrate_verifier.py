"""Verifier calibration: make 90% mean 90%.

Fits a temperature T (standard post-hoc scaling) minimizing NLL on the
VitaminC validation split, and reports the ECE (expected calibration error)
before and after. The temperature is saved next to the model and
`aidam/verify.py` applies it automatically.

With --xnli-es, it also measures how much Spanish the model keeps (XNLI
Spanish validation) — VitaminC and MNLI are English and forgetting must be
watched.

Usage:
  python training/calibrate_verifier.py [--xnli-es]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from datasets import load_dataset

from aidam.verify import VerificadorNLI, _resolver_modelo

_MAPA_VITAMINC = {"SUPPORTS": "entailment", "REFUTES": "contradiction", "NOT ENOUGH INFO": "neutral"}


def _logits_y_etiquetas(verificador, premisas, hipotesis, ids, batch=64):
    logits = []
    for inicio in range(0, len(premisas), batch):
        entradas = verificador.tokenizer(
            premisas[inicio : inicio + batch],
            hipotesis[inicio : inicio + batch],
            truncation=True,
            max_length=256,
            padding=True,
            return_tensors="pt",
        ).to(verificador.device)
        with torch.inference_mode():
            logits.append(verificador.modelo(**entradas).logits.float().cpu())
    return torch.cat(logits), torch.tensor(ids)


def _ece(probs: torch.Tensor, etiquetas: torch.Tensor, bins: int = 10) -> float:
    confianzas, predichas = probs.max(dim=1)
    aciertos = (predichas == etiquetas).float()
    ece = 0.0
    for i in range(bins):
        mascara = (confianzas > i / bins) & (confianzas <= (i + 1) / bins)
        if mascara.any():
            ece += mascara.float().mean() * (aciertos[mascara].mean() - confianzas[mascara].mean()).abs()
    return float(ece)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ejemplos", type=int, default=8_000)
    parser.add_argument("--xnli-es", action="store_true")
    args = parser.parse_args()

    verificador = VerificadorNLI()
    por_nombre = {n.lower(): i for i, n in verificador.modelo.config.id2label.items()}

    datos = load_dataset("tals/vitaminc", split="validation").shuffle(seed=42)
    datos = datos.select(range(min(args.ejemplos, len(datos))))
    ids = [por_nombre[_MAPA_VITAMINC[e]] for e in datos["label"]]
    logits, etiquetas = _logits_y_etiquetas(
        verificador, list(datos["evidence"]), list(datos["claim"]), ids
    )

    ece_antes = _ece(torch.softmax(logits, dim=1), etiquetas)

    temperatura = torch.nn.Parameter(torch.ones(1))
    optimizador = torch.optim.LBFGS([temperatura], lr=0.05, max_iter=100)

    def paso():
        optimizador.zero_grad()
        perdida = torch.nn.functional.cross_entropy(logits / temperatura, etiquetas)
        perdida.backward()
        return perdida

    optimizador.step(paso)
    t = float(temperatura.detach())
    ece_despues = _ece(torch.softmax(logits / t, dim=1), etiquetas)
    print(f"[calibrar] temperatura = {t:.3f} · ECE {ece_antes:.4f} → {ece_despues:.4f}")

    ruta = Path(_resolver_modelo())
    if ruta.is_dir():
        (ruta / "calibracion.json").write_text(json.dumps({"temperatura": t}))
        print(f"[calibrar] guardada en {ruta / 'calibracion.json'}")

    if args.xnli_es:
        xnli = load_dataset("facebook/xnli", "es", split="validation")
        # XNLI: 0=entailment, 1=neutral, 2=contradiction
        ids_x = [
            {0: por_nombre["entailment"], 1: por_nombre["neutral"], 2: por_nombre["contradiction"]}[e]
            for e in xnli["label"]
        ]
        logits_x, etiquetas_x = _logits_y_etiquetas(
            verificador, list(xnli["premise"]), list(xnli["hypothesis"]), ids_x
        )
        exactitud = float((logits_x.argmax(dim=1) == etiquetas_x).float().mean())
        print(f"[calibrar] XNLI-es exactitud: {exactitud:.1%} "
              "(checkpoint base público: ~85% — vigilar el olvido del español)")


if __name__ == "__main__":
    main()

"""Phase B of the decomposition prototype: verify atomic facts, aggregate.

Reads the decompositions from evaluation/decompose_claims.py, scores each
atomic fact against the document with the production verifier (windowed
max p(supports), same as eval_llm_aggrefact), aggregates with the MIN over
facts — one unsupported fact sinks the claim — and reports BAcc against
gold next to the whole-claim baseline on the same items.

Claims whose decomposition came back empty fall back to the whole claim.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from datasets import load_dataset

from aidam.verify import VerificadorNLI
from evaluation.eval_llm_aggrefact import _p_sustenta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decomp", type=Path,
                        default=Path("data/local/decomp_cnn.jsonl"))
    parser.add_argument("--umbral", type=float, default=0.5)
    args = parser.parse_args()

    filas = [json.loads(l) for l in args.decomp.open()]
    datos = load_dataset("lytang/LLM-AggreFact", split="test")
    verificador = VerificadorNLI()

    oro, p_min, p_entera = [], [], []
    for n, f in enumerate(filas):
        doc = datos[f["idx"]]["doc"]
        claim = datos[f["idx"]]["claim"]
        hechos = f["hechos"] or [claim]
        probs = _p_sustenta(verificador, [doc] * len(hechos), hechos)
        p_min.append(min(probs))
        p_entera.append(_p_sustenta(verificador, [doc], [claim])[0])
        oro.append(f["label"])
        if (n + 1) % 50 == 0:
            print(f"[verif] {n + 1}/{len(filas)}")

    oro = np.array(oro)

    def bacc(p):
        pred = (np.array(p) >= args.umbral).astype(int)
        tpr = (pred[oro == 1] == 1).mean()
        tnr = (pred[oro == 0] == 0).mean()
        return (tpr + tnr) / 2, tpr, tnr

    for nombre, p in (("claim entero (línea base)", p_entera),
                      ("descompuesto + min", p_min)):
        b, tpr, tnr = bacc(p)
        print(f"[verif] {nombre}: BAcc {b:.1%}  (label=1: {tpr:.1%}, label=0: {tnr:.1%})")


if __name__ == "__main__":
    main()

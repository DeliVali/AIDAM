"""Tune the veto-hybrid threshold OFF-test, freeze it, then apply.

The measured directional law (2026-07-12): decomposition+min fixes
credulity-shaped failure (AggreFact-CNN +11.2) and worsens
skepticism-shaped failure (ExpertQA -3.4). The deployment that preserves
the win without the damage is a VETO: the whole-claim verdict stands,
except a confident "supports" gets overridden when some atomic fact
scores at or below T_bajo.

Discipline, stated where the code lives: T_bajo is chosen on a HELD-OUT
D2C dev set (fresh seed, never trained on, never the benchmark), frozen,
and only then applied — read-only — to the benchmark dumps. Tuning
anything on the benchmark itself would be overfitting the yardstick.

Inputs:
  --pares      dev pairs jsonl {claim, evidence, label}
  --decomp     their decompositions (decompose_claims.py --pares)
  --aplicar    benchmark per-item dumps (verify_decomposed.py --guardar)
               to score with the FROZEN threshold, format name=path
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from aidam.verify import VerificadorNLI
from evaluation.eval_llm_aggrefact import _p_sustenta


def _bacc(oro: np.ndarray, pred: np.ndarray) -> float:
    tpr = (pred[oro == 1] == 1).mean() if (oro == 1).any() else 0.0
    tnr = (pred[oro == 0] == 0).mean() if (oro == 0).any() else 0.0
    return (tpr + tnr) / 2


def _veto(p_entera: np.ndarray, p_min: np.ndarray, t_bajo: float) -> np.ndarray:
    pred = (p_entera >= 0.5).astype(int)
    pred[(pred == 1) & (p_min <= t_bajo)] = 0
    return pred


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pares", type=Path,
                        default=Path("data/local/multisent_dev_pairs.jsonl"))
    parser.add_argument("--decomp", type=Path,
                        default=Path("data/local/decomp_multisent_dev.jsonl"))
    parser.add_argument("--aplicar", nargs="*", default=[],
                        help="name=path of benchmark dumps to score with the "
                        "frozen threshold (read-only)")
    args = parser.parse_args()

    filas = [json.loads(l) for l in args.pares.open()]
    filas = [f for f in filas if f["label"] in ("SUPPORTS", "REFUTES")]
    descomp = {d["idx"]: d["hechos"] for d in map(json.loads, args.decomp.open())}

    verificador = VerificadorNLI()
    oro, p_entera, p_min = [], [], []
    for i, f in enumerate(filas):
        if i not in descomp:
            continue
        hechos = descomp[i] or [f["claim"]]
        probs = _p_sustenta(verificador, [f["evidence"]] * len(hechos), hechos)
        p_min.append(min(probs))
        p_entera.append(_p_sustenta(verificador, [f["evidence"]], [f["claim"]])[0])
        oro.append(int(f["label"] == "SUPPORTS"))
        if (len(oro)) % 200 == 0:
            print(f"[tune] {len(oro)} pares dev")
    oro = np.array(oro)
    p_entera, p_min = np.array(p_entera), np.array(p_min)
    print(f"[tune] dev n={len(oro)} | entera BAcc {_bacc(oro, (p_entera >= 0.5).astype(int)):.1%}"
          f" | min BAcc {_bacc(oro, (p_min >= 0.5).astype(int)):.1%}")

    rejilla = np.round(np.arange(0.05, 0.55, 0.05), 2)
    puntajes = [(t, _bacc(oro, _veto(p_entera, p_min, t))) for t in rejilla]
    for t, b in puntajes:
        print(f"[tune]   T_bajo={t:.2f} → dev BAcc {b:.1%}")
    t_congelado = max(puntajes, key=lambda x: x[1])[0]
    print(f"[tune] T_bajo CONGELADO = {t_congelado:.2f}")

    for spec in args.aplicar:
        nombre, ruta = spec.split("=", 1)
        d = [json.loads(l) for l in open(ruta)]
        o = np.array([f["label"] for f in d])
        pe = np.array([f["p_entera"] for f in d])
        pm = np.array([f["p_min"] for f in d])
        base = _bacc(o, (pe >= 0.5).astype(int))
        hibrido = _bacc(o, _veto(pe, pm, t_congelado))
        print(f"[aplicar] {nombre}: entera {base:.1%} → veto-híbrido {hibrido:.1%}")


if __name__ == "__main__":
    main()

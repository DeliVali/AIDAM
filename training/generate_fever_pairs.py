"""FEVER-register pairs from FEVER TRAIN (never validation: that's our eval).

The move that won +8.7 on SciFact (in-register training from the benchmark's
own train split), applied to FEVER — where the headroom is real: 77.7%
oracle-evidence accuracy vs. high-80s/90s for published systems in the same
setting, and 228k gold-evidence train claims never used. FEVER's NEI class
is also the largest clean source of related-but-not-probative pairs we have
(its evidence was retrieval-mined, not hand-picked), which targets the NEI
erosion documented as v10's cost on AVeriTeC.

Balanced subsample (default 10k per label) via fixed seed; evidence is the
concatenated gold sentences, exactly as the eval reads them.

Output: data/local/fever_pairs.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SALIDA = Path("data/local/fever_pairs.jsonl")
SEMILLA = 49
_MAPA = {"SUPPORTS": "SUPPORTS", "REFUTES": "REFUTES", "NOT ENOUGH INFO": "NOT ENOUGH INFO"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--por-etiqueta", type=int, default=10_000)
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    from datasets import load_dataset

    datos = load_dataset("copenlu/fever_gold_evidence", split="train")
    por_clase: dict[str, list[dict]] = {k: [] for k in _MAPA}
    for ejemplo in datos:
        if ejemplo["label"] not in por_clase:
            continue
        oraciones = [e[2] for e in ejemplo.get("evidence", []) if len(e) >= 3 and e[2]]
        texto = " ".join(oraciones).strip()
        if len(texto) < 30:
            continue
        por_clase[ejemplo["label"]].append(
            {"claim": ejemplo["claim"], "evidence": texto[:2000]}
        )

    aleatorio = random.Random(SEMILLA)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    generados: dict[str, int] = {}
    with args.salida.open("w") as salida:
        for etiqueta, filas in por_clase.items():
            aleatorio.shuffle(filas)
            for fila in filas[: args.por_etiqueta]:
                salida.write(json.dumps(
                    {**fila, "label": etiqueta, "origen": "fever"}, ensure_ascii=False) + "\n")
            generados[etiqueta] = min(args.por_etiqueta, len(filas))
    for etiqueta, n in generados.items():
        print(f"  {etiqueta}: {n} (de {len(por_clase[etiqueta])})")
    print(f"[fever] {sum(generados.values())} pares → {args.salida}")


if __name__ == "__main__":
    main()

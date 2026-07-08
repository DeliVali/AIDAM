"""Generates hard-neutral pairs: same topic, different proof.

The verifier's measured failure (v0 and v1): topically related but
non-probative passages get judged as contradiction. The published recipe
(synthetic hard negatives, Auto-GDA) asks for pairs "aligned in topic,
irrelevant in semantics". VitaminC already carries the structure to build
them mechanically: several distinct claims per Wikipedia page. We pair
claim i with the evidence of claim j (same page, different fact) →
neutral label.

Anti-noise filters:
- the evidence must share ≥2 content words with the claim (otherwise the
  probative gate would filter it at inference: we want the hard zone),
- the two claims must be distinct facts (overlap < 50%),
- one evidence per (claim, page) to avoid repetition.

Output: data/local/hard_neutrals.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

SALIDA = Path("data/local/hard_neutrals.jsonl")
SEMILLA = 42


def _palabras(texto: str) -> set[str]:
    return set(re.findall(r"\w{4,}", texto.lower()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pares", type=int, default=30_000)
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    train = load_dataset("tals/vitaminc", split="train").shuffle(seed=SEMILLA)

    por_pagina: dict[str, list[dict]] = defaultdict(list)
    for fila in train:
        pagina = fila.get("page") or ""
        if pagina:
            por_pagina[pagina].append(fila)

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    generados = 0
    with args.salida.open("w") as salida:
        for pagina, filas in por_pagina.items():
            if generados >= args.max_pares:
                break
            vistos: set[str] = set()
            for i, fila_i in enumerate(filas):
                claim_i = fila_i["claim"]
                palabras_i = _palabras(claim_i)
                if not palabras_i or claim_i in vistos:
                    continue
                for fila_j in filas[i + 1 :]:
                    evidencia_j = fila_j["evidence"]
                    palabras_j = _palabras(fila_j["claim"])
                    # distinct facts: little overlap between claims
                    if palabras_j and len(palabras_i & palabras_j) / len(palabras_i) >= 0.5:
                        continue
                    # hard zone: the evidence does share the claim's topic
                    if len(palabras_i & _palabras(evidencia_j)) < 2:
                        continue
                    salida.write(
                        json.dumps(
                            {
                                "claim": claim_i,
                                "evidence": evidencia_j,
                                "label": "NOT ENOUGH INFO",
                                "origen": f"neutral-dificil:{pagina}",
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    vistos.add(claim_i)
                    generados += 1
                    break  # one per claim
                if generados >= args.max_pares:
                    break
    print(f"[neutrales] {generados} pares neutrales-difíciles → {args.salida}")


if __name__ == "__main__":
    main()

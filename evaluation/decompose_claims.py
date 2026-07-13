"""Phase A of the decomposition prototype: claim → atomic facts.

The CNN audit measured why naive judging fails on subtle errors: whole
claims read as \"supported\" when one embedded fact is wrong (the 8B
zero-shot caught 9.3% of unsupported claims; even our specialist reads
whole summaries). Stage 4's mechanism attacks exactly that: split each
claim into atomic factual statements so the verifier judges each fact
against the document separately — one wrong fact then sinks the claim
regardless of how much of the rest is right.

This script only decomposes (LLM work); verification is a separate pass
(evaluation/verify_decomposed.py) so the 8B and the verifier never share
the GPU.

Output: jsonl rows {idx, label, hechos: [str, ...]}.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from datasets import load_dataset

from aidam.questions import GeneradorPreguntas

_PROMPT_DESCOMPONER = (
    "Break the claim below into its atomic factual statements. Each atomic "
    "fact must be a single self-contained sentence that names its subject "
    "explicitly (no pronouns). Output one fact per line, nothing else.\n"
    "Claim: {claim}"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subconjunto", default="AggreFact-CNN")
    parser.add_argument("--salida", type=Path,
                        default=Path("data/local/decomp_cnn.jsonl"))
    args = parser.parse_args()

    datos = load_dataset("lytang/LLM-AggreFact", split="test")
    indices = [i for i, d in enumerate(datos["dataset"]) if d == args.subconjunto]
    print(f"[decomp] {len(indices)} claims de {args.subconjunto}")

    generador = GeneradorPreguntas()
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with args.salida.open("w") as salida:
        for n, idx in enumerate(indices):
            fila = datos[idx]
            crudo = generador._responder(
                _PROMPT_DESCOMPONER.format(claim=fila["claim"]),
                max_tokens=300, temperature=0.0,
            )
            hechos = [
                re.sub(r"^[\s\-\*\d\.\)]+", "", linea).strip()
                for linea in (crudo or "").splitlines()
            ]
            hechos = [h for h in hechos if len(h) > 15]
            salida.write(json.dumps(
                {"idx": idx, "label": int(fila["label"]), "hechos": hechos},
                ensure_ascii=False) + "\n")
            salida.flush()
            if (n + 1) % 25 == 0:
                print(f"[decomp] {n + 1}/{len(indices)}")
    print(f"[decomp] COMPLETO → {args.salida}")


if __name__ == "__main__":
    main()

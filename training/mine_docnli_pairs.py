"""Long-document pairs mined from DocNLI: the missing register for grounding.

Diagnosed since day 2 and never addressed until now: every training pair in
the mix is a short passage, but LLM-AggreFact's documents are long — and our
worst sub-dataset there (AggreFact-CNN, 50.3% ≈ coin flip) is exactly
long-document summarization consistency. MiniCheck's published edge comes
from long-document training data; DocNLI (942k public pairs, premise = full
document) is the zero-generation-cost source of that register.

Label mapping is deliberately conservative: entailment→SUPPORTS,
not_entailment→NOT ENOUGH INFO — never REFUTES, because DocNLI's negative
class mixes contradiction with mere non-support, and mislabeling non-support
as contradiction would corrupt the refute boundary that AVeriTeC depends on
(the v9 lesson: protecting real refutation signal matters more than
coverage).

Output: data/local/docnli_pairs.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SALIDA = Path("data/local/docnli_pairs.jsonl")
SEMILLA = 50


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--por-etiqueta", type=int, default=20_000)
    parser.add_argument("--min-chars", type=int, default=800,
                        help="only genuinely long premises: the register being added")
    parser.add_argument("--max-chars", type=int, default=6000)
    parser.add_argument("--salida", type=Path, default=SALIDA)
    parser.add_argument(
        "--solo-entailment", action="store_true",
        help="mine ONLY the entailment side (its positives are summaries, "
        "clean); DocNLI's not_entailment class includes FEVER/ANLI "
        "contradictions relabeled as non-entailment -- mapping those to NEI "
        "taught anti-refutation (measured: v12, FEVER 77.7->48.1)",
    )
    args = parser.parse_args()

    from datasets import load_dataset

    datos = load_dataset("saattrupdan/doc-nli", split="train")
    clases = ["entailment"] if args.solo_entailment else ["entailment", "not_entailment"]
    por_clase: dict[str, list[dict]] = {c: [] for c in clases}
    objetivo = args.por_etiqueta * 3  # oversample before shuffling down
    for ejemplo in datos:
        etiqueta = ejemplo["label"]
        if etiqueta not in por_clase or len(por_clase[etiqueta]) >= objetivo:
            if all(len(v) >= objetivo for v in por_clase.values()):
                break
            continue
        premisa = ejemplo["premise"]
        if not (args.min_chars <= len(premisa) <= args.max_chars):
            continue
        hipotesis = ejemplo["hypothesis"].strip()
        if len(hipotesis) < 15:
            continue
        por_clase[etiqueta].append({"claim": hipotesis, "evidence": premisa})

    aleatorio = random.Random(SEMILLA)
    mapa = {"entailment": "SUPPORTS", "not_entailment": "NOT ENOUGH INFO"}
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    generados: dict[str, int] = {}
    with args.salida.open("w") as salida:
        for etiqueta, filas in por_clase.items():
            aleatorio.shuffle(filas)
            for fila in filas[: args.por_etiqueta]:
                salida.write(json.dumps(
                    {**fila, "label": mapa[etiqueta], "origen": "docnli"},
                    ensure_ascii=False) + "\n")
            generados[mapa[etiqueta]] = min(args.por_etiqueta, len(filas))
    for etiqueta, n in generados.items():
        print(f"  {etiqueta}: {n}")
    print(f"[docnli] {sum(generados.values())} pares → {args.salida}")


if __name__ == "__main__":
    main()

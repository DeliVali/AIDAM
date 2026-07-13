"""Label audit for AggreFact-CNN: quantify the annotation-noise ceiling.

AggreFact-CNN sat at 52.8-57.1 across four verifier builds (v17-v20)
while every other subset responded to register levers. Its labels come
from the FactCC/Frank-era human annotations, documented as noisy by the
AggreFact authors themselves. Before spending training nights on it, we
measure how much of the gap is even reachable: the local LLM judges each
(doc, claim) pair independently; items where the strong models
unanimously contradict gold are noise-ceiling candidates.

The audit informs interpretation and the certified-subset program ONLY.
Its output NEVER feeds training — auditing test labels and then training
on the conclusions would be contamination, stated here so the boundary
survives the enthusiasm of any future session.

Output: one jsonl row per item {idx, label, veredicto_llm, p_sustenta_v20}.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from datasets import load_dataset

from aidam.questions import GeneradorPreguntas

_PROMPT_JUEZ = (
    "Document:\n{doc}\n\nClaim: {claim}\n\nDoes the document fully support "
    "the claim? Every fact in the claim must be stated in or clearly implied "
    "by the document. Reply with ONLY one word: yes or no."
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subconjunto", default="AggreFact-CNN")
    parser.add_argument("--confianzas", type=Path,
                        default=Path("data/local/confianzas_v20_aggrefact.jsonl"),
                        help="per-example dump from eval_llm_aggrefact.py "
                        "--guardar (same dataset order) to join p_sustenta")
    parser.add_argument("--salida", type=Path,
                        default=Path("data/local/audit_cnn_labels.jsonl"))
    args = parser.parse_args()

    datos = load_dataset("lytang/LLM-AggreFact", split="test")
    indices = [i for i, d in enumerate(datos["dataset"]) if d == args.subconjunto]
    print(f"[audit] {len(indices)} items de {args.subconjunto}")

    p_v20: list[float | None] = [None] * len(indices)
    if args.confianzas.exists():
        filas = [json.loads(l) for l in args.confianzas.open()]
        del_sub = [f["p_sustenta"] for f in filas if f["dataset"] == args.subconjunto]
        if len(del_sub) == len(indices):
            p_v20 = del_sub

    generador = GeneradorPreguntas()
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with args.salida.open("w") as salida:
        for n, (idx, p20) in enumerate(zip(indices, p_v20)):
            fila = datos[idx]
            crudo = generador._responder(
                _PROMPT_JUEZ.format(doc=fila["doc"][:6000], claim=fila["claim"]),
                max_tokens=120, temperature=0.0,
            )
            m = re.search(r"\b(yes|no)\b", crudo.lower()) if crudo else None
            veredicto = {"yes": 1, "no": 0}.get(m.group(1)) if m else None
            salida.write(json.dumps({
                "idx": idx, "label": int(fila["label"]),
                "veredicto_llm": veredicto,
                "p_sustenta_v20": p20,
            }) + "\n")
            salida.flush()
            if (n + 1) % 25 == 0:
                print(f"[audit] {n + 1}/{len(indices)}")
    print(f"[audit] COMPLETO → {args.salida}")


if __name__ == "__main__":
    main()

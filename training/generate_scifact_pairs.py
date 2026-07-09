"""Scientific-register pairs from SciFact TRAIN (never dev/test: no leakage).

The gap SciFact dev exposed (2026-07-09): the verifier calls 96/300
SUPPORT/CONTRADICT claims NEI because scientific abstracts hedge and no
single sentence clears the entailment threshold — the model has never seen
this register. SciFact train ships exactly the fix: real expert claims with
human-annotated rationale sentences and SUPPORT/CONTRADICT labels. We turn
each annotated rationale into an (evidence, claim) pair in the verifier's
own vocabulary, plus mechanical NEI pairs (claim × a sentence from an
unrelated abstract) so the three classes stay balanced — the same
shortcut-proofing that made v8's denial pairs work and distinguished them
from v7's failed mining.

Output: data/local/scifact_pairs.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

RUTA = Path("data/local/scifact/data")
SALIDA = Path("data/local/scifact_pairs.jsonl")
SEMILLA = 47


def _corpus() -> dict[int, list[str]]:
    return {
        doc["doc_id"]: doc["abstract"]
        for doc in (json.loads(l) for l in (RUTA / "corpus.jsonl").read_text().splitlines())
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    corpus = _corpus()
    todos_doc_ids = list(corpus)
    aleatorio = random.Random(SEMILLA)
    claims = [
        json.loads(l)
        for l in (RUTA / "claims_train.jsonl").read_text().splitlines()
        if l.strip()
    ]

    generados = {"SUPPORTS": 0, "REFUTES": 0, "NOT ENOUGH INFO": 0}
    with args.salida.open("w") as salida:
        for ejemplo in claims:
            claim = ejemplo["claim"]
            evidencia = ejemplo.get("evidence") or {}
            # SUPPORT/REFUTE: the exact human-annotated rationale sentences.
            for doc_id, grupos in evidencia.items():
                abstract = corpus.get(int(doc_id), [])
                for grupo in grupos:
                    oraciones = [abstract[i] for i in grupo["sentences"] if i < len(abstract)]
                    texto = " ".join(oraciones).strip()
                    if len(texto) < 30:
                        continue
                    etiqueta = "SUPPORTS" if grupo["label"] == "SUPPORT" else "REFUTES"
                    salida.write(json.dumps(
                        {"claim": claim, "evidence": texto, "label": etiqueta,
                         "origen": "scifact"}, ensure_ascii=False) + "\n")
                    generados[etiqueta] += 1
            # NEI: claim against a sentence from an unrelated abstract. One per
            # claim keeps the class from swamping; topical-but-irrelevant is the
            # hard-neutral profile the verifier needs (a random biomedical
            # sentence, not gibberish).
            for _ in range(2):
                doc_id = aleatorio.choice(todos_doc_ids)
                if str(doc_id) in evidencia or doc_id in evidencia:
                    continue
                abstract = corpus.get(doc_id, [])
                if not abstract:
                    continue
                texto = aleatorio.choice(abstract).strip()
                if len(texto) < 30:
                    continue
                salida.write(json.dumps(
                    {"claim": claim, "evidence": texto, "label": "NOT ENOUGH INFO",
                     "origen": "scifact"}, ensure_ascii=False) + "\n")
                generados["NOT ENOUGH INFO"] += 1
                break

    for etiqueta, n in generados.items():
        print(f"  {etiqueta}: {n}")
    print(f"[scifact] {sum(generados.values())} pares → {args.salida}")


if __name__ == "__main__":
    main()

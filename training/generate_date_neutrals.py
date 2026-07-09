"""Hard-neutral pairs for the specific pattern traced 2026-07-08: same
topic, different (but real, nearby) date — should read as ambiguous, not
automatically contradiction.

Measured failure (AVeriTeC offline eval, Amy Coney Barrett claim): a claim
true and gold-Supported ("confirmed...October 26, 2020") was refuted at 87%
confidence because 8 of 10 top passages cite October 27 — not bad sources,
supremecourt.gov itself states the Judicial Oath was administered the 27th,
a technically distinct event (oath vs. confirmation vote) a day apart.
Multiple authoritative sources use the same verbs for adjacent-but-different
dated events; the verifier reads any date mismatch as a flat contradiction
signal, with no notion that some date mismatches are between closely related
events rather than a genuinely false claim.

Mechanical, not LLM-generated (no hallucination risk, same spirit as
generate_neutrals.py): mines VitaminC's own same-page structure for pairs
where the claim and a DIFFERENT claim's evidence share topic AND each
contain a date-like token, but the tokens differ — real Wikipedia text,
real dates, just mismatched by construction.

Output: data/local/date_neutrals.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

SALIDA = Path("data/local/date_neutrals.jsonl")
SEMILLA = 45  # distinct from generate_neutrals.py's 42: different VitaminC shuffle

_MESES = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
)
_FECHA = re.compile(rf"\b(?:{_MESES})\s+\d{{1,2}}\b|\b(19|20)\d{{2}}\b", re.IGNORECASE)


def _palabras(texto: str) -> set[str]:
    return set(re.findall(r"\w{4,}", texto.lower()))


def _fechas(texto: str) -> set[str]:
    return {m.group(0).lower() for m in _FECHA.finditer(texto)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pares", type=int, default=10_000)
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
                fechas_i = _fechas(claim_i)
                palabras_i = _palabras(claim_i)
                if not fechas_i or not palabras_i or claim_i in vistos:
                    continue
                for fila_j in filas[i + 1 :]:
                    evidencia_j = fila_j["evidence"]
                    fechas_j = _fechas(evidencia_j)
                    if not fechas_j or fechas_i & fechas_j:
                        continue  # need a date mismatch, not just any date
                    palabras_j = _palabras(fila_j["claim"])
                    if palabras_j and len(palabras_i & palabras_j) / len(palabras_i) >= 0.5:
                        continue  # distinct facts, same guard as generate_neutrals.py
                    if len(palabras_i & _palabras(evidencia_j)) < 2:
                        continue  # same topic, the hard zone
                    salida.write(
                        json.dumps(
                            {
                                "claim": claim_i,
                                "evidence": evidencia_j,
                                "label": "NOT ENOUGH INFO",
                                "origen": f"neutral-fecha:{pagina}",
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    vistos.add(claim_i)
                    generados += 1
                    break
                if generados >= args.max_pares:
                    break
    print(f"[neutrales-fecha] {generados} pares → {args.salida}")


if __name__ == "__main__":
    main()

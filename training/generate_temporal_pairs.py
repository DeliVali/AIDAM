"""Temporal/quantity-qualification pairs: a number for a DIFFERENT time
doesn't contradict a time-qualified claim.

The traced gap (v8-500, 2026-07-09, biggest error bucket): "At independence,
Nigeria had a population of 45 million" (true, gold Supported) was refuted
at confidence 1.00 because evidence stating TODAY's population (200M) reads
as a flat numeric contradiction — the verifier has no notion that a
quantity is bound to its time qualifier. v7 tried to teach this by mining
VitaminC mechanically and failed (mechanism never fired); v8's denial set
established the recipe that does work: fully synthetic three-way contrast
with identical surface structure per label, so nothing predicts the label
except the alignment being taught.

Three-way per template (identical vocabulary, only time-alignment varies):
  evidence "In {t1}, {X} had {q1}."  + claim "In {t1}, {X} had {q1}." → SUPPORTS
  evidence "In {t1}, {X} had {q2}."  + claim "In {t1}, {X} had {q1}." → REFUTES
  evidence "In {t2}, {X} had {q2}."  + claim "In {t1}, {X} had {q1}." → NOT ENOUGH INFO

Output: data/local/temporal_pairs.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SALIDA = Path("data/local/temporal_pairs.jsonl")
SEMILLA = 46

_ENTIDADES = [
    "Nigeria", "Kenya", "Indonesia", "Brazil", "Vietnam", "Poland", "Peru",
    "Morocco", "Bangladesh", "Ukraine", "Colombia", "Egypt", "Thailand",
    "the city of Lagos", "the city of Mumbai", "the city of Jakarta",
    "the metropolitan area of Mexico City", "the province of Ontario",
    "the state of Texas", "the region of Catalonia", "the company",
    "the university", "the national railway", "the airline", "the port",
]
_CANTIDADES = [
    ("a population of {n} million", (3, 220)),
    ("a GDP of {n} billion dollars", (5, 900)),
    ("{n} thousand employees", (2, 400)),
    ("an unemployment rate of {n} percent", (2, 30)),
    ("{n} million registered vehicles", (1, 40)),
    ("an annual budget of {n} million dollars", (10, 900)),
    ("{n} public hospitals", (5, 800)),
    ("{n} kilometers of rail network", (100, 9000)),
]
# Time qualifiers deliberately mix styles: years, named events, relative eras.
_TIEMPOS = [
    "In {y}", "As of {y}", "By {y}", "At independence", "At its founding",
    "Before the reform", "After the merger", "At the last census",
    "During the crisis", "At the start of the decade",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--por-etiqueta", type=int, default=4000, help="pairs per label")
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    aleatorio = random.Random(SEMILLA)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    generados = {"SUPPORTS": 0, "REFUTES": 0, "NOT ENOUGH INFO": 0}

    def _tiempo() -> str:
        plantilla = aleatorio.choice(_TIEMPOS)
        return plantilla.format(y=aleatorio.randint(1955, 2026)) if "{y}" in plantilla else plantilla

    with args.salida.open("w") as salida:
        for _ in range(args.por_etiqueta):
            entidad = aleatorio.choice(_ENTIDADES)
            forma, (lo, hi) = aleatorio.choice(_CANTIDADES)
            n1 = aleatorio.randint(lo, hi)
            # A clearly different number: at least 25% away, never equal.
            while True:
                n2 = aleatorio.randint(lo, hi)
                if abs(n2 - n1) > max(1, n1 // 4):
                    break
            t1 = _tiempo()
            while True:
                t2 = _tiempo()
                if t2 != t1:
                    break
            q1, q2 = forma.format(n=n1), forma.format(n=n2)
            claim = f"{t1}, {entidad} had {q1}."
            filas = [
                {"claim": claim, "evidence": f"{t1}, {entidad} had {q1}.", "label": "SUPPORTS"},
                {"claim": claim, "evidence": f"{t1}, {entidad} had {q2}.", "label": "REFUTES"},
                {"claim": claim, "evidence": f"{t2}, {entidad} had {q2}.", "label": "NOT ENOUGH INFO"},
            ]
            for fila in filas:
                salida.write(json.dumps({**fila, "origen": "temporal"}, ensure_ascii=False) + "\n")
                generados[fila["label"]] += 1
    for etiqueta, n in generados.items():
        print(f"  {etiqueta}: {n}")
    print(f"[temporal] {sum(generados.values())} pares → {args.salida}")


if __name__ == "__main__":
    main()

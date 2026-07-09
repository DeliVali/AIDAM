"""Denial-pattern pairs: teach that "X denied reports that Y" refutes Y.

The traced gap (AVeriTeC-100 offline, 2026-07-08, Pogba case): passages
carrying an explicit denial ("he said he will take legal action after
reports claimed he had retired") were ALL judged NEUTRAL by the verifier —
"subject denies Y" is a meta-level negation that doesn't look like textbook
NLI contradiction, so the one passage stating the rumor directly won by
default. On the full 500 set, misread Refuted claims are the largest error
mass (39 Refuted→Supported + 29 Refuted→NEI).

Shortcut-proofing (the v4/v7 lesson: an unbalanced or vocabulary-separable
set teaches a bias, not a skill): every template appears with ALL THREE
labels in identical surface structure, so denial vocabulary alone predicts
nothing — only the relationship between the denied content and the claim
does:
  - "Officials denied reports that {Y}."   + claim Y → REFUTES
  - "Officials denied reports that {Z}."   + claim Y → NOT ENOUGH INFO
  - "Officials confirmed reports that {Y}." + claim Y → SUPPORTS

Claims come from VitaminC train (real-world-adjacent, varied topics); Z is
a different claim from the same shuffled pool.

Output: data/local/denial_pairs.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from datasets import load_dataset

SALIDA = Path("data/local/denial_pairs.jsonl")
SEMILLA = 45

# Each template pairs a denial form with its confirmation twin — same
# structure, same length profile, opposite verb. {s} is the claim sentence.
_PLANTILLAS = [
    ("A spokesperson denied reports that {s}, calling them completely false.",
     "A spokesperson confirmed reports that {s}, calling them accurate."),
    ("Officials dismissed claims that {s} as a fabrication.",
     "Officials acknowledged that {s}, according to the statement."),
    ("He said he would take legal action over reports claiming that {s}.",
     "He stood by earlier statements affirming that {s}."),
    ("The organization rejected as baseless the allegation that {s}.",
     "The organization verified the report that {s}."),
    ("Representatives called the story that {s} a hoax and demanded a retraction.",
     "Representatives corroborated the story that {s} in a press briefing."),
    ("She denied ever having said that {s}, describing the reports as invented.",
     "She reiterated publicly that {s}, standing by the reports."),
    ("The ministry issued a statement refuting rumors that {s}.",
     "The ministry issued a statement confirming that {s}."),
    ("Sources close to the matter said reports that {s} were untrue.",
     "Sources close to the matter said reports that {s} were accurate."),
]


def _frase(claim: str) -> str:
    """Claim as an embeddable clause: lowercase lead-in, no trailing period."""
    claim = claim.strip().rstrip(".")
    return claim[0].lower() + claim[1:] if claim else claim


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--por-etiqueta", type=int, default=4000, help="pairs per label")
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    base = load_dataset("tals/vitaminc", split="train").shuffle(seed=SEMILLA)
    claims = []
    vistos: set[str] = set()
    for fila in base:
        c = fila["claim"].strip()
        # Embeddable-clause filter: short declaratives without internal
        # sentence breaks read naturally inside "reports that {s}".
        if 20 <= len(c) <= 160 and c.count(".") <= 1 and c not in vistos:
            vistos.add(c)
            claims.append(c)
        if len(claims) >= args.por_etiqueta * 2 + 100:
            break

    aleatorio = random.Random(SEMILLA)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    generados = {"REFUTES": 0, "NOT ENOUGH INFO": 0, "SUPPORTS": 0}
    with args.salida.open("w") as salida:
        for i in range(args.por_etiqueta):
            y = claims[i]
            z = claims[len(claims) - 1 - i]  # disjoint slice: unrelated claim
            negar, confirmar = aleatorio.choice(_PLANTILLAS)
            filas = [
                {"claim": y, "evidence": negar.format(s=_frase(y)), "label": "REFUTES"},
                {"claim": y, "evidence": negar.format(s=_frase(z)), "label": "NOT ENOUGH INFO"},
                {"claim": y, "evidence": confirmar.format(s=_frase(y)), "label": "SUPPORTS"},
            ]
            for fila in filas:
                salida.write(json.dumps({**fila, "origen": "denial"}, ensure_ascii=False) + "\n")
                generados[fila["label"]] += 1
    for etiqueta, n in generados.items():
        print(f"  {etiqueta}: {n}")
    print(f"[denial] {sum(generados.values())} pares → {args.salida}")


if __name__ == "__main__":
    main()

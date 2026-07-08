"""Subtle factual errors generated with a local LLM (MiniCheck recipe).

MiniCheck showed that a small verifier reaches GPT-4 level by training on
*subtle* LLM-generated errors: claims almost identical to a true one where
only the key fact changes. This script builds them with a local LLM
(no APIs, no cost):

- REFUTES: minimally rewrite a supported claim so the same evidence now
  refutes it (change the number, date, name or direction).
- NOT ENOUGH INFO: add to the claim a specific detail the evidence doesn't
  mention (more specific than the evidence can prove).

Mechanical quality control: the generated claim must differ from the
original but keep most of its words (minimal edit).

Output: data/local/sinteticos_mimo.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from datasets import load_dataset

from aidam.preguntas import GeneradorPreguntas

SALIDA = Path("data/local/sinteticos_mimo.jsonl")
SEMILLA = 43  # different from the training seed: other VitaminC rows

_PROMPT_REFUTA = (
    "Rewrite the claim below with a MINIMAL edit so that the evidence now "
    "REFUTES it: change only the key fact (a number, date, name, place or "
    "direction). Keep every other word identical. Reply with ONLY the "
    "rewritten claim.\nEvidence: {evidencia}\nClaim: {claim}"
)
_PROMPT_NEI = (
    "Rewrite the claim below adding ONE specific detail that the evidence "
    "does NOT mention (so the evidence can no longer fully verify it). Keep "
    "the rest identical. Reply with ONLY the rewritten claim.\n"
    "Evidence: {evidencia}\nClaim: {claim}"
)


def _palabras(texto: str) -> set[str]:
    return set(re.findall(r"\w+", texto.lower()))


_PREFIJOS = re.compile(r"^\s*(rewritten claim|claim|new claim|answer)\s*:\s*", re.IGNORECASE)


def _limpiar(generada: str) -> str:
    """Strips LLM formatting artifacts: 'Rewritten claim:'-style prefixes,
    markdown and quotes (measured: they leaked into the first generated batch)."""
    generada = _PREFIJOS.sub("", generada.strip())
    generada = generada.replace("**", "").strip().strip('"').strip()
    return generada


def _edicion_minima(original: str, generada: str) -> bool:
    """Is the rewrite a valid minimal edit?"""
    if not generada or generada.lower() == original.lower():
        return False
    po, pg = _palabras(original), _palabras(generada)
    if not po or not pg:
        return False
    solape = len(po & pg) / len(po | pg)
    return 0.5 <= solape < 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max", type=int, default=4_000, help="total pairs to generate")
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    generador = GeneradorPreguntas()
    base = (
        load_dataset("tals/vitaminc", split="train")
        .filter(lambda f: f["label"] == "SUPPORTS")
        .shuffle(seed=SEMILLA)
    )

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    hechos = 0
    with args.salida.open("w") as salida:
        for indice, fila in enumerate(base):
            if hechos >= args.max:
                break
            objetivo = "REFUTES" if hechos % 2 == 0 else "NOT ENOUGH INFO"
            plantilla = _PROMPT_REFUTA if objetivo == "REFUTES" else _PROMPT_NEI
            prompt = plantilla.format(
                evidencia=fila["evidence"][:600], claim=fila["claim"][:300]
            )
            generada = generador._responder(prompt, max_tokens=120, temperature=0.4)
            generada = _limpiar(generada.strip().splitlines()[0]) if generada.strip() else ""
            if not _edicion_minima(fila["claim"], generada):
                continue
            salida.write(
                json.dumps(
                    {
                        "claim": generada,
                        "evidence": fila["evidence"],
                        "label": objetivo,
                        "origen": "sintetico-mimo",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            salida.flush()
            hechos += 1
            if hechos % 200 == 0:
                print(f"[sinteticos] {hechos}/{args.max} (fila {indice})")
    print(f"[sinteticos] {hechos} pares generados → {args.salida}")


if __name__ == "__main__":
    main()

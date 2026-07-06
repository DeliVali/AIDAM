"""Errores factuales sutiles generados con LLM local (receta MiniCheck).

MiniCheck demostró que un verificador pequeño alcanza nivel GPT-4 entrenando
con errores *sutiles* generados por un LLM: afirmaciones casi idénticas a una
verdadera donde solo cambia el dato clave. Este script los fabrica con
MiMo-7B-RL local (sin APIs, sin costo):

- REFUTES: reescribir mínimamente una afirmación sustentada para que la misma
  evidencia ahora la refute (cambia el número, la fecha, el nombre, el sentido).
- NOT ENOUGH INFO: añadir a la afirmación un detalle específico que la
  evidencia no menciona (más específica de lo que la evidencia puede probar).

Control de calidad mecánico: la afirmación generada debe diferir de la
original pero conservar la mayor parte de sus palabras (edición mínima).

Salida: data/local/sinteticos_mimo.jsonl con {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from datasets import load_dataset

from aidam.preguntas import GeneradorPreguntas

SALIDA = Path("data/local/sinteticos_mimo.jsonl")
SEMILLA = 43  # distinta de la de entrenamiento: otras filas de VitaminC

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


def _edicion_minima(original: str, generada: str) -> bool:
    """¿La reescritura es una edición mínima válida?"""
    generada = generada.strip().strip('"')
    if not generada or generada.lower() == original.lower():
        return False
    po, pg = _palabras(original), _palabras(generada)
    if not po or not pg:
        return False
    solape = len(po & pg) / len(po | pg)
    return 0.5 <= solape < 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max", type=int, default=4_000, help="pares totales a generar")
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
            generada = generada.strip().splitlines()[0].strip() if generada.strip() else ""
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

"""In-domain pairs from the AVeriTeC TRAIN split (never dev: no leakage).

The verifier was trained on Wikipedia-style pairs (VitaminC/MNLI); AVeriTeC
claims are real-world viral statements with QA-shaped gold evidence — a
style gap measured on every eval. This script converts each train claim's
gold question-answer evidence into (evidence, claim) NLI pairs:

- evidence = the claim's gold QA lines joined ("Q A. explanation"), the same
  shape the winning shared-task systems feed their classifiers,
- label = the claim's verdict (Supported→SUPPORTS, Refuted→REFUTES,
  Not Enough Evidence→NOT ENOUGH INFO); Conflicting claims are skipped —
  their evidence mixes both sides and would teach noise.

Repetition (--repetir) upweights the ~2.9k in-domain pairs against the
~210k generic mix so the style actually registers.

Output: data/local/averitec_train_pairs.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ENTRADA = Path("data/local/averitec_train.json")
SALIDA = Path("data/local/averitec_train_pairs.jsonl")

_MAPA = {
    "Supported": "SUPPORTS",
    "Refuted": "REFUTES",
    "Not Enough Evidence": "NOT ENOUGH INFO",
}


def _texto_qa(pregunta: dict) -> str:
    """One gold QA as an evidence line."""
    partes = [pregunta.get("question", "").strip().rstrip("?") + "?"]
    for respuesta in pregunta.get("answers", []):
        texto = (respuesta.get("answer") or "").strip()
        explicacion = (respuesta.get("boolean_explanation") or "").strip()
        if texto:
            partes.append(texto if texto.endswith(".") else texto + ".")
        if explicacion:
            partes.append(explicacion if explicacion.endswith(".") else explicacion + ".")
    return " ".join(p for p in partes if p)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--salida", type=Path, default=SALIDA)
    parser.add_argument("--repetir", type=int, default=3, help="copies of each pair in the mix")
    args = parser.parse_args()

    datos = json.loads(args.entrada.read_text())
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    generados = 0
    with args.salida.open("w") as salida:
        for ejemplo in datos:
            etiqueta = _MAPA.get(ejemplo["label"])
            if etiqueta is None:  # Conflicting: mixed evidence, skipped
                continue
            lineas = [_texto_qa(p) for p in ejemplo.get("questions", [])]
            evidencia = " ".join(l for l in lineas if len(l) > 10)
            if len(evidencia) < 40:
                continue
            registro = json.dumps(
                {
                    "claim": ejemplo["claim"],
                    "evidence": evidencia[:4000],
                    "label": etiqueta,
                    "origen": "averitec-train",
                },
                ensure_ascii=False,
            )
            for _ in range(args.repetir):
                salida.write(registro + "\n")
            generados += 1
    print(f"[averitec-pares] {generados} claims → {generados * args.repetir} pares → {args.salida}")


if __name__ == "__main__":
    main()

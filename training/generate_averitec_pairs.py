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

Class balancing (--balancear, on by default): AVeriTeC's raw label
distribution is 62% Refuted / 30% Supported / 10% NEI. Feeding that
imbalance into training taught v4 a REFUTES shortcut — verified on the same
gold evidence, a trivially true claim ("Amy Coney Barrett was confirmed...")
got 3 voices, confidence 1.00, predicted Refuted anyway. Each label is
capped at the minority class count so the claim-STYLE transfers without the
label-FREQUENCY prior.

Repetition (--repetir) upweights the balanced in-domain pairs against the
~210k generic mix so the style actually registers.

Output: data/local/averitec_train_pairs.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

ENTRADA = Path("data/local/averitec_train.json")
SEMILLA = 44
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
    parser.add_argument(
        "--balancear", action="store_true", default=True,
        help="cap each label at the minority class count (default on)",
    )
    parser.add_argument("--no-balancear", dest="balancear", action="store_false")
    args = parser.parse_args()

    datos = json.loads(args.entrada.read_text())
    args.salida.parent.mkdir(parents=True, exist_ok=True)

    por_etiqueta: dict[str, list[dict]] = defaultdict(list)
    for ejemplo in datos:
        etiqueta = _MAPA.get(ejemplo["label"])
        if etiqueta is None:  # Conflicting: mixed evidence, skipped
            continue
        lineas = [_texto_qa(p) for p in ejemplo.get("questions", [])]
        evidencia = " ".join(l for l in lineas if len(l) > 10)
        if len(evidencia) < 40:
            continue
        por_etiqueta[etiqueta].append(
            {"claim": ejemplo["claim"], "evidence": evidencia[:4000], "label": etiqueta}
        )

    aleatorio = random.Random(SEMILLA)
    for filas in por_etiqueta.values():
        aleatorio.shuffle(filas)
    if args.balancear:
        tope = min(len(filas) for filas in por_etiqueta.values())
        por_etiqueta = {etiqueta: filas[:tope] for etiqueta, filas in por_etiqueta.items()}
        print(f"[averitec-pares] balanceado a {tope} por clase (minoría)")

    generados = 0
    with args.salida.open("w") as salida:
        for filas in por_etiqueta.values():
            for fila in filas:
                registro = json.dumps(
                    {**fila, "origen": "averitec-train"}, ensure_ascii=False
                )
                for _ in range(args.repetir):
                    salida.write(registro + "\n")
                generados += 1
    for etiqueta, filas in por_etiqueta.items():
        print(f"  {etiqueta}: {len(filas)} claims")
    print(f"[averitec-pares] {generados} claims → {generados * args.repetir} pares → {args.salida}")


if __name__ == "__main__":
    main()

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
import re
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


SALIDA_NEI = Path("data/local/averitec_nei_pairs.jsonl")


def _generar_nei_cruzado(datos: list[dict], n: int) -> None:
    """Abstention pairs: claim_i vs the gold evidence of a nearby claim_j.

    Sampling is verified per pair: the neighbor must be topical (e5 cosine
    in [0.78, 0.90)) and must NOT share a majority of content words with
    claim_i's own evidence — a cheap guard against the same-event case
    where j's evidence WOULD be probative for i (the label-noise failure
    scidoc taught us to fear).
    """
    import numpy as np

    from aidam.vectores import _codificador

    ejemplos = []
    for ejemplo in datos:
        lineas = [_texto_qa(p) for p in ejemplo.get("questions", [])]
        evidencia = " ".join(l for l in lineas if len(l) > 10)
        if len(evidencia) >= 40:
            ejemplos.append({"claim": ejemplo["claim"], "evidence": evidencia[:4000]})
    print(f"[nei-cruzado] {len(ejemplos)} claims con evidencia; emparejando por significado…")

    codificar = _codificador()
    vectores = np.vstack([
        codificar([f"query: {e['claim']}" for e in ejemplos[i:i + 64]])
        for i in range(0, len(ejemplos), 64)
    ])
    similitud = vectores @ vectores.T
    np.fill_diagonal(similitud, -1.0)

    aleatorio = random.Random(SEMILLA)
    indices = list(range(len(ejemplos)))
    aleatorio.shuffle(indices)
    filas, usados = [], set()
    for i in indices:
        if len(filas) >= n:
            break
        candidatos_j = np.argsort(-similitud[i])
        for j in candidatos_j[:20]:
            s = similitud[i, j]
            if not (0.78 <= s < 0.90) or (i, j) in usados:
                continue
            palabras_i = set(re.findall(r"\w{5,}", ejemplos[i]["evidence"].lower()))
            palabras_j = set(re.findall(r"\w{5,}", ejemplos[j]["evidence"].lower()))
            if palabras_i and len(palabras_i & palabras_j) / len(palabras_i) > 0.4:
                continue  # same event: j's evidence could be probative for i
            filas.append({
                "claim": ejemplos[i]["claim"],
                "evidence": ejemplos[j]["evidence"],
                "label": "NOT ENOUGH INFO",
            })
            usados.add((i, j))
            break

    SALIDA_NEI.parent.mkdir(parents=True, exist_ok=True)
    with SALIDA_NEI.open("w") as salida:
        for fila in filas:
            salida.write(json.dumps(
                {**fila, "origen": "averitec-nei-cruzado"}, ensure_ascii=False) + "\n")
    print(f"[nei-cruzado] {len(filas)} pares NEI → {SALIDA_NEI}")


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
    parser.add_argument(
        "--nei-cruzado", type=int, default=0, metavar="N",
        help="v22 abstention pairs: N rows labeling claim_i against the gold "
        "evidence of a TOPICALLY NEARBY claim_j as NOT ENOUGH INFO. Neighbor "
        "band by e5 cosine [0.78, 0.90): same topic, different event — high "
        "enough to be hard, low enough that j's evidence is genuinely not "
        "probative for i (the scidoc lesson: same-document halves are "
        "redundant and teach credulity, so neighbors come from OTHER claims)",
    )
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

    if args.nei_cruzado:
        _generar_nei_cruzado(datos, args.nei_cruzado)

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

"""AIDAM verifier on FEVER (Wikipedia claim verification).

Third benchmark leg: FEVER's claims are short Wikipedia-derived statements —
a different register from both AVeriTeC (viral/political claims) and SciFact
(scientific abstracts). Oracle-retrieval setting like the SciFact eval: the
gold evidence sentences are handed to the verifier (via
copenlu/fever_gold_evidence, which inlines the sentence text — no 3 GB wiki
dump needed) and the predicted label is scored. Isolates judgment from
retrieval.

Balanced sample (default 999): FEVER dev is ~16k claims, far more than
needed to estimate accuracy; a fixed-seed balanced sample keeps runs fast
and class-fair.

Usage:
  python evaluation/eval_fever.py [--por-clase 333]
"""

from __future__ import annotations

import argparse
import random
from collections import Counter

from aidam.models import EtiquetaPar, Evidencia, HechoAtomico
from aidam.verify import crear_verificador

_MAPA = {"SUPPORTS": "sustenta", "REFUTES": "refuta", "NOT ENOUGH INFO": "nei"}
SEMILLA = 48


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--por-clase", type=int, default=333)
    args = parser.parse_args()

    from datasets import load_dataset

    datos = load_dataset("copenlu/fever_gold_evidence", split="validation")
    por_clase: dict[str, list] = {"SUPPORTS": [], "REFUTES": [], "NOT ENOUGH INFO": []}
    for ejemplo in datos:
        if ejemplo["label"] in por_clase:
            por_clase[ejemplo["label"]].append(ejemplo)
    aleatorio = random.Random(SEMILLA)
    muestra = []
    for etiqueta, ejemplos in por_clase.items():
        aleatorio.shuffle(ejemplos)
        muestra.extend(ejemplos[: args.por_clase])
        print(f"  {etiqueta}: {min(args.por_clase, len(ejemplos))} de {len(ejemplos)}")

    verificador = crear_verificador()
    confusion: Counter = Counter()
    aciertos = total = 0

    for ejemplo in muestra:
        oro = _MAPA[ejemplo["label"]]
        oraciones = [e[2] for e in ejemplo.get("evidence", []) if len(e) >= 3 and e[2]]
        if not oraciones:
            continue
        hecho = HechoAtomico(texto=ejemplo["claim"], origen=ejemplo["claim"])
        evidencias = [
            Evidencia(texto=o, url="", titulo="", dominio="wikipedia",
                      fuente="wikipedia", idioma="en")
            for o in oraciones if len(o) > 20
        ]
        if not evidencias:
            continue
        pares = verificador.juzgar(hecho, evidencias)
        fuertes = [p for p in pares if p.etiqueta is not EtiquetaPar.NO_CONCLUYE and p.prob >= 0.6]
        if not fuertes:
            pred = "nei"
        else:
            mejor = max(fuertes, key=lambda p: p.prob)
            pred = "sustenta" if mejor.etiqueta is EtiquetaPar.SUSTENTA else "refuta"
        total += 1
        aciertos += pred == oro
        confusion[(oro, pred)] += 1

    print(f"\n=== FEVER dev (oracle retrieval, muestra balanceada, {total} claims) ===")
    print(f"exactitud: {aciertos / max(total, 1):.1%}")
    f1s = []
    for clase in ("sustenta", "refuta", "nei"):
        tp = confusion.get((clase, clase), 0)
        fp = sum(v for (o, p), v in confusion.items() if p == clase and o != clase)
        fn = sum(v for (o, p), v in confusion.items() if o == clase and p != clase)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        f1s.append(f1)
        print(f"  {clase:9s} F1={f1:.3f}")
    print(f"F1 macro: {sum(f1s) / len(f1s):.3f}")
    for (oro, pred), n in confusion.most_common(9):
        marca = "✓" if oro == pred else "✗"
        print(f"  {marca} {oro} → {pred}: {n}")


if __name__ == "__main__":
    main()

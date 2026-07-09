"""AIDAM verifier on SciFact (scientific claim verification).

A second certified benchmark, structurally different from AVeriTeC: expert
claims judged against peer-reviewed abstracts. Tests whether the verifier's
comparative skill transfers to scientific language, and exercises the
medical/academic source design directly.

Oracle-retrieval setting (like LLM-AggreFact): hand the verifier the gold
cited abstract and score the label it predicts — isolates the verifier core
from live retrieval, so the number is about judgment, not search luck.
Label map: SUPPORT→sustenta, CONTRADICT→refuta, no-evidence claim→NEI.

Usage:
  python evaluation/eval_scifact.py [--split dev]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from aidam.models import EtiquetaPar, Evidencia, HechoAtomico
from aidam.verify import crear_verificador

RUTA = Path("data/local/scifact/data")


def _cargar_corpus() -> dict[int, list[str]]:
    corpus = {}
    for linea in (RUTA / "corpus.jsonl").read_text().splitlines():
        doc = json.loads(linea)
        corpus[doc["doc_id"]] = doc["abstract"]
    return corpus


def _etiqueta_oro(ejemplo: dict) -> str:
    """SciFact claim → our verdict vocabulary. Empty evidence = NEI; else the
    label of its cited document (SUPPORT/CONTRADICT, consistent per claim)."""
    evidencia = ejemplo.get("evidence") or {}
    if not evidencia:
        return "nei"
    etiquetas = {e["label"] for grupos in evidencia.values() for e in grupos}
    return "sustenta" if "SUPPORT" in etiquetas else "refuta"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="dev", choices=["dev", "train"])
    parser.add_argument("--limite", type=int, default=0, help="0 = all")
    args = parser.parse_args()

    corpus = _cargar_corpus()
    claims = [
        json.loads(l)
        for l in (RUTA / f"claims_{args.split}.jsonl").read_text().splitlines()
        if l.strip()
    ]
    if args.limite:
        claims = claims[: args.limite]

    verificador = crear_verificador()
    confusion: Counter = Counter()
    aciertos = 0
    total = 0

    for ejemplo in claims:
        oro = _etiqueta_oro(ejemplo)
        # Oracle evidence: the abstract(s) this claim cites. For NEI claims
        # (no gold evidence), use the cited-but-non-evidential docs if present,
        # else skip — there's no document to judge against.
        doc_ids = list((ejemplo.get("evidence") or {}).keys()) or [
            str(d) for d in ejemplo.get("cited_doc_ids", [])
        ]
        oraciones: list[str] = []
        for doc_id in doc_ids:
            oraciones.extend(corpus.get(int(doc_id), []))
        if not oraciones:
            continue

        hecho = HechoAtomico(texto=ejemplo["claim"], origen=ejemplo["claim"])
        evidencias = [
            Evidencia(texto=o, url="", titulo="", dominio="scifact",
                      fuente="academica", idioma="en")
            for o in oraciones if len(o) > 20
        ]
        pares = verificador.juzgar(hecho, evidencias)
        # Claim-level: the strongest non-neutral judgement across the abstract's
        # sentences decides; if none clears signal, the claim is NEI.
        fuertes = [p for p in pares if p.etiqueta is not EtiquetaPar.NO_CONCLUYE and p.prob >= 0.6]
        if not fuertes:
            pred = "nei"
        else:
            mejor = max(fuertes, key=lambda p: p.prob)
            pred = "sustenta" if mejor.etiqueta is EtiquetaPar.SUSTENTA else "refuta"

        total += 1
        aciertos += pred == oro
        confusion[(oro, pred)] += 1

    print(f"\n=== SciFact {args.split} (oracle retrieval, {total} claims) ===")
    print(f"exactitud: {aciertos / max(total, 1):.1%}")
    clases = ["sustenta", "refuta", "nei"]
    f1s = []
    for clase in clases:
        tp = confusion.get((clase, clase), 0)
        fp = sum(v for (o, p), v in confusion.items() if p == clase and o != clase)
        fn = sum(v for (o, p), v in confusion.items() if o == clase and p != clase)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        f1s.append(f1)
        oro_n = sum(v for (o, _p), v in confusion.items() if o == clase)
        print(f"  {clase:9s} F1={f1:.3f}  (oro {oro_n})")
    print(f"F1 macro: {sum(f1s) / len(f1s):.3f}")
    print("confusión (oro → pred):")
    for (oro, pred), n in confusion.most_common():
        marca = "✓" if oro == pred else "✗"
        print(f"  {marca} {oro} → {pred}: {n}")


if __name__ == "__main__":
    main()

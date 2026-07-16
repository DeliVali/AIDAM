"""Aggregation-parameter sweeps on cached verifier pairs.

The aggregator's constants (UMBRAL_SENAL, DOMINANCIA, reliability priors)
were each born from a measured failure but have never been *swept* — every
configuration cost a full eval run (retrieval + NLI ≈ 1.5 h per point on
the 500). This caches the expensive part once (decompose → offline retrieve
→ question-driven search → NLI pairs, per claim) and then re-aggregates in
milliseconds per configuration.

Overfitting guard: tune on a --desde/--hasta slice DISJOINT from the claims
used to report results; only the winning configuration gets a full run.

Usage:
  python evaluation/sweep_aggregation.py --cachear --desde 100 --hasta 300
  python evaluation/sweep_aggregation.py --barrer --desde 100 --hasta 300
"""

from __future__ import annotations

import argparse
import itertools
import json
import pickle
from pathlib import Path

def _ruta_cache() -> Path:
    """Cache keyed BY MODEL. The flat cache silently mixed two models'
    judgements (200 files from the v10 era + 302 from v20, found
    2026-07-15): a sweep over that chimera tuned constants for a model
    that does not exist. One subdirectory per verifier checkpoint."""
    import os

    modelo = Path(
        os.environ.get("AIDAM_MODELO_VERIFICADOR", "models/verificador-v0")
    ).name
    return Path("data/local/pares_cache") / modelo


RUTA_CACHE = _ruta_cache()
RUTA_DEV = Path("data/local/averitec_dev.json")

A_AVERITEC = {
    "sustentado": "Supported",
    "refutado": "Refuted",
    "evidencia_insuficiente": "Not Enough Evidence",
    "evidencia_contradictoria": "Conflicting Evidence/Cherrypicking",
}


def cachear(desde: int, hasta: int) -> None:
    """Runs the expensive pipeline stages once per claim and pickles the pairs."""
    from aidam.decompose import descomponer
    from aidam.pipeline import _generador_preguntas
    from aidam.verify import crear_verificador
    from evaluation.knowledge_store import crear_recuperador_offline

    dev = json.loads(RUTA_DEV.read_text())
    verificador = crear_verificador()
    generador = _generador_preguntas()
    RUTA_CACHE.mkdir(parents=True, exist_ok=True)

    for indice in range(desde, hasta):
        destino = RUTA_CACHE / f"{indice}.pkl"
        if destino.exists():
            continue
        claim = dev[indice]
        buscar = crear_recuperador_offline(indice, Path("data/local/knowledge_store/dev"))
        hechos_pares = []
        for hecho in descomponer(claim["claim"]):
            evidencias = buscar(hecho, lang="en")
            if generador is not None:
                for pregunta in generador.preguntas(hecho.texto, n=2, lang="en"):
                    evidencias.extend(buscar_pregunta(buscar, pregunta))
            pares = verificador.juzgar(hecho, evidencias) if evidencias else []
            hechos_pares.append((hecho, pares))
        destino.write_bytes(pickle.dumps({"oro": claim["label"], "hechos": hechos_pares}))
        print(f"[cache] {indice} listo ({sum(len(p) for _, p in hechos_pares)} pares)")


def buscar_pregunta(buscar, pregunta: str):
    from aidam.models import HechoAtomico

    return buscar(HechoAtomico(texto=pregunta, origen=pregunta), lang="en")


def evaluar_config(indices: list[int], **params) -> dict:
    """Re-aggregates cached pairs under parameter overrides and scores."""
    from aidam import aggregate

    originales = {k: getattr(aggregate, k) for k in params}
    try:
        for k, v in params.items():
            setattr(aggregate, k, v)
        aciertos, total = 0, 0
        confusion: dict[tuple[str, str], int] = {}
        for indice in indices:
            ruta = RUTA_CACHE / f"{indice}.pkl"
            if not ruta.exists():
                continue
            datos = pickle.loads(ruta.read_bytes())
            veredictos = [
                aggregate.agregar_hecho(hecho, pares) for hecho, pares in datos["hechos"]
            ]
            informe = aggregate.agregar_informe("", veredictos)
            prediccion = A_AVERITEC[informe.veredicto.value]
            total += 1
            aciertos += prediccion == datos["oro"]
            confusion[(datos["oro"], prediccion)] = confusion.get((datos["oro"], prediccion), 0) + 1
        clases = set(A_AVERITEC.values())
        f1s = []
        for clase in clases:
            tp = confusion.get((clase, clase), 0)
            fp = sum(v for (o, p), v in confusion.items() if p == clase and o != clase)
            fn = sum(v for (o, p), v in confusion.items() if o == clase and p != clase)
            prec = tp / (tp + fp) if tp + fp else 0.0
            rec = tp / (tp + fn) if tp + fn else 0.0
            f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
        return {"exactitud": aciertos / max(total, 1), "f1_macro": sum(f1s) / len(f1s), "n": total}
    finally:
        for k, v in originales.items():
            setattr(aggregate, k, v)


def barrer(desde: int, hasta: int) -> None:
    indices = list(range(desde, hasta))
    base = evaluar_config(indices)
    print(f"base: exactitud {base['exactitud']:.3f} · F1 {base['f1_macro']:.3f} (n={base['n']})")
    rejilla = {
        "DOMINANCIA": [1.5, 2.0, 2.5, 3.0],
        "UMBRAL_SENAL": [0.55, 0.60, 0.65],
        "PESO_DESMENTIDO": [0.15, 0.25, 0.40],
    }
    mejores = []
    for valores in itertools.product(*rejilla.values()):
        params = dict(zip(rejilla.keys(), valores))
        r = evaluar_config(indices, **params)
        mejores.append((r["exactitud"], r["f1_macro"], params))
    mejores.sort(key=lambda t: (t[0], t[1]), reverse=True)
    print("top 8 por exactitud:")
    for exactitud, f1, params in mejores[:8]:
        print(f"  {exactitud:.3f} · F1 {f1:.3f} · {params}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cachear", action="store_true")
    parser.add_argument("--barrer", action="store_true")
    parser.add_argument("--desde", type=int, default=100)
    parser.add_argument("--hasta", type=int, default=300)
    args = parser.parse_args()
    if args.cachear:
        cachear(args.desde, args.hasta)
    if args.barrer:
        barrer(args.desde, args.hasta)


if __name__ == "__main__":
    main()

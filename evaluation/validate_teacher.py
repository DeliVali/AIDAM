"""Validate the scaffolded teacher OFF-test before any distillation run.

Measured so far: the local 8B judging WHOLE claims is credulous (BAcc
53.4 on AggreFact-CNN, catches 9.3% of unsupported claims) — distilling
from it as-is would teach credulity. The scaffold hypothesis: judging
fact-by-fact (decompose, then one yes/no per atomic fact, claim supported
iff every fact is) removes the failure mode, because per-fact questions
are short and specific.

Pre-registered gate (docs/ROADMAP.md, declared before the numbers): the
scaffolded teacher must reach BAcc >= 80 on the held-out D2C dev to
license the distillation harvest. The dev pairs carry construction
labels and were never trained on; no benchmark data is touched.

Reports both modes on the same pairs: whole-claim judge (the credulous
baseline) and scaffolded judge (decompose + per-fact + min).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

from aidam.questions import GeneradorPreguntas

_PROMPT_JUEZ = (
    "Document:\n{doc}\n\nClaim: {claim}\n\nDoes the document fully support "
    "the claim? Every fact in the claim must be stated in or clearly implied "
    "by the document. Reply with ONLY one word: yes or no."
)


def _si_o_no(generador: GeneradorPreguntas, doc: str, claim: str) -> int | None:
    crudo = generador._responder(
        _PROMPT_JUEZ.format(doc=doc[:6000], claim=claim),
        max_tokens=120, temperature=0.0,
    )
    m = re.search(r"\b(yes|no)\b", crudo.lower()) if crudo else None
    return {"yes": 1, "no": 0}.get(m.group(1)) if m else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pares", type=Path,
                        default=Path("data/local/multisent_dev_pairs.jsonl"))
    parser.add_argument("--decomp", type=Path,
                        default=Path("data/local/decomp_multisent_dev.jsonl"))
    parser.add_argument("--salida", type=Path,
                        default=Path("data/local/teacher_dev_verdicts.jsonl"))
    args = parser.parse_args()

    todas = [json.loads(l) for l in args.pares.open()]
    # same index convention as decompose_claims --pares (row in file)
    filas = [(i, f) for i, f in enumerate(todas)
             if f["label"] in ("SUPPORTS", "REFUTES")]
    descomp = {d["idx"]: d for d in map(json.loads, args.decomp.open())}

    generador = GeneradorPreguntas()
    oro, entero, andamiado = [], [], []
    with args.salida.open("w") as salida:
        for n, (i, f) in enumerate(filas):
            if i not in descomp:
                continue
            assert descomp[i]["label"] == int(f["label"] == "SUPPORTS")
            v_entero = _si_o_no(generador, f["evidence"], f["claim"])
            hechos = descomp[i]["hechos"] or [f["claim"]]
            v_hechos = [_si_o_no(generador, f["evidence"], h) for h in hechos]
            validos = [v for v in v_hechos if v is not None]
            v_min = min(validos) if validos else None
            if v_entero is None or v_min is None:
                continue
            oro.append(int(f["label"] == "SUPPORTS"))
            entero.append(v_entero)
            andamiado.append(v_min)
            salida.write(json.dumps({
                "idx": i, "label": oro[-1], "entero": v_entero,
                "hechos": v_hechos, "andamiado": v_min}) + "\n")
            if (n + 1) % 100 == 0:
                print(f"[maestro] {n + 1}/{len(filas)}")

    oro = np.array(oro)

    def bacc(pred):
        pred = np.array(pred)
        tpr = (pred[oro == 1] == 1).mean()
        tnr = (pred[oro == 0] == 0).mean()
        return (tpr + tnr) / 2, tpr, tnr

    for nombre, pred in (("juez claim entero", entero),
                         ("juez andamiado (hechos+min)", andamiado)):
        b, tpr, tnr = bacc(pred)
        print(f"[maestro] {nombre}: BAcc {b:.1%}  (label=1: {tpr:.1%}, label=0: {tnr:.1%})")
    print(f"[maestro] puerta pre-registrada: BAcc >= 80 para licenciar la destilación")


if __name__ == "__main__":
    main()

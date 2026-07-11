"""D2C long-document pairs: the actual MiniCheck recipe, with a local LLM.

v12 proved two things at once: the long-document register lever is real
(AggreFact-CNN +4 even from contaminated data) and mined shortcuts are
dangerous (DocNLI's relabeled FEVER contradictions taught anti-refutation;
see ROADMAP 2026-07-10). The clean version is what MiniCheck actually did —
generate the data purpose-built (doc-to-claim, "D2C"):

For each real news article chunk (CNN/DailyMail train split — the same
register as AggreFact-CNN, our weakest sub-dataset):
  1. SUPPORTS: the LLM writes a claim that requires composing facts from
     MULTIPLE sentences of the chunk (single-sentence copies are rejected
     by a mechanical multi-sentence check).
  2. REFUTES: the LLM minimally corrupts that claim (flip a fact); the
     edit-distance QC from generate_synthetic_llm.py applies.
  3. NOT ENOUGH INFO: the same claim paired with a DIFFERENT chunk of the
     same article (topically aligned, not probative — mechanical, free).

All three labels share the claim text and register — the shortcut-proofing
recipe that v8 established.

Output: data/local/longdoc_pairs.jsonl with {claim, evidence, label}.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from aidam.questions import GeneradorPreguntas
from training.generate_synthetic_llm import _edicion_minima, _limpiar

SALIDA = Path("data/local/longdoc_pairs.jsonl")
SEMILLA = 51

_PROMPT_CLAIM = (
    "Read the article excerpt below. Write ONE factual claim (a single "
    "sentence, max 35 words) that is fully supported by the excerpt and "
    "combines information from at least two different sentences. Reply with "
    "ONLY the claim.\nExcerpt:\n{doc}"
)
_PROMPT_CORRUPT = (
    "Rewrite the claim below with a MINIMAL edit so the excerpt now REFUTES "
    "it: change one key fact (a number, name, place, outcome or direction). "
    "Keep every other word identical. Reply with ONLY the rewritten claim.\n"
    "Excerpt:\n{doc}\nClaim: {claim}"
)


def _trocear_doc(texto: str, objetivo: int = 1500) -> list[str]:
    """Article → chunks of ~objetivo chars, split on sentence boundaries."""
    frases = re.split(r"(?<=[.!?])\s+", texto)
    trozos, actual = [], ""
    for frase in frases:
        if actual and len(actual) + len(frase) > objetivo:
            trozos.append(actual.strip())
            actual = frase
        else:
            actual = f"{actual} {frase}".strip()
    if len(actual) > 400:
        trozos.append(actual.strip())
    return trozos


def _usa_varias_frases(claim: str, doc: str) -> bool:
    """Reject claims copiable from a single document sentence: every content
    word appearing together in one sentence means no composition happened."""
    palabras = set(re.findall(r"\w{5,}", claim.lower()))
    if len(palabras) < 3:
        return False
    for frase in re.split(r"(?<=[.!?])\s+", doc.lower()):
        if sum(1 for p in palabras if p in frase) >= len(palabras) - 1:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grupos", type=int, default=1500,
                        help="article chunks to process (3 pairs each)")
    parser.add_argument("--salida", type=Path, default=SALIDA)
    parser.add_argument("--fuente", default="cnndm",
                        choices=["cnndm", "xsum", "pubmed"],
                        help="article source: cnndm (CNN/DailyMail), xsum "
                        "(BBC — the AggreFact-XSum register) or pubmed "
                        "(MedRAG abstracts — the expert/technical register "
                        "ExpertQA and SciFact expose as our weakest)")
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    args = parser.parse_args()

    from datasets import load_dataset

    if args.fuente == "xsum":
        articulos = load_dataset("EdinburghNLP/xsum", split="train",
                                 streaming=True, trust_remote_code=False)
        articulos = articulos.shuffle(seed=args.semilla, buffer_size=10_000)
        articulos = ({"article": a["document"]} for a in articulos)
    elif args.fuente == "pubmed":
        articulos = load_dataset("MedRAG/pubmed", split="train", streaming=True)
        articulos = articulos.shuffle(seed=args.semilla, buffer_size=10_000)
        articulos = ({"article": a["content"]} for a in articulos)
    else:
        articulos = load_dataset("abisee/cnn_dailymail", "3.0.0", split="train",
                                 streaming=True).shuffle(seed=args.semilla, buffer_size=10_000)
    # Abstracts run ~1.3k chars (median): halve the chunk target so the
    # doc-swap NEI still gets two topically-aligned chunks — same study,
    # different section, the hardest kind of not-probative pair.
    objetivo_trozo = 700 if args.fuente == "pubmed" else 1500
    generador = GeneradorPreguntas()

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    hechos = 0
    with args.salida.open("a") as salida:
        for articulo in articulos:
            if hechos >= args.grupos:
                break
            trozos = _trocear_doc(articulo["article"], objetivo_trozo)
            if len(trozos) < 2:
                continue
            doc, doc_otro = trozos[0], trozos[1]

            crudo = generador._responder(
                _PROMPT_CLAIM.format(doc=doc[:1800]), max_tokens=80, temperature=0.4
            )
            claim = _limpiar(crudo.strip().splitlines()[0]) if crudo.strip() else ""
            if not (30 < len(claim) < 260) or not _usa_varias_frases(claim, doc):
                continue

            crudo = generador._responder(
                _PROMPT_CORRUPT.format(doc=doc[:1800], claim=claim),
                max_tokens=80, temperature=0.4,
            )
            corrupta = _limpiar(crudo.strip().splitlines()[0]) if crudo.strip() else ""
            if not _edicion_minima(claim, corrupta):
                continue

            for fila in (
                {"claim": claim, "evidence": doc, "label": "SUPPORTS"},
                {"claim": corrupta, "evidence": doc, "label": "REFUTES"},
                {"claim": claim, "evidence": doc_otro, "label": "NOT ENOUGH INFO"},
            ):
                salida.write(json.dumps(
                    {**fila, "origen": f"d2c-{args.fuente}"}, ensure_ascii=False) + "\n")
            salida.flush()
            hechos += 1
            if hechos % 50 == 0:
                print(f"[d2c] {hechos}/{args.grupos} grupos")
    print(f"[d2c] {hechos} grupos → {hechos * 3} pares → {args.salida}")


if __name__ == "__main__":
    main()

"""Citation-support protocol (ALCE-style) for AIDAM's answer mode.

BENCHMARKS.md Tier 3: the answer mode's product promise is that every factual
sentence it shows comes from the source it cites. This harness turns that
promise into a number, judged by the RESIDENT NLI verifier — the same
instrument as the grounding gate (`razonador.revisar_respuesta`) at the same
threshold (`UMBRAL_SUSTENTO`) — so the metric audits the product mechanism
directly instead of a proxy for it.

Two numbers, both reported (ALCE's pair, adapted to an answer that cites one
primary source plus corroborating domains):

  citation recall     % of factual answer sentences entailed by >= 1 of the
                      sources the answer cites
  citation precision  % of cited sources that entail >= 1 sentence of the
                      answer they are attached to

Recall catches «asserted something its source does not say» (the
hallucination we exist to prevent); precision catches «padded the answer with
citations that do not back it» (citation theater). Both matter: an answer
that cites nothing scores 0 recall, one that cites everything scores low
precision.

Substrate: AVeriTeC dev questions + the organizers' offline knowledge store.
Frozen evidence on purpose — live search degrades cumulatively inside a
single run (docs/ROADMAP.md Phase 2: 45%→41%→38%→39%→22% tracking exhausted
quota, not quality), and a reproducible number needs a fixed substrate.

Usage:
  python evaluation/eval_citation_support.py --limite 50
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from aidam.agente.razonador import UMBRAL_SUSTENTO
from aidam.agente.sintesis import _frases, responder_pregunta
from aidam.models import Evidencia, HechoAtomico
from aidam.verify import crear_verificador

RUTA_DEV = Path("data/local/averitec_dev.json")
RUTA_STORE = Path("data/local/knowledge_store/dev")

_FRASES_PARTIR = re.compile(r"(?<=[.!?»])\s+")
# Same shape filter the grounding gate applies before it judges a sentence.
_MIN_FRASE, _MAX_FRASE = 25, 300


def _partir_respuesta(
    respuesta: str, lang: str
) -> tuple[list[str], list[str], list[str]]:
    """(factual sentences, primary citations, secondary citations).

    Parses the real product output rather than reconstructing it: the answer
    is what the user sees, so the metric must be computed on exactly that.

    The two citation kinds are kept apart on purpose — they make *different*
    claims. «Source: X» asserts that X backs the sentence; «Also reported by:
    Y» only asserts that Y covers the topic. Scoring them as one number would
    blame the product for a distinction it never made.
    """
    etiqueta_fuente = _frases(lang)["fuente"]
    etiqueta_tambien = _frases(lang)["tambien"]
    primarios: list[str] = []
    secundarios: list[str] = []
    cuerpo: list[str] = []
    en_codigo = False
    for linea in respuesta.split("\n"):
        if linea.strip().startswith("```"):
            en_codigo = not en_codigo
            continue
        if en_codigo:
            continue  # code blocks are quoted verbatim; not factual prose
        if linea.startswith(f"{etiqueta_fuente}: "):
            resto = linea[len(etiqueta_fuente) + 2:]
            primarios.append(resto.split(" — ")[0].strip())
            continue
        if linea.startswith(f"{etiqueta_tambien}: "):
            resto = linea[len(etiqueta_tambien) + 2:].rstrip(".")
            secundarios.extend(d.strip() for d in resto.split(",") if d.strip())
            continue
        cuerpo.append(linea)

    frases = []
    for frase in _FRASES_PARTIR.split(" ".join(cuerpo)):
        frase = frase.strip()
        if _MIN_FRASE <= len(frase) <= _MAX_FRASE and not frase.endswith("?"):
            frases.append(frase)

    def _unicos(dominios: list[str], ya: set[str]) -> list[str]:
        salida = []
        for d in dominios:
            if d and d not in ya:
                ya.add(d)
                salida.append(d)
        return salida

    vistos: set[str] = set()
    return frases, _unicos(primarios, vistos), _unicos(secundarios, vistos)


def _mejor_sustento(
    verificador, pasajes: list[str], frase: str, tope: int
) -> float:
    """Best entailment of `frase` across a cited domain's passages.

    One call per passage: `puntuar_entailment` batches hypotheses against a
    single premise, and here the premise is what varies. Fine at this scale
    (the `--pasajes-por-dominio` cap bounds it); batching would mean reaching
    into the verifier's private `_predecir_lote`, not worth it for an
    offline harness.
    """
    if not pasajes:
        return 0.0
    return max(
        (max(verificador.puntuar_entailment(p, [frase])) for p in pasajes[:tope]),
        default=0.0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limite", type=int, default=50,
                        help="number of AVeriTeC dev claims to draw questions from")
    parser.add_argument("--preguntas-por-claim", type=int, default=1)
    parser.add_argument("--umbral", type=float, default=UMBRAL_SUSTENTO,
                        help="entailment threshold; defaults to the grounding gate's")
    parser.add_argument("--max-pasajes", type=int, default=25)
    parser.add_argument("--pasajes-por-dominio", type=int, default=5,
                        help="cap on passages scored per cited domain")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--gate-secundarias", action="store_true",
                        help="pass the NLI to responder_pregunta so «also covered "
                             "by» domains are entailment-gated (the fix under test)")
    parser.add_argument("--salida", default="", help="optional JSONL trace path")
    args = parser.parse_args()

    from evaluation.knowledge_store import crear_recuperador_offline

    ejemplos = json.loads(RUTA_DEV.read_text())[: args.limite]
    verificador = crear_verificador()

    n_frases = n_frases_ok = 0
    n_prim = n_prim_ok = 0
    n_sec = n_sec_ok = 0
    n_respuestas = n_sin_evidencia = 0
    trazas = []
    sin_respuesta = _frases(args.lang)["sin_respuesta"]

    for indice, ejemplo in enumerate(ejemplos):
        ruta_claim = RUTA_STORE / f"{indice}.json"
        if not ruta_claim.exists():
            continue
        recuperador = crear_recuperador_offline(
            indice, RUTA_STORE, max_pasajes=args.max_pasajes
        )
        preguntas = [q["question"] for q in (ejemplo.get("questions") or [])]
        for pregunta in preguntas[: args.preguntas_por_claim]:
            evidencias: list[Evidencia] = recuperador(
                HechoAtomico(texto=pregunta, origen=""), lang=args.lang
            )
            if not evidencias:
                continue
            respuesta = responder_pregunta(
                pregunta, evidencias, lang=args.lang,
                verificador=verificador if args.gate_secundarias else None,
            )
            if respuesta.strip() == sin_respuesta:
                n_sin_evidencia += 1
                continue
            n_respuestas += 1

            frases, primarios, secundarios = _partir_respuesta(respuesta, args.lang)
            dominios = primarios + secundarios
            por_dominio: dict[str, list[str]] = {}
            for e in evidencias:
                por_dominio.setdefault(e.dominio, []).append(e.texto)

            # sustento[(frase, dominio)] — computed once, used by both metrics.
            sustento: dict[tuple[int, str], float] = {}
            for i, frase in enumerate(frases):
                for dominio in dominios:
                    sustento[(i, dominio)] = _mejor_sustento(
                        verificador, por_dominio.get(dominio, []), frase,
                        args.pasajes_por_dominio,
                    )

            for i, frase in enumerate(frases):
                n_frases += 1
                mejor = max((sustento[(i, d)] for d in dominios), default=0.0)
                if mejor >= args.umbral:
                    n_frases_ok += 1
                elif args.salida:
                    trazas.append({"tipo": "frase_sin_sustento", "pregunta": pregunta,
                                   "frase": frase, "mejor": round(mejor, 3),
                                   "dominios": dominios})
            for clase, grupo in (("primaria", primarios), ("secundaria", secundarios)):
                for dominio in grupo:
                    mejor = max((sustento[(i, dominio)] for i in range(len(frases))),
                                default=0.0)
                    if clase == "primaria":
                        n_prim += 1
                        n_prim_ok += mejor >= args.umbral
                    else:
                        n_sec += 1
                        n_sec_ok += mejor >= args.umbral
                    if mejor < args.umbral and args.salida:
                        trazas.append({"tipo": f"cita_{clase}_sin_uso",
                                       "pregunta": pregunta, "dominio": dominio,
                                       "mejor": round(mejor, 3)})

    recall = n_frases_ok / n_frases if n_frases else 0.0
    prec_prim = n_prim_ok / n_prim if n_prim else 0.0
    prec_sec = n_sec_ok / n_sec if n_sec else 0.0
    f1 = (2 * recall * prec_prim / (recall + prec_prim)
          if recall + prec_prim else 0.0)

    print("\n=== Citation support (AVeriTeC dev questions, offline store) ===")
    print(f"answers scored:        {n_respuestas}"
          f"   (no-evidence answers skipped: {n_sin_evidencia})")
    print(f"threshold:             {args.umbral} (the grounding gate's)")
    print(f"citation recall:       {recall:.1%}   ({n_frases_ok}/{n_frases} sentences"
          f" entailed by a cited source)")
    print(f"precision (primary):   {prec_prim:.1%}   ({n_prim_ok}/{n_prim} «"
          f"{_frases(args.lang)['fuente']}» citations that back a sentence)")
    print(f"precision (secondary): {prec_sec:.1%}   ({n_sec_ok}/{n_sec} «"
          f"{_frases(args.lang)['tambien']}» domains that back a sentence)")
    print(f"F1 (recall × primary): {f1:.3f}")
    print("\nRead honestly: this answer mode is EXTRACTIVE — it quotes a retrieved\n"
          "sentence verbatim — so high recall is grounded by construction, not a\n"
          "surprise. The discriminating number is precision, and the secondary\n"
          "line is diagnostic: «also reported by» promises topical corroboration,\n"
          "so a low value there means those domains do not actually back the\n"
          "answer. The metric becomes load-bearing for recall once the LLM\n"
          "synthesiser (`sintesis.sintetizar`) writes the answer instead.")

    if args.salida and trazas:
        Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
        with open(args.salida, "w") as f:
            for t in trazas:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        print(f"\n{len(trazas)} failure traces → {args.salida}")


if __name__ == "__main__":
    main()

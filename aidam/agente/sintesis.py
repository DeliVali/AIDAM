"""Narrative synthesis: the LLM writes, it NEVER judges.

Architectural invariant (measured: LLM-as-sole-judge 24.0% vs the
aggregator's 58.0%): verdicts come from the NLI core + explicit aggregation.
The synthesizer receives only the deterministic evidence table and turns it
into prose; a post-hoc marker check drops any output that contradicts the
verdicts rather than letting it through softened or reversed.
"""

from __future__ import annotations

import re

from ..models import Informe, Veredicto

_PENSAMIENTO = re.compile(r"<think>.*?</think>", re.DOTALL)

# Post-LLM safeguard: if the synthesis contains a marker of the OPPOSITE
# verdict, it is discarded (the caller falls back to the table). Simple,
# auditable, and deliberately conservative.
_MARCADORES_CONTRARIOS: dict[Veredicto, tuple[str, ...]] = {
    Veredicto.SUSTENTADO: ("refutada", "refutado", "es falsa", "es falso", "refuted", "is false"),
    Veredicto.REFUTADO: (
        "sustentada", "sustentado", "es cierta", "es cierto", "es verdadera",
        "supported", "is true",
    ),
    Veredicto.CONTRADICTORIO: (),
    Veredicto.INSUFICIENTE: (),
}

_TITULO = {
    Veredicto.SUSTENTADO: "SUPPORTED",
    Veredicto.REFUTADO: "REFUTED",
    Veredicto.CONTRADICTORIO: "CONFLICTING EVIDENCE",
    Veredicto.INSUFICIENTE: "NOT ENOUGH EVIDENCE",
}


def tabla_evidencia(informe: Informe) -> str:
    """Deterministic rendering of the aggregated result — the ONLY thing the LLM sees."""
    lineas = [
        f"CLAIM: {informe.afirmacion}",
        f"VERDICT: {_TITULO[informe.veredicto]} (confidence {informe.confianza:.2f})",
    ]
    for vh in informe.hechos:
        lineas.append(f"- FACT: {vh.hecho.texto}")
        lineas.append(f"  verdict: {_TITULO[vh.veredicto]} (confidence {vh.confianza:.2f})")
        for etiqueta, pares in (("supports", vh.a_favor), ("refutes", vh.en_contra)):
            for par in pares[:3]:
                lineas.append(
                    f"  {etiqueta} ({par.prob:.2f}) [{par.evidencia.dominio}] "
                    f"{par.evidencia.url}\n    \"{par.evidencia.texto[:200]}\""
                )
    return "\n".join(lineas)


_INTERROGATIVOS = re.compile(
    r"^\s*(¿|qu[eé]\b|qui[eé]n|d[oó]nde|cu[aá]ndo|cu[aá]l|cu[aá]nt[oa]s?\b|c[oó]mo\b"
    r"|por qu[eé]|para qu[eé]|what\b|who\b|where\b|when\b|which\b|how\b|why\b)",
    re.IGNORECASE,
)


def es_pregunta(texto: str) -> bool:
    """Is the input a research question rather than a claim to verify?

    A question cannot be \"refuted\" — treating it as a claim produced the
    measured product failure of 2026-07-16 («¿dónde está la Mona Lisa?» →
    REFUTADO 75%). Questions route to answer mode: retrieve, rank by
    meaning, answer with the passage that contains the answer.
    """
    limpio = texto.strip()
    return limpio.endswith("?") or bool(_INTERROGATIVOS.match(limpio))


def responder_pregunta(pregunta: str, evidencias: list) -> str:
    """Evidence-grounded answer to a question, concise by construction.

    Ranks the retrieved passages by meaning against the question (the same
    computed-once embedder as the semantic memory; graceful order-preserving
    fallback without it) and answers with the best passage, cited. No LLM
    required; when the narrator LLM is active it may polish this, never
    replace its grounding.
    """
    utiles = [e for e in evidencias if e.texto.strip()]
    if not utiles:
        return ("No encontré evidencia para responder esta pregunta; "
                "conviene reformularla o intentar más tarde.")
    orden = utiles
    try:
        import numpy as np

        from ..vectores import _codificador

        codificar = _codificador()
        consulta = codificar([f"query: {pregunta}"])[0]
        matriz = codificar([f"passage: {e.texto[:1000]}" for e in utiles])
        puntajes = matriz @ consulta
        orden = [utiles[i] for i in np.argsort(-puntajes)]
    except Exception:
        pass
    mejor = orden[0]
    lineas = [f"Según {mejor.dominio}: «{mejor.texto[:220].strip()}…»", f"  {mejor.url}"]
    for extra in orden[1:3]:
        lineas.append(f"También: {extra.dominio} — {extra.url}")
    return "\n".join(lineas)


def respuesta_concisa(informe: Informe) -> str:
    """Deterministic one-breath answer: direct, grounded, never long.

    Jeffrey's product rule (2026-07-16): the user always gets an
    understandable answer — «No, X porque Y (fuente)» — never a bare
    label and never an essay. This template needs no LLM, costs nothing,
    and cannot contradict the verdict because it is BUILT from it; the
    optional LLM polish (sintetizar) obeys the same brevity contract.
    """
    def _mejor(pares):
        return max(pares, key=lambda p: p.prob, default=None)

    # the fact that decided the global verdict, and its strongest voice
    decisivos = [h for h in informe.hechos if h.veredicto is informe.veredicto] or informe.hechos
    hecho = decisivos[0] if decisivos else None

    if informe.veredicto is Veredicto.REFUTADO:
        par = _mejor(hecho.en_contra) if hecho else None
        base = "No — la evidencia lo refuta"
    elif informe.veredicto is Veredicto.SUSTENTADO:
        par = _mejor(hecho.a_favor) if hecho else None
        base = "Sí — la evidencia lo confirma"
    elif informe.veredicto is Veredicto.CONTRADICTORIO:
        favor = _mejor(hecho.a_favor) if hecho else None
        contra = _mejor(hecho.en_contra) if hecho else None
        partes = [
            f"{p.evidencia.dominio} dice «{p.evidencia.texto[:110].strip()}…»"
            for p in (favor, contra) if p is not None
        ]
        return ("Hay evidencia seria en ambos sentidos: " + "; pero ".join(partes)
                + f" (confianza {informe.confianza:.0%}).")
    else:
        consultadas = sum(len(h.a_favor) + len(h.en_contra) for h in informe.hechos)
        return ("No hay evidencia suficiente para confirmarlo ni refutarlo "
                f"({consultadas} pasaje(s) evaluados; conviene reformular o esperar mejores fuentes).")

    if par is None:
        return f"{base} (confianza {informe.confianza:.0%})."
    return (f"{base}: {par.evidencia.dominio} señala que "
            f"«{par.evidencia.texto[:150].strip()}…» "
            f"(confianza {informe.confianza:.0%}; {par.evidencia.url})")


def sintetizar(informe: Informe, generador=None, lang: str = "es", max_tokens: int = 700) -> str | None:
    """Prose summary of the verified table, or None (no generator / unsafe output)."""
    if generador is None:
        return None
    tabla = tabla_evidencia(informe)
    prompt = (
        "You are the writing assistant of a fact-checking system. Below is the "
        "final, aggregated verification table. Answer the user.\n\nHARD RULES:\n"
        "- Report ONLY what the table supports. The verdicts are final: do not "
        "contradict or soften them.\n"
        "- Cite only the listed URLs; never add outside knowledge.\n"
        "- CONCISE: at most 2 sentences, under 50 words. Start with the direct "
        "answer (yes / no / it depends / unknown), then the single strongest "
        "reason with its source. No preamble, no hedging filler.\n"
        f"- Answer in the language «{lang}».\n\n"
        f"{tabla}\n\nAnswer:"
    )
    try:
        texto = generador.completar(prompt, max_tokens=min(max_tokens, 160), temperature=0.3)
    except Exception:
        return None
    texto = _PENSAMIENTO.sub("", texto or "").strip()
    if not texto:
        return None
    plano = texto.casefold()
    if any(marca in plano for marca in _MARCADORES_CONTRARIOS.get(informe.veredicto, ())):
        return None
    return texto

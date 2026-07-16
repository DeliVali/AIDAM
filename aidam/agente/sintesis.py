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


def sintetizar(informe: Informe, generador=None, lang: str = "es", max_tokens: int = 700) -> str | None:
    """Prose summary of the verified table, or None (no generator / unsafe output)."""
    if generador is None:
        return None
    tabla = tabla_evidencia(informe)
    prompt = (
        "You are the writing assistant of a fact-checking system. Below is the "
        "final, aggregated verification table. Write a brief summary for the "
        "user.\n\nHARD RULES:\n"
        "- Report ONLY what the table supports. The verdicts are final: do not "
        "contradict or soften them.\n"
        "- Cite only the listed URLs; never add outside knowledge.\n"
        f"- Answer in the language «{lang}». 3-6 sentences.\n\n"
        f"{tabla}\n\nSummary:"
    )
    try:
        texto = generador.completar(prompt, max_tokens=max_tokens, temperature=0.3)
    except Exception:
        return None
    texto = _PENSAMIENTO.sub("", texto or "").strip()
    if not texto:
        return None
    plano = texto.casefold()
    if any(marca in plano for marca in _MARCADORES_CONTRARIOS.get(informe.veredicto, ())):
        return None
    return texto

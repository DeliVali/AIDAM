"""Pipeline orchestrator: decompose → retrieve → verify → aggregate."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

from .aggregate import agregar_hecho, agregar_informe
from .decompose import descomponer
from .models import EtiquetaPar, Informe, Veredicto
from .retrieve import recuperar


@lru_cache(maxsize=1)
def _generador_preguntas():
    """Loads the generator (~5 GB) ONCE per process.

    Loading it per call leaks VRAM until the GPU is exhausted — measured: a
    100-claim evaluation died at #7 because of this. If loading fails, it
    returns None and the pipeline continues without that stage.
    """
    from .questions import GeneradorPreguntas, ruta_modelo

    if ruta_modelo() is None:
        return None
    try:
        return GeneradorPreguntas()
    except Exception:
        return None


def verificar(
    afirmacion: str,
    lang: str = "es",
    max_idiomas: int = 5,
    preguntas: bool = False,
    verificador=None,
    progreso: Callable[[str], None] | None = None,
    recuperador: Callable[..., list] | None = None,
    buscador_preguntas: Callable[[str], list] | None = None,
) -> Informe:
    """Verifies a claim end to end and returns the report.

    `verificador` accepts any object with the contract
    `juzgar(hecho, evidencias) -> list[VeredictoPar]`; if not given, the
    default NLI backend is loaded (requires `pip install aidam[verificador]`).

    `recuperador` accepts any `(hecho, lang, max_idiomas, categoria) ->
    list[Evidencia]` callable in place of live `recuperar()` — the seam
    `evaluation/knowledge_store.py` uses to swap in the AVeriTeC organizers'
    offline knowledge store, so a reproducible eval never depends on live
    search staying healthy.

    `buscador_preguntas` accepts any `(pregunta: str) -> list[Evidencia]`
    callable, used for the LLM-generated follow-up questions when `preguntas`
    is set. Defaults to live `buscar_web`; the offline knowledge-store eval
    overrides it to re-query the SAME per-claim document set with the more
    targeted sub-question instead of the whole (possibly compound) claim —
    the same mechanism `recuperador` uses, applied per generated question.
    """
    avisar = progreso or (lambda _mensaje: None)
    buscar = recuperador or recuperar

    from .agente.sintesis import es_pregunta, responder_pregunta

    if recuperador is None and es_pregunta(afirmacion):
        # Research question → answer mode. Verdict semantics do not apply
        # (a question cannot be refuted); the answer comes from retrieved
        # evidence, ranked by meaning, with citations. Gated to the live
        # path: eval seams inject `recuperador` and always verify claims.
        avisar("Pregunta detectada: buscando la respuesta en las fuentes…")
        from .models import HechoAtomico

        hecho_q = HechoAtomico(texto=afirmacion, origen="pregunta")
        evidencias = buscar(hecho_q, lang=lang, max_idiomas=max_idiomas, categoria=None)
        return Informe(
            afirmacion=afirmacion,
            veredicto=Veredicto.INSUFICIENTE,
            confianza=0.0,
            hechos=[],
            tipo="pregunta",
            respuesta=responder_pregunta(afirmacion, evidencias),
        )

    if verificador is None:
        avisar("Cargando el núcleo verificador…")
        from .verify import crear_verificador

        verificador = crear_verificador()

    hechos = descomponer(afirmacion)
    avisar(f"Afirmación descompuesta en {len(hechos)} hecho(s) atómico(s)")

    from .router import clasificar

    generador = None
    if preguntas:
        avisar("Cargando el generador de preguntas (MiMo)…")
        generador = _generador_preguntas()
        if generador is None:
            avisar("Generador de preguntas no disponible; sigo sin esa etapa")

    veredictos_hechos = []
    for hecho in hechos:
        categoria = clasificar(hecho.texto, verificador)
        avisar(f"Buscando evidencia [{categoria}]: «{hecho.texto[:70]}»")
        evidencias = buscar(hecho, lang=lang, max_idiomas=max_idiomas, categoria=categoria)

        if generador is not None:
            buscar_pregunta = buscador_preguntas
            if buscar_pregunta is None:
                from .retrieve import buscar_web

                buscar_pregunta = lambda p: buscar_web(  # noqa: E731
                    p, max_resultados=4, lang=lang, paginas_completas=1
                )

            for pregunta in generador.preguntas(hecho.texto, n=2, lang=lang):
                avisar(f"  pregunta de búsqueda: «{pregunta[:70]}»")
                evidencias.extend(buscar_pregunta(pregunta))
        idiomas = sorted({e.idioma for e in evidencias if e.idioma})
        avisar(
            f"  {len(evidencias)} pasajes de {len({e.dominio for e in evidencias})} dominios"
            f" · idiomas: {', '.join(idiomas) or lang}"
        )

        pares = verificador.juzgar(hecho, evidencias) if evidencias else []
        # Symbolic comparators (Phase 3 seed): different-period quantity
        # mismatches are not contradictions — judged by rule, not weights.
        # Measured on the pair cache (2026-07-09): fires rarely (1/200
        # claims) because it requires explicit time markers on BOTH sides;
        # kept because it's zero-cost, correct where it fires, and the
        # growth path is real (ground relative periods via Wikidata dates,
        # date arithmetic, unit conversion). Honest status: seed, not win.
        from .comparators import ajustar_pares

        ajustar_pares(pares)
        vh = agregar_hecho(hecho, pares)

        # Cherry-picking: a supported claim can still deceive by omission.
        # The judge (LLM) decides ONLY from the evidence on the table, and
        # only when contrary context was retrieved to evaluate.
        if generador is not None and vh.veredicto is Veredicto.SUSTENTADO:
            # Measured brake (AVeriTeC-500: 109 predicted conflicting vs 38
            # real): only consult the judge if the contrary context is
            # substantial — strong signal (≥0.75), not any lukewarm passage.
            contexto = [
                p.evidencia.texto
                for p in sorted(pares, key=lambda p: p.prob, reverse=True)
                if p.etiqueta is EtiquetaPar.REFUTA and p.prob >= 0.75
            ]
            juicio = generador.juzgar_omision(
                hecho.texto, [p.evidencia.texto for p in vh.a_favor], contexto
            )
            if juicio == "enganosa":
                avisar("  juez de omisión: engañosa por omisión → contradictoria")
                vh.veredicto = Veredicto.CONTRADICTORIO
                vh.confianza = round(min(vh.confianza, 0.6), 3)

        # Both LLM resolvers below need the passages that actually swayed the
        # NLI verifier, not just the first N in retrieval order — with
        # question-driven search routinely pulling in 30+ passages, the
        # informative ones (highest-signal SUSTENTA/REFUTA) can easily fall
        # past evidencias[:8] while low-signal NO_CONCLUYE filler stays at
        # the front (measured: this exact bug silently starved the dissent
        # resolver below of the very REFUTA evidence that triggered it).
        pasajes_priorizados = [
            p.evidencia.texto
            for p in sorted(
                pares, key=lambda p: (p.etiqueta is not EtiquetaPar.NO_CONCLUYE, p.prob),
                reverse=True,
            )
        ]

        # NEI resolver: the aggregator has no confident signal (no passage
        # cleared UMBRAL_SENAL, or nothing but neutral judgements) — often
        # exactly the implicit-negation case a pairwise NLI classifier can't
        # resolve ("X denies Y" doesn't read as textbook contradiction) but a
        # holistic reasoner can. Measured standalone, the LLM is FAR too
        # NEI-happy to be the primary judge (24.0% vs. the aggregator's
        # 58.0% on AVeriTeC-100 — it defaulted 63/100 claims to NEI against
        # 7 gold). Used only here, on cases the aggregator already couldn't
        # decide, that same caution becomes a feature: if it still comes back
        # with a confident answer despite its own bias toward "not enough
        # evidence", that disagreement is real signal, not noise.
        if generador is not None and vh.veredicto is Veredicto.INSUFICIENTE and evidencias:
            etiqueta_llm = generador.juzgar_veredicto(hecho.texto, pasajes_priorizados)
            veredicto_llm = {
                "Supported": Veredicto.SUSTENTADO,
                "Refuted": Veredicto.REFUTADO,
                "Conflicting Evidence/Cherrypicking": Veredicto.CONTRADICTORIO,
            }.get(etiqueta_llm or "")
            if veredicto_llm is not None:
                avisar(f"  resolutor NEI: {etiqueta_llm} (evidencia insuficiente para el NLI)")
                vh.veredicto = veredicto_llm
                vh.confianza = 0.5  # categorical LLM answer, not a calibrated probability

        # Tried and reverted (2026-07-08): a broader "dissent resolver" that
        # also consulted the LLM whenever SUSTENTADO coexisted with
        # substantial REFUTA evidence the aggregator's weighting had simply
        # outvoted — motivated by a real traced case (Pogba hoax: SUSTENTADO
        # at confidence 1.00, because six denial-carrying passages were each
        # individually judged NEUTRAL, so they never got to outvote the one
        # passage stating the rumor directly). Fixed two real bugs finding
        # this out — `pasajes_priorizados` above (the LLM was silently
        # seeing evidencias[:8] in retrieval order, missing the very REFUTA
        # passages that triggered it) and the reasoning-length cap on
        # `juzgar_veredicto` (this model circles rather than converging on
        # ambiguous compound claims; needed an explicit "2-3 sentences, then
        # answer" constraint, not just more max_tokens — measured up to
        # 8,861 characters of reasoning, still undecided). Even with both
        # fixed, the specific Pogba case still didn't resolve, and the
        # broader trigger measured worse overall (58.0%→57.0%, Supported F1
        # 0.286→0.229) — reverted. The two bug fixes stay, since they're
        # real improvements to `juzgar_veredicto` itself.

        veredictos_hechos.append(vh)

    informe = agregar_informe(afirmacion, veredictos_hechos)
    # Jeffrey's product rule (2026-07-16): a bare label is not an answer.
    # Every claim report carries the one-breath grounded explanation.
    from .agente.sintesis import respuesta_concisa

    informe.respuesta = respuesta_concisa(informe)
    return informe

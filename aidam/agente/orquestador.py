"""Investigation-weight cascade: cheap tier-0 always, escalation only on measured signals.

The weight of an investigation is MEASURED after a cheap first pass, never
guessed a priori (cascade literature: 45-85% cost saved at ~95% quality,
arXiv:2410.10347; per-query escalation on calibrated error, arXiv:2605.18796).
Escalation adds evidence through diversified angles (see angulos.py); the
verdict always comes out of the same auditable aggregator — no other path.
LLMs reformulate queries and narrate; they never judge (measured here:
LLM-as-sole-judge 24.0% vs aggregator 58.0% on AVeriTeC-100).

NOT promoted to default: `aidam verificar` behavior is untouched. The
pre-registered promotion gate lives in docs/AGENT.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..models import HechoAtomico, Informe, Veredicto, VeredictoPar
from .angulos import generar_angulos, invertir_pares

# ───────── constantes (off-test, ajustables; NUNCA calibradas sobre benchmarks) ─────────

UMBRAL_CONFIANZA = 0.6   # tier confidence below which the cascade escalates
UMBRAL_CONFLICTO = 0.75  # min prob for opposing evidence to count as conflict
MAX_NIVEL = 2


@dataclass
class SenalesEscalado:
    confianza: float          # report confidence after the last pass
    conflicto: bool           # some fact has strong evidence on BOTH sides (≥ UMBRAL_CONFLICTO)
    insuficiente: bool        # overall verdict is INSUFICIENTE
    desacuerdo: float = 0.0   # 1 - modal fraction of per-angle verdicts (0 if < 2 angles)


@dataclass
class ResultadoAngulo:
    nombre: str
    consulta: str
    hecho: str
    evidencias: int
    pares: int


@dataclass
class InformeInvestigacion:
    informe: Informe
    nivel: int
    senales: SenalesEscalado
    angulos: list[ResultadoAngulo] = field(default_factory=list)
    sintesis: str | None = None
    # Always present: the one-breath answer the user actually reads
    # («No — la evidencia lo refuta: … (fuente)»). Deterministic template
    # by default; the LLM synthesis replaces it only when available AND
    # it passes the contradiction safeguard.
    respuesta: str = ""


# ───────── señales ─────────

def desacuerdo(veredictos: list[Veredicto]) -> float:
    """Disagreement among per-angle verdicts: 1 - modal fraction; 0 below 2 votes."""
    if len(veredictos) < 2:
        return 0.0
    conteos = {v: veredictos.count(v) for v in set(veredictos)}
    return round(1.0 - max(conteos.values()) / len(veredictos), 3)


def medir_senales(informe: Informe) -> SenalesEscalado:
    conflicto = any(
        any(par.prob >= UMBRAL_CONFLICTO for par in vh.a_favor)
        and any(par.prob >= UMBRAL_CONFLICTO for par in vh.en_contra)
        for vh in informe.hechos
    )
    return SenalesEscalado(
        confianza=informe.confianza,
        conflicto=conflicto,
        insuficiente=informe.veredicto is Veredicto.INSUFICIENTE,
    )


def hay_que_escalar(senales: SenalesEscalado) -> bool:
    return senales.confianza < UMBRAL_CONFIANZA or senales.conflicto or senales.insuficiente


# ───────── cascada ─────────

def investigar(
    afirmacion: str,
    nivel: int | None = None,
    lang: str = "es",
    max_idiomas: int = 5,
    preguntas: bool = False,
    verificador=None,
    progreso: Callable[[str], None] | None = None,
    sintetizar_final: bool = False,
    memoria_evidencia: bool = True,
) -> InformeInvestigacion:
    """Cascaded verification: tier-0 pass, then measured escalation by angles.

    Re-implements the per-fact loop with the same pieces as
    `pipeline.verificar` (descomponer, clasificar, recuperar, juzgar,
    ajustar_pares, agregar_*) so the raw pairs stay in hand for auditable
    re-aggregation across angles. The LLM post-processes of the pipeline
    (omission judge, NEI resolver) are deliberately absent here in v1: this
    path adds evidence instead of consulting a model about the shortfall.

    `nivel` forces an exact escalation level (0-2); None escalates
    automatically while `hay_que_escalar` holds.
    """
    avisar = progreso or (lambda _mensaje: None)

    from .sintesis import es_pregunta, responder_pregunta

    if es_pregunta(afirmacion):
        # Answer mode: questions are answered from evidence, never judged
        # (same rule as pipeline.verificar; measured failure 2026-07-16).
        avisar("Pregunta detectada: buscando la respuesta en las fuentes…")
        from ..models import HechoAtomico

        hecho_q = HechoAtomico(texto=afirmacion, origen="pregunta")
        evidencias = _recuperar(hecho_q, lang, max_idiomas, None)
        respuesta = responder_pregunta(afirmacion, evidencias)
        informe_q = Informe(
            afirmacion=afirmacion, veredicto=Veredicto.INSUFICIENTE,
            confianza=0.0, hechos=[], tipo="pregunta", respuesta=respuesta,
        )
        return InformeInvestigacion(
            informe=informe_q, nivel=0,
            senales=SenalesEscalado(confianza=0.0, conflicto=False, insuficiente=False),
            respuesta=respuesta,
        )

    if verificador is None:
        avisar("Cargando el núcleo verificador…")
        from ..verify import crear_verificador

        verificador = crear_verificador()

    from ..aggregate import agregar_hecho, agregar_informe
    from ..comparators import ajustar_pares
    from ..decompose import descomponer
    from ..router import clasificar

    generador = None
    if preguntas:
        from ..pipeline import _generador_preguntas

        generador = _generador_preguntas()
        if generador is None:
            avisar("Generador de preguntas no disponible; ángulos sin reformulación LLM")

    # ── tier-0: cheap pass, keeping the raw pairs per fact ──
    hechos = descomponer(afirmacion)
    avisar(f"Afirmación descompuesta en {len(hechos)} hecho(s) atómico(s)")

    # Dynamic instances (2026-07-16): retrieval is network-bound, so the
    # facts of a claim hunt for evidence SIMULTANEOUSLY (each fact already
    # fans out one thread per source inside `recuperar`). Judging stays
    # sequential on purpose: one resident verifier judging in batches is
    # the GPU-honest form of parallelism (see docs/AGENT.md doctrine).
    categorias = [clasificar(h.texto, verificador) for h in hechos]
    for hecho, categoria in zip(hechos, categorias):
        avisar(f"nivel 0 [{categoria}]: «{hecho.texto[:70]}»")

    def _evidencia_hecho(par_hc) -> list:
        hecho, categoria = par_hc
        evidencias = _recuperar(hecho, lang, max_idiomas, categoria)
        if memoria_evidencia:
            # Remembered passages join tier-0 for free (computed-once
            # vectors, original provenance kept so weights stay honest).
            recordadas = _desde_memoria(hecho, {(e.dominio, e.texto[:120]) for e in evidencias})
            if recordadas:
                avisar(f"  memoria: {len(recordadas)} pasaje(s) recordado(s)")
                evidencias = evidencias + recordadas
        return evidencias

    if len(hechos) > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(len(hechos), 4)) as pool:
            evidencias_por_hecho = list(pool.map(_evidencia_hecho, zip(hechos, categorias)))
    else:
        evidencias_por_hecho = [_evidencia_hecho((hechos[0], categorias[0]))] if hechos else []

    pares_por_hecho: list[list[VeredictoPar]] = []
    vistas_por_hecho: list[set[tuple[str, str]]] = []
    veredictos = []
    for hecho, evidencias in zip(hechos, evidencias_por_hecho):
        pares = verificador.juzgar(hecho, evidencias) if evidencias else []
        ajustar_pares(pares)
        pares_por_hecho.append(pares)
        vistas_por_hecho.append({(e.dominio, e.texto[:120]) for e in evidencias})
        veredictos.append(agregar_hecho(hecho, pares))

    informe = agregar_informe(afirmacion, veredictos)
    senales = medir_senales(informe)

    objetivo = MAX_NIVEL if nivel is None else max(0, min(nivel, MAX_NIVEL))
    resultados: list[ResultadoAngulo] = []
    votos_angulo: list[list[Veredicto]] = [[] for _ in hechos]
    consultas_usadas: list[set[str]] = [set() for _ in hechos]
    nivel_final = 0

    while nivel_final < objetivo:
        if nivel is None and not hay_que_escalar(senales):
            break
        nivel_actual = nivel_final + 1

        for indice, hecho in enumerate(hechos):
            vh = veredictos[indice]
            debil = vh.veredicto is not Veredicto.SUSTENTADO or vh.confianza < UMBRAL_CONFIANZA
            if nivel is None and not debil:
                continue  # auto mode spends angles only on weak facts; forced level covers all
            for angulo in generar_angulos(hecho.texto, nivel_actual, generador, lang):
                # A level-2 pass must not re-spend searches on level-1 angles:
                # the same query yields the same (already deduped) evidence.
                clave_consulta = angulo.consulta.casefold().strip()
                if clave_consulta in consultas_usadas[indice]:
                    continue
                consultas_usadas[indice].add(clave_consulta)
                avisar(f"nivel {nivel_actual} [{angulo.nombre}]: «{angulo.consulta[:60]}»")
                nuevas = _buscar_consulta(angulo.consulta, lang)
                nuevas = [
                    e for e in nuevas if (e.dominio, e.texto[:120]) not in vistas_por_hecho[indice]
                ]
                vistas_por_hecho[indice].update((e.dominio, e.texto[:120]) for e in nuevas)
                # Reformulations only diversify RETRIEVAL: the judged
                # hypothesis stays the fact verbatim. The negation angle is
                # the exception — it judges the negated hypothesis (an NLI
                # reads "supports not-X" more readily than "refutes X" for
                # implicit denials) and the labels are then flipped back and
                # reattached to the ORIGINAL fact.
                hecho_juzgado = (
                    HechoAtomico(angulo.consulta, "angulo-negacion") if angulo.invertido else hecho
                )
                pares_nuevos = verificador.juzgar(hecho_juzgado, nuevas) if nuevas else []
                ajustar_pares(pares_nuevos)
                if angulo.invertido:
                    pares_nuevos = invertir_pares(pares_nuevos, hecho=hecho)
                if pares_nuevos:
                    votos_angulo[indice].append(agregar_hecho(hecho, pares_nuevos).veredicto)
                pares_por_hecho[indice].extend(pares_nuevos)
                resultados.append(
                    ResultadoAngulo(
                        angulo.nombre, angulo.consulta, hecho.texto, len(nuevas), len(pares_nuevos)
                    )
                )

        # Re-aggregate through the SAME auditable rules — the only verdict path.
        veredictos = [
            agregar_hecho(hecho, pares) for hecho, pares in zip(hechos, pares_por_hecho)
        ]
        informe = agregar_informe(afirmacion, veredictos)
        senales = medir_senales(informe)
        votos = [desacuerdo(v) for v in votos_angulo if v]
        senales.desacuerdo = round(sum(votos) / len(votos), 3) if votos else 0.0
        nivel_final = nivel_actual

    from .sintesis import respuesta_concisa

    respuesta = respuesta_concisa(informe)
    sintesis = None
    if sintetizar_final and generador is not None:
        from .sintesis import sintetizar

        avisar("Redactando síntesis (el LLM narra, no juzga)…")
        sintesis = sintetizar(informe, generador, lang=lang)
        if sintesis:
            respuesta = sintesis

    return InformeInvestigacion(
        informe=informe, nivel=nivel_final, senales=senales, angulos=resultados,
        sintesis=sintesis, respuesta=respuesta,
    )


# ───────── recuperación (indirection kept lazy and monkeypatch-friendly) ─────────

def _desde_memoria(hecho: HechoAtomico, vistas: set[tuple[str, str]]) -> list:
    """Tier-0 evidence from the semantic memory (agent path only — the
    eval seams inject their own retrievers and never come through here).

    Passages keep their ORIGINAL url/domain/source, so the aggregator's
    reliability priors apply unchanged; memory is a cache of documents,
    never of verdicts. Best effort: without the embedder or with an empty
    index this contributes nothing and costs nothing.
    """
    try:
        from ..memoria import RUTA_DEFECTO
        from ..models import Evidencia
        from ..vectores import IndiceEvidencia

        indice = IndiceEvidencia(RUTA_DEFECTO)
        try:
            filas = indice.buscar(hecho.texto, limite=4)
        finally:
            indice.cerrar()
    except Exception:
        return []
    _UMBRAL_MEMORIA = 0.85  # e5 cosine: clearly-relevant passages only
    return [
        Evidencia(texto=f["texto"], url=f["url"], titulo="",
                  dominio=f["dominio"], fuente=f["fuente"], idioma=f["idioma"])
        for f in filas
        if f["puntaje"] >= _UMBRAL_MEMORIA and (f["dominio"], f["texto"][:120]) not in vistas
    ]


def _recuperar(hecho: HechoAtomico, lang: str, max_idiomas: int, categoria: str | None):
    from .. import retrieve

    return retrieve.recuperar(hecho, lang=lang, max_idiomas=max_idiomas, categoria=categoria)


def _buscar_consulta(consulta: str, lang: str):
    from .. import retrieve

    try:
        return retrieve.buscar_web(consulta, max_resultados=4, lang=lang, paginas_completas=1)
    except Exception:
        return []  # a failing search engine must never take the investigation down

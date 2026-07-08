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
) -> Informe:
    """Verifies a claim end to end and returns the report.

    `verificador` accepts any object with the contract
    `juzgar(hecho, evidencias) -> list[VeredictoPar]`; if not given, the
    default NLI backend is loaded (requires `pip install aidam[verificador]`).
    """
    avisar = progreso or (lambda _mensaje: None)

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
        evidencias = recuperar(hecho, lang=lang, max_idiomas=max_idiomas, categoria=categoria)

        if generador is not None:
            from .retrieve import buscar_web

            for pregunta in generador.preguntas(hecho.texto, n=2, lang=lang):
                avisar(f"  pregunta de búsqueda: «{pregunta[:70]}»")
                evidencias.extend(
                    buscar_web(pregunta, max_resultados=4, lang=lang, paginas_completas=1)
                )
        idiomas = sorted({e.idioma for e in evidencias if e.idioma})
        avisar(
            f"  {len(evidencias)} pasajes de {len({e.dominio for e in evidencias})} dominios"
            f" · idiomas: {', '.join(idiomas) or lang}"
        )

        pares = verificador.juzgar(hecho, evidencias) if evidencias else []
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

        veredictos_hechos.append(vh)

    return agregar_informe(afirmacion, veredictos_hechos)

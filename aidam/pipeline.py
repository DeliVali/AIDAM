"""Orquestador del pipeline: descomponer → recuperar → verificar → agregar."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

from .aggregate import agregar_hecho, agregar_informe
from .decompose import descomponer
from .models import Informe
from .retrieve import recuperar


@lru_cache(maxsize=1)
def _generador_preguntas():
    """Carga el generador (4.7 GB) UNA sola vez por proceso.

    Cargarlo por llamada filtra VRAM hasta agotar la GPU — medido: una
    evaluación de 100 afirmaciones murió en la #7 por esto. Si la carga
    falla, devuelve None y el pipeline sigue sin esa etapa.
    """
    from .preguntas import GeneradorPreguntas, ruta_modelo

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
    """Verifica una afirmación de punta a punta y devuelve el informe.

    `verificador` acepta cualquier objeto con el contrato
    `juzgar(hecho, evidencias) -> list[VeredictoPar]`; si no se pasa,
    se carga el backend NLI por defecto (requiere `pip install aidam[verificador]`).
    """
    avisar = progreso or (lambda _mensaje: None)

    if verificador is None:
        avisar("Cargando el núcleo verificador…")
        from .verify import VerificadorNLI

        verificador = VerificadorNLI()

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
        veredictos_hechos.append(agregar_hecho(hecho, pares))

    return agregar_informe(afirmacion, veredictos_hechos)

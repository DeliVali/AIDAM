"""Orquestador del pipeline: descomponer → recuperar → verificar → agregar."""

from __future__ import annotations

from typing import Callable

from .aggregate import agregar_hecho, agregar_informe
from .decompose import descomponer
from .models import Informe
from .retrieve import recuperar


def verificar(
    afirmacion: str,
    lang: str = "es",
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

    veredictos_hechos = []
    for hecho in hechos:
        avisar(f"Buscando evidencia: «{hecho.texto[:70]}»")
        evidencias = recuperar(hecho, lang=lang)
        avisar(f"  {len(evidencias)} pasajes de {len({e.dominio for e in evidencias})} dominios")
        pares = verificador.juzgar(hecho, evidencias) if evidencias else []
        veredictos_hechos.append(agregar_hecho(hecho, pares))

    return agregar_informe(afirmacion, veredictos_hechos)

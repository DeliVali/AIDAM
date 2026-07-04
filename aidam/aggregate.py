"""Agregador de lógica comparativa (Módulo 4).

Matemática explícita y auditable — sin red neuronal, a propósito. Combina los
juicios por par en un veredicto por hecho, y los veredictos por hecho en el
veredicto de la afirmación completa.

Reglas de independencia: cada dominio aporta una sola voz por lado (su mejor
evidencia). Así, cien páginas que copian el mismo comunicado no pesan más que
una fuente original.
"""

from __future__ import annotations

from .models import (
    EtiquetaPar,
    HechoAtomico,
    Informe,
    Veredicto,
    VeredictoHecho,
    VeredictoPar,
)

# Probabilidad mínima para que un juicio cuente como señal.
UMBRAL_SENAL = 0.60
# Cuánto debe superar la señal de un lado a la del otro para dominar;
# por debajo de esto, el veredicto es "evidencia contradictoria".
DOMINANCIA = 2.0
# Fuentes independientes necesarias para confianza plena.
FUENTES_PLENAS = 3


def _mejor_por_dominio(pares: list[VeredictoPar]) -> dict[tuple[str, str], VeredictoPar]:
    """Se queda con el juicio más seguro de cada (dominio, lado)."""
    mejores: dict[tuple[str, str], VeredictoPar] = {}
    for par in pares:
        if par.etiqueta is EtiquetaPar.NO_CONCLUYE or par.prob < UMBRAL_SENAL:
            continue
        clave = (par.evidencia.dominio, par.etiqueta.value)
        if clave not in mejores or par.prob > mejores[clave].prob:
            mejores[clave] = par
    return mejores


def agregar_hecho(hecho: HechoAtomico, pares: list[VeredictoPar]) -> VeredictoHecho:
    """Agrega los juicios por par en un veredicto para el hecho."""
    voces = _mejor_por_dominio(pares)
    a_favor = sorted(
        (p for p in voces.values() if p.etiqueta is EtiquetaPar.SUSTENTA),
        key=lambda p: p.prob,
        reverse=True,
    )
    en_contra = sorted(
        (p for p in voces.values() if p.etiqueta is EtiquetaPar.REFUTA),
        key=lambda p: p.prob,
        reverse=True,
    )
    senal_favor = sum(p.prob for p in a_favor)
    senal_contra = sum(p.prob for p in en_contra)
    total = senal_favor + senal_contra
    cobertura = min(1.0, len(voces) / FUENTES_PLENAS)

    if total == 0:
        veredicto, confianza = Veredicto.INSUFICIENTE, 0.0
    elif senal_favor > 0 and senal_contra > 0 and (
        max(senal_favor, senal_contra) < DOMINANCIA * min(senal_favor, senal_contra)
    ):
        veredicto = Veredicto.CONTRADICTORIO
        confianza = cobertura
    elif senal_favor > senal_contra:
        veredicto = Veredicto.SUSTENTADO
        confianza = (senal_favor / total) * cobertura
    else:
        veredicto = Veredicto.REFUTADO
        confianza = (senal_contra / total) * cobertura

    return VeredictoHecho(
        hecho=hecho,
        veredicto=veredicto,
        confianza=round(confianza, 3),
        a_favor=a_favor,
        en_contra=en_contra,
    )


def agregar_informe(afirmacion: str, hechos: list[VeredictoHecho]) -> Informe:
    """Combina los veredictos por hecho en el veredicto de la afirmación.

    Una afirmación es tan cierta como su hecho más débil: cualquier hecho
    refutado refuta el conjunto; cualquier contradicción o hueco impide
    declararla sustentada.
    """
    veredictos = {h.veredicto for h in hechos}
    if Veredicto.REFUTADO in veredictos:
        global_ = Veredicto.REFUTADO
        relevantes = [h for h in hechos if h.veredicto is Veredicto.REFUTADO]
    elif Veredicto.CONTRADICTORIO in veredictos:
        global_ = Veredicto.CONTRADICTORIO
        relevantes = [h for h in hechos if h.veredicto is Veredicto.CONTRADICTORIO]
    elif Veredicto.INSUFICIENTE in veredictos:
        global_ = Veredicto.INSUFICIENTE
        relevantes = [h for h in hechos if h.veredicto is Veredicto.INSUFICIENTE]
    else:
        global_ = Veredicto.SUSTENTADO
        relevantes = hechos

    confianza = (
        round(min(h.confianza for h in relevantes), 3) if relevantes else 0.0
    )
    return Informe(
        afirmacion=afirmacion,
        veredicto=global_,
        confianza=confianza,
        hechos=hechos,
    )

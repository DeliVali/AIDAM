"""Agregador de lógica comparativa (Módulo 4).

Matemática explícita y auditable — sin red neuronal, a propósito. Combina los
juicios por par en un veredicto por hecho, y los veredictos por hecho en el
veredicto de la afirmación completa.

Reglas de independencia y fiabilidad (cada una nació de un fallo medido):
1. Cada dominio aporta una sola voz por lado (su mejor evidencia). Cien
   páginas que copian el mismo comunicado no pesan más que una fuente.
2. Priores de fiabilidad por tipo de fuente: los verificadores profesionales,
   enciclopedias, academia y organismos oficiales pesan más que un dominio
   desconocido. Motivado por AVeriTeC: sin esto, la mentira viral repetida en
   muchos sitios le gana al fact-checker que la desmiente.
3. El eco no es evidencia: un snippet web que solo repite la afirmación casi
   palabra por palabra no aporta información propia — sostener no es repetir.
   (Solo aplica al lado que sustenta: refutar exige contenido propio.)
"""

from __future__ import annotations

import re

from .models import (
    EtiquetaPar,
    Evidencia,
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

# ── Priores de fiabilidad (transparentes y discutibles en el repo) ──
# Verificadores profesionales de hechos (miembros/afines a la red IFCN).
VERIFICADORES = {
    "politifact.com", "snopes.com", "factcheck.org", "fullfact.org",
    "chequeado.com", "maldita.es", "newtral.es", "factual.afp.com",
    "factcheck.afp.com", "leadstories.com", "checkyourfact.com",
    "boomlive.in", "altnews.in", "colombiacheck.com", "verificado.com.mx",
    "aosfatos.org", "lupa.uol.com.br", "correctiv.org", "pagellapolitica.it",
}
# Un desmentido profesional vale ~un orden de magnitud más que la afirmación
# de un dominio desconocido: con 8.0, un fact-checker le gana a 3 sitios
# virales, pero 6+ sitios independientes aún fuerzan "contradictorio".
PESO_VERIFICADOR = 8.0
PESO_ENCICLOPEDIA = 2.5  # *.wikipedia.org
PESO_ACADEMICO = 2.5  # papers (fuente == "academica")
PESO_OFICIAL = 2.0  # dominios .gov / .edu
PESO_WIKINEWS = 1.5
PESO_BASE = 1.0
PESO_ECO = 0.3  # multiplicador para el eco (regla 3)
_UMBRAL_ECO = 0.8  # fracción de palabras de la afirmación presentes en el pasaje


def peso_fuente(evidencia: Evidencia) -> float:
    """Prior de fiabilidad del dominio. Explícito para poder auditarlo."""
    dominio = evidencia.dominio
    if dominio in VERIFICADORES:
        return PESO_VERIFICADOR
    if dominio.endswith(".wikipedia.org"):
        return PESO_ENCICLOPEDIA
    if evidencia.fuente == "academica":
        return PESO_ACADEMICO
    if dominio.endswith((".gov", ".edu")) or ".gov." in dominio or ".edu." in dominio:
        return PESO_OFICIAL
    if evidencia.fuente == "wikinews":
        return PESO_WIKINEWS
    return PESO_BASE


_MIN_PALABRAS_ECO = 6


def _es_eco(hecho: HechoAtomico, evidencia: Evidencia) -> bool:
    """¿El pasaje solo repite la afirmación sin aportar contenido propio?

    Solo aplica a afirmaciones largas y específicas (≥6 palabras de contenido,
    el perfil de una afirmación viral). En afirmaciones técnicas cortas
    («Python lists are mutable») cualquier pasaje legítimo sobre el tema
    contiene todas las palabras — eso es cobertura, no eco.
    """
    palabras = set(re.findall(r"\w{4,}", hecho.texto.lower()))
    if len(palabras) < _MIN_PALABRAS_ECO:
        return False
    presentes = sum(1 for p in palabras if p in evidencia.texto.lower())
    return presentes / len(palabras) >= _UMBRAL_ECO


def _peso(par: VeredictoPar) -> float:
    """Peso total de un juicio: prior de fiabilidad × penalización por eco."""
    peso = peso_fuente(par.evidencia)
    if (
        par.etiqueta is EtiquetaPar.SUSTENTA
        and par.evidencia.fuente in ("web", "desmentidos")
        and _es_eco(par.hecho, par.evidencia)
    ):
        peso *= PESO_ECO
    return peso


def _mejor_por_dominio(pares: list[VeredictoPar]) -> dict[str, VeredictoPar]:
    """Un dominio, una sola voz: su juicio de mayor señal ponderada.

    Si un mismo sitio tiene pasajes en ambos lados (típico de un fact-check,
    que narra el mito antes de desmentirlo), vota solo con su señal más
    fuerte — su postura real — en vez de contarse dos veces.
    """
    mejores: dict[str, VeredictoPar] = {}
    for par in pares:
        if par.etiqueta is EtiquetaPar.NO_CONCLUYE or par.prob < UMBRAL_SENAL:
            continue
        clave = par.evidencia.dominio
        if clave not in mejores or par.prob * _peso(par) > mejores[clave].prob * _peso(
            mejores[clave]
        ):
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
    senal_favor = sum(p.prob * _peso(p) for p in a_favor)
    senal_contra = sum(p.prob * _peso(p) for p in en_contra)
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

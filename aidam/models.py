"""Estructuras de datos centrales de AIDAM."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EtiquetaPar(str, Enum):
    """Juicio del verificador sobre un par (hecho, evidencia)."""

    SUSTENTA = "sustenta"
    REFUTA = "refuta"
    NO_CONCLUYE = "no_concluye"


class Veredicto(str, Enum):
    """Veredicto agregado sobre un hecho o afirmación (clases de AVeriTeC)."""

    SUSTENTADO = "sustentado"
    REFUTADO = "refutado"
    CONTRADICTORIO = "evidencia_contradictoria"
    INSUFICIENTE = "evidencia_insuficiente"


@dataclass
class HechoAtomico:
    """Un hecho autocontenido y verificable, extraído de la afirmación original."""

    texto: str
    origen: str


@dataclass
class Evidencia:
    """Un pasaje de texto recuperado de una fuente, con su procedencia."""

    texto: str
    url: str
    titulo: str
    dominio: str
    fuente: str  # "wikipedia" | "web"
    idioma: str = ""  # código ISO del idioma del pasaje ("es", "en", "zh", …)


@dataclass
class VeredictoPar:
    """Juicio del verificador para un par (hecho, evidencia) con su probabilidad."""

    hecho: HechoAtomico
    evidencia: Evidencia
    etiqueta: EtiquetaPar
    prob: float


@dataclass
class VeredictoHecho:
    """Veredicto agregado de un hecho, con las evidencias que lo justifican."""

    hecho: HechoAtomico
    veredicto: Veredicto
    confianza: float
    a_favor: list[VeredictoPar] = field(default_factory=list)
    en_contra: list[VeredictoPar] = field(default_factory=list)


@dataclass
class Informe:
    """Resultado completo de verificar una afirmación."""

    afirmacion: str
    veredicto: Veredicto
    confianza: float
    hechos: list[VeredictoHecho] = field(default_factory=list)

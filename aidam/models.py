"""Core data structures of AIDAM."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EtiquetaPar(str, Enum):
    """Verifier judgement for a (fact, evidence) pair."""

    SUSTENTA = "sustenta"
    REFUTA = "refuta"
    NO_CONCLUYE = "no_concluye"


class Veredicto(str, Enum):
    """Aggregated verdict for a fact or claim (AVeriTeC classes)."""

    SUSTENTADO = "sustentado"
    REFUTADO = "refutado"
    CONTRADICTORIO = "evidencia_contradictoria"
    INSUFICIENTE = "evidencia_insuficiente"


@dataclass
class HechoAtomico:
    """A self-contained, verifiable fact extracted from the original claim."""

    texto: str
    origen: str


@dataclass
class Evidencia:
    """A text passage retrieved from a source, with its provenance."""

    texto: str
    url: str
    titulo: str
    dominio: str
    fuente: str  # "wikipedia" | "web"
    idioma: str = ""  # ISO code of the passage language ("es", "en", "zh", …)


@dataclass
class VeredictoPar:
    """Verifier judgement for a (fact, evidence) pair with its probability."""

    hecho: HechoAtomico
    evidencia: Evidencia
    etiqueta: EtiquetaPar
    prob: float


@dataclass
class VeredictoHecho:
    """Aggregated verdict for a fact, with the evidence that justifies it."""

    hecho: HechoAtomico
    veredicto: Veredicto
    confianza: float
    a_favor: list[VeredictoPar] = field(default_factory=list)
    en_contra: list[VeredictoPar] = field(default_factory=list)


@dataclass
class Informe:
    """Complete result of verifying a claim."""

    afirmacion: str
    veredicto: Veredicto
    confianza: float
    hechos: list[VeredictoHecho] = field(default_factory=list)


def informe_a_dict(informe: Informe) -> dict:
    """Serializes a report to JSON-ready primitives.

    Shared by the CLI (`--json`) and the web interface (WebSocket protocol),
    so both always emit the same shape.
    """
    import dataclasses

    def limpiar(obj):
        if dataclasses.is_dataclass(obj):
            obj = dataclasses.asdict(obj)
        if isinstance(obj, dict):
            return {k: limpiar(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [limpiar(x) for x in obj]
        if isinstance(obj, Enum):
            return obj.value
        return obj

    return limpiar(informe)

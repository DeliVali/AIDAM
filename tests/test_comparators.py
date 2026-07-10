"""Symbolic comparator tests: surgical scope, no collateral damage."""

from aidam.comparators import _cantidades, _periodo, _periodos_distintos, ajustar_pares
from aidam.models import EtiquetaPar, Evidencia, HechoAtomico, VeredictoPar


def _par(claim: str, evidencia: str, etiqueta: EtiquetaPar, prob: float = 0.9) -> VeredictoPar:
    return VeredictoPar(
        hecho=HechoAtomico(texto=claim, origen=claim),
        evidencia=Evidencia(texto=evidencia, url="", titulo="", dominio="x.org",
                            fuente="web", idioma="en"),
        etiqueta=etiqueta,
        prob=prob,
    )


def test_caso_207_nigeria_se_neutraliza():
    """The traced case: past-relative quantity vs present quantity."""
    par = _par(
        "At independence, Nigeria had a population of 45 million.",
        "Nigeria currently has a population of 200 million people.",
        EtiquetaPar.REFUTA,
    )
    ajustar_pares([par])
    assert par.etiqueta is EtiquetaPar.NO_CONCLUYE


def test_mismo_periodo_sigue_refutando():
    """Same explicit year with different numbers IS a real contradiction."""
    par = _par(
        "In 2020, the city had 45 million inhabitants.",
        "In 2020, the city had a population of 200 million.",
        EtiquetaPar.REFUTA,
    )
    ajustar_pares([par])
    assert par.etiqueta is EtiquetaPar.REFUTA


def test_sin_marcador_temporal_no_toca_nada():
    """No explicit period on one side → leave the NLI verdict alone
    (can't prove the periods differ)."""
    par = _par(
        "Nigeria has a population of 45 million.",
        "Nigeria has a population of 200 million people.",
        EtiquetaPar.REFUTA,
    )
    ajustar_pares([par])
    assert par.etiqueta is EtiquetaPar.REFUTA


def test_anio_vs_pasado_relativo_no_es_demostrable():
    """'At independence' might BE 1960 — not provably different periods."""
    par = _par(
        "At independence, Nigeria had 45 million inhabitants.",
        "In 1960, Nigeria had a population of 60 million.",
        EtiquetaPar.REFUTA,
    )
    ajustar_pares([par])
    assert par.etiqueta is EtiquetaPar.REFUTA


def test_cantidades_cercanas_no_se_neutralizan():
    """Within-20% quantities aren't 'different' — no downgrade."""
    par = _par(
        "In 1990, the company had 100 thousand employees.",
        "The company currently employs 110 thousand people.",
        EtiquetaPar.REFUTA,
    )
    ajustar_pares([par])
    assert par.etiqueta is EtiquetaPar.REFUTA


def test_sustenta_y_neutral_jamas_cambian():
    pares = [
        _par("In 1960, X had 45 million.", "X currently has 200 million.",
             EtiquetaPar.SUSTENTA),
        _par("In 1960, X had 45 million.", "X currently has 200 million.",
             EtiquetaPar.NO_CONCLUYE),
    ]
    ajustar_pares(pares)
    assert pares[0].etiqueta is EtiquetaPar.SUSTENTA
    assert pares[1].etiqueta is EtiquetaPar.NO_CONCLUYE


def test_extraccion_de_cantidades():
    assert _cantidades("a population of 45 million") == [45e6]
    assert _cantidades("about 2.5 billion dollars") == [2.5e9]
    assert _cantidades("4 senators visited") == []  # bare small ints: too noisy


def test_periodos():
    assert _periodo("In 1960, the population was large") == "1960"
    assert _periodo("At independence, it had...") == "pasado-relativo"
    assert _periodo("It currently has...") == "presente"
    assert _periodo("The population is large") is None
    assert _periodos_distintos("1960", "presente")
    assert _periodos_distintos("1960", "1980")
    assert not _periodos_distintos("2024", "presente")  # recent year ≈ now

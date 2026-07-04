"""Tests del agregador: la lógica comparativa debe ser predecible y auditable."""

from aidam.aggregate import agregar_hecho, agregar_informe
from aidam.models import (
    EtiquetaPar,
    Evidencia,
    HechoAtomico,
    Veredicto,
    VeredictoHecho,
    VeredictoPar,
)

HECHO = HechoAtomico(texto="La Torre Eiffel está en París", origen="…")


def _par(etiqueta: EtiquetaPar, prob: float, dominio: str) -> VeredictoPar:
    evidencia = Evidencia(
        texto="pasaje", url=f"https://{dominio}/x", titulo="t", dominio=dominio, fuente="web"
    )
    return VeredictoPar(hecho=HECHO, evidencia=evidencia, etiqueta=etiqueta, prob=prob)


def test_sin_evidencia_es_insuficiente():
    resultado = agregar_hecho(HECHO, [])
    assert resultado.veredicto is Veredicto.INSUFICIENTE
    assert resultado.confianza == 0.0


def test_solo_neutrales_es_insuficiente():
    pares = [_par(EtiquetaPar.NO_CONCLUYE, 0.9, f"d{i}.org") for i in range(4)]
    assert agregar_hecho(HECHO, pares).veredicto is Veredicto.INSUFICIENTE


def test_apoyo_unanime_sustenta():
    pares = [_par(EtiquetaPar.SUSTENTA, 0.9, f"d{i}.org") for i in range(3)]
    resultado = agregar_hecho(HECHO, pares)
    assert resultado.veredicto is Veredicto.SUSTENTADO
    assert resultado.confianza > 0.9


def test_senal_debil_se_descarta():
    pares = [_par(EtiquetaPar.SUSTENTA, 0.55, "d1.org")]  # bajo el umbral de 0.60
    assert agregar_hecho(HECHO, pares).veredicto is Veredicto.INSUFICIENTE


def test_refutacion_dominante_refuta():
    pares = [
        _par(EtiquetaPar.REFUTA, 0.95, "d1.org"),
        _par(EtiquetaPar.REFUTA, 0.90, "d2.org"),
        _par(EtiquetaPar.SUSTENTA, 0.65, "d3.org"),
    ]
    assert agregar_hecho(HECHO, pares).veredicto is Veredicto.REFUTADO


def test_senales_parejas_son_contradictorias():
    pares = [
        _par(EtiquetaPar.SUSTENTA, 0.85, "d1.org"),
        _par(EtiquetaPar.REFUTA, 0.80, "d2.org"),
    ]
    assert agregar_hecho(HECHO, pares).veredicto is Veredicto.CONTRADICTORIO


def test_cien_copias_cuentan_como_una_voz():
    """Independencia: el mismo dominio no gana por repetición."""
    copias = [_par(EtiquetaPar.SUSTENTA, 0.9, "copiaspam.com") for _ in range(100)]
    originales = [
        _par(EtiquetaPar.REFUTA, 0.9, "fuente1.org"),
        _par(EtiquetaPar.REFUTA, 0.9, "fuente2.org"),
    ]
    resultado = agregar_hecho(HECHO, copias + originales)
    assert resultado.veredicto is Veredicto.REFUTADO


def _vh(veredicto: Veredicto, confianza: float = 0.8) -> VeredictoHecho:
    return VeredictoHecho(hecho=HECHO, veredicto=veredicto, confianza=confianza)


def test_informe_un_hecho_refutado_refuta_todo():
    hechos = [_vh(Veredicto.SUSTENTADO), _vh(Veredicto.REFUTADO, 0.7)]
    informe = agregar_informe("afirmación", hechos)
    assert informe.veredicto is Veredicto.REFUTADO
    assert informe.confianza == 0.7


def test_informe_sustentado_solo_si_todos_sustentados():
    hechos = [_vh(Veredicto.SUSTENTADO), _vh(Veredicto.INSUFICIENTE, 0.0)]
    assert agregar_informe("afirmación", hechos).veredicto is Veredicto.INSUFICIENTE


def test_informe_todo_sustentado():
    hechos = [_vh(Veredicto.SUSTENTADO, 0.9), _vh(Veredicto.SUSTENTADO, 0.6)]
    informe = agregar_informe("afirmación", hechos)
    assert informe.veredicto is Veredicto.SUSTENTADO
    assert informe.confianza == 0.6  # tan cierto como su hecho más débil

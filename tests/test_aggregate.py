"""Aggregator tests: the comparative logic must be predictable and auditable."""

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
    pares = [_par(EtiquetaPar.SUSTENTA, 0.55, "d1.org")]  # below the 0.60 threshold
    assert agregar_hecho(HECHO, pares).veredicto is Veredicto.INSUFICIENTE


def test_refutacion_dominante_refuta():
    pares = [
        _par(EtiquetaPar.REFUTA, 0.95, "d1.org"),
        _par(EtiquetaPar.REFUTA, 0.90, "d2.org"),
        _par(EtiquetaPar.SUSTENTA, 0.65, "d3.org"),
    ]
    assert agregar_hecho(HECHO, pares).veredicto is Veredicto.REFUTADO


def test_conflicto_real_exige_fiabilidad_en_ambos_lados():
    """Tie with credible evidence on both sides = genuine contradiction."""
    pares = [
        _par(EtiquetaPar.SUSTENTA, 0.85, "es.wikipedia.org"),
        _par(EtiquetaPar.REFUTA, 0.80, "politifact.com"),
        _par(EtiquetaPar.SUSTENTA, 0.9, "viral1.com"),
        _par(EtiquetaPar.SUSTENTA, 0.9, "viral2.com"),
    ]
    assert agregar_hecho(HECHO, pares).veredicto is Veredicto.CONTRADICTORIO


def test_ruido_web_no_establece_conflicto():
    """The measured AVeriTeC pattern: viral supports in bulk, one credible
    debunk refutes, the signal ties — but that's not conflict: it's refutation."""
    pares = [
        _par(EtiquetaPar.SUSTENTA, 0.97, "viral1.com"),
        _par(EtiquetaPar.SUSTENTA, 0.96, "viral2.com"),
        _par(EtiquetaPar.SUSTENTA, 0.95, "viral3.com"),
        _par(EtiquetaPar.SUSTENTA, 0.95, "viral4.com"),
        _par(EtiquetaPar.SUSTENTA, 0.94, "viral5.com"),
        _par(EtiquetaPar.REFUTA, 0.95, "politifact.com"),
    ]
    assert agregar_hecho(HECHO, pares).veredicto is Veredicto.REFUTADO


def test_empate_sin_fiabilidad_gana_la_mayoria():
    """Weak web against weak web: the comparative logic picks the side with
    more signal, with naturally low confidence."""
    pares = [
        _par(EtiquetaPar.SUSTENTA, 0.85, "d1.org"),
        _par(EtiquetaPar.SUSTENTA, 0.7, "d3.org"),
        _par(EtiquetaPar.REFUTA, 0.80, "d2.org"),
    ]
    resultado = agregar_hecho(HECHO, pares)
    assert resultado.veredicto is Veredicto.SUSTENTADO
    assert resultado.confianza < 0.7


def test_cien_copias_cuentan_como_una_voz():
    """Independence: the same domain doesn't win by repetition."""
    copias = [_par(EtiquetaPar.SUSTENTA, 0.9, "copiaspam.com") for _ in range(100)]
    originales = [
        _par(EtiquetaPar.REFUTA, 0.9, "fuente1.org"),
        _par(EtiquetaPar.REFUTA, 0.9, "fuente2.org"),
    ]
    resultado = agregar_hecho(HECHO, copias + originales)
    assert resultado.veredicto is Veredicto.REFUTADO


def test_un_verificador_le_gana_a_la_mentira_viral():
    """Reliability priors: the AVeriTeC case — many sites repeat the lie,
    one fact-checker debunks it. The fact-checker must win."""
    virales = [
        _par(EtiquetaPar.SUSTENTA, 0.95, f"viral{i}.com") for i in range(3)
    ]
    desmentido = [_par(EtiquetaPar.REFUTA, 0.95, "politifact.com")]
    resultado = agregar_hecho(HECHO, virales + desmentido)
    assert resultado.veredicto is Veredicto.REFUTADO


HECHO_VIRAL = HechoAtomico(
    texto="En una carta a Steve Jobs, Sean Connery rechazó aparecer en un comercial de Apple",
    origen="…",
)


def test_el_eco_no_es_evidencia():
    """A web snippet that only repeats a viral claim weighs little as support."""
    evidencia_eco = Evidencia(
        texto="Viral: en una carta a Steve Jobs, Sean Connery rechazó aparecer "
        "en un comercial de Apple, según reportes",
        url="https://viral.com/x",
        titulo="t",
        dominio="viral.com",
        fuente="web",
    )
    eco = VeredictoPar(
        hecho=HECHO_VIRAL, evidencia=evidencia_eco, etiqueta=EtiquetaPar.SUSTENTA, prob=0.95
    )
    contra = [
        VeredictoPar(
            hecho=HECHO_VIRAL,
            evidencia=Evidencia(
                texto="La carta es una sátira fabricada; el actor nunca la escribió",
                url="https://museo.org/x",
                titulo="t",
                dominio="museo.org",
                fuente="web",
            ),
            etiqueta=EtiquetaPar.REFUTA,
            prob=0.75,
        )
    ]
    resultado = agregar_hecho(HECHO_VIRAL, [eco] + contra)
    assert resultado.veredicto is Veredicto.REFUTADO


def test_afirmacion_tecnica_corta_no_es_eco():
    """Regression measured in /verify: for short claims («Python lists are
    mutable») every legitimate passage contains its words — coverage, not echo."""
    evidencia = Evidencia(
        texto="Python lists are mutable: you can add, remove or change elements "
        "in place with append, pop or slicing",
        url="https://tutorial.org/x",
        titulo="t",
        dominio="tutorial.org",
        fuente="web",
    )
    hecho_corto = HechoAtomico(texto="Python lists are mutable", origen="…")
    par = VeredictoPar(
        hecho=hecho_corto, evidencia=evidencia, etiqueta=EtiquetaPar.SUSTENTA, prob=0.95
    )
    resultado = agregar_hecho(hecho_corto, [par])
    assert resultado.veredicto is Veredicto.SUSTENTADO
    assert resultado.confianza > 0.3  # without the echo penalty


def test_la_trampa_de_la_atribucion():
    """A passage that 'supports' but describes the hoax ('purportedly', 'hoax')
    is a misread debunk: its support barely weighs."""
    trampa = VeredictoPar(
        hecho=HECHO,
        evidencia=Evidencia(
            texto="Viral video purportedly shows the tower being in Paris, "
            "a claim fact-checkers call misleading",
            url="https://noticias.com/x",
            titulo="t",
            dominio="noticias.com",
            fuente="web",
        ),
        etiqueta=EtiquetaPar.SUSTENTA,
        prob=0.95,
    )
    contra = [_par(EtiquetaPar.REFUTA, 0.8, "otra.org")]
    resultado = agregar_hecho(HECHO, [trampa] + contra)
    assert resultado.veredicto is Veredicto.REFUTADO


def test_un_dominio_una_voz():
    """A fact-check narrates the myth (a 'supporting' passage) before
    debunking it (a stronger 'refuting' passage): the domain votes once,
    with its strongest signal."""
    pares = [
        _par(EtiquetaPar.SUSTENTA, 0.78, "chequeado.com"),
        _par(EtiquetaPar.REFUTA, 0.95, "chequeado.com"),
    ]
    resultado = agregar_hecho(HECHO, pares)
    assert resultado.veredicto is Veredicto.REFUTADO
    assert not resultado.a_favor  # narrating the myth doesn't count as a voice


def test_wikipedia_sustenta_aunque_haya_eco_en_contrario():
    """The priors don't break the legitimate case: encyclopedia + web agree."""
    pares = [
        _par(EtiquetaPar.SUSTENTA, 0.9, "es.wikipedia.org"),
        _par(EtiquetaPar.SUSTENTA, 0.9, "detallada.org"),
        _par(EtiquetaPar.REFUTA, 0.7, "confuso.com"),
    ]
    assert agregar_hecho(HECHO, pares).veredicto is Veredicto.SUSTENTADO


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
    assert informe.confianza == 0.6  # only as true as its weakest fact

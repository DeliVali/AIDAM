"""Investigation cascade: signals, escalation, angle judging, auditable re-aggregation.

No network, no models: retrieval is monkeypatched at the `aidam.retrieve`
module (the orchestrator resolves it lazily at call time) and the verifier is
a local programmable fake honoring the `juzgar` contract.
"""

from __future__ import annotations

from aidam import retrieve
from aidam.agente.orquestador import (
    SenalesEscalado,
    desacuerdo,
    hay_que_escalar,
    investigar,
    medir_senales,
)
from aidam.models import EtiquetaPar, Evidencia, HechoAtomico, Veredicto, VeredictoPar

AFIRMACION = "La torre Eiffel está en París"


def _ev(dominio, texto, fuente="wikipedia"):
    return Evidencia(texto=texto, url=f"https://{dominio}/x", titulo="t",
                     dominio=dominio, fuente=fuente)


class _Verificador:
    """Deterministic fake: label depends on the evidence text and the hypothesis.

    - texts containing "inconcluso" → NO_CONCLUYE
    - negated hypothesis (contains " no ") → REFUTA (the evidence refutes the negation)
    - otherwise → SUSTENTA
    """

    def juzgar(self, hecho, evidencias):
        pares = []
        for evidencia in evidencias:
            if "inconcluso" in evidencia.texto:
                etiqueta = EtiquetaPar.NO_CONCLUYE
            elif " no " in f" {hecho.texto} ":
                etiqueta = EtiquetaPar.REFUTA
            else:
                etiqueta = EtiquetaPar.SUSTENTA
            pares.append(VeredictoPar(hecho, evidencia, etiqueta, 0.9))
        return pares

    def puntuar_entailment(self, premisa, hipotesis):
        return [0.0] * len(hipotesis)  # router stays on "general"


# ───────── señales puras ─────────

def test_desacuerdo():
    assert desacuerdo([]) == 0.0
    assert desacuerdo([Veredicto.SUSTENTADO]) == 0.0
    assert desacuerdo([Veredicto.SUSTENTADO, Veredicto.SUSTENTADO]) == 0.0
    assert desacuerdo([Veredicto.SUSTENTADO, Veredicto.REFUTADO]) == 0.5


def test_hay_que_escalar():
    base = SenalesEscalado(confianza=0.9, conflicto=False, insuficiente=False)
    assert not hay_que_escalar(base)
    assert hay_que_escalar(SenalesEscalado(0.3, False, False))
    assert hay_que_escalar(SenalesEscalado(0.9, True, False))
    assert hay_que_escalar(SenalesEscalado(0.9, False, True))


def test_medir_senales_detecta_conflicto():
    hecho = HechoAtomico(AFIRMACION, "test")
    fuerte_favor = VeredictoPar(hecho, _ev("a.com", "x"), EtiquetaPar.SUSTENTA, 0.9)
    fuerte_contra = VeredictoPar(hecho, _ev("b.com", "y"), EtiquetaPar.REFUTA, 0.8)
    from aidam.aggregate import agregar_hecho, agregar_informe

    informe = agregar_informe(AFIRMACION, [agregar_hecho(hecho, [fuerte_favor, fuerte_contra])])
    assert medir_senales(informe).conflicto is True


# ───────── cascada ─────────

def test_tier0_confiado_no_escala(monkeypatch):
    llamadas_web = []
    monkeypatch.setattr(retrieve, "recuperar", lambda hecho, **kw: [
        _ev("a.org", "la torre se alza en la capital francesa"),
        _ev("b.org", "el monumento parisino de hierro"),
        _ev("c.org", "situada en el campo de Marte"),
    ])
    monkeypatch.setattr(retrieve, "buscar_web", lambda *a, **kw: llamadas_web.append(a) or [])

    resultado = investigar(AFIRMACION, verificador=_Verificador())
    assert resultado.informe.veredicto is Veredicto.SUSTENTADO
    assert resultado.nivel == 0
    assert resultado.angulos == []
    assert llamadas_web == []  # never escalated → never searched


def test_nivel_forzado_cero_nunca_escala(monkeypatch):
    monkeypatch.setattr(retrieve, "recuperar", lambda hecho, **kw: [
        _ev("a.org", "dato inconcluso sobre el tema"),
    ])
    monkeypatch.setattr(
        retrieve, "buscar_web",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no debió buscar")),
    )
    resultado = investigar(AFIRMACION, nivel=0, verificador=_Verificador())
    assert resultado.nivel == 0
    assert resultado.informe.veredicto is Veredicto.INSUFICIENTE


def test_insuficiente_escala_y_resuelve_con_negacion(monkeypatch):
    # tier-0 finds only inconclusive evidence; the negation angle retrieves
    # three fresh domains whose evidence refutes the negation → supports the
    # claim after inversion, re-aggregated by the SAME auditable rules.
    monkeypatch.setattr(retrieve, "recuperar", lambda hecho, **kw: [
        _ev("a.org", "dato inconcluso sobre el tema"),
    ])
    monkeypatch.setattr(retrieve, "buscar_web", lambda consulta, **kw: [
        _ev("a.org", "dato inconcluso sobre el tema"),  # duplicate → must be deduped
        _ev("b.org", "el monumento está en la capital"),
        _ev("c.org", "torre situada junto al Sena"),
        _ev("d.org", "icono de la ciudad de París"),
    ])

    resultado = investigar(AFIRMACION, verificador=_Verificador())
    assert resultado.nivel == 1
    assert resultado.informe.veredicto is Veredicto.SUSTENTADO
    assert [a.nombre for a in resultado.angulos] == ["negacion"]
    assert resultado.angulos[0].evidencias == 3  # the duplicate was dropped
    # Inverted pairs must speak about the ORIGINAL fact, not the negation.
    a_favor = resultado.informe.hechos[0].a_favor
    assert a_favor and all(par.hecho.texto == AFIRMACION for par in a_favor)


def test_nivel_forzado_dos_cubre_todos_los_hechos(monkeypatch):
    monkeypatch.setattr(retrieve, "recuperar", lambda hecho, **kw: [
        _ev("a.org", "la torre se alza en la capital francesa"),
        _ev("b.org", "el monumento parisino de hierro"),
        _ev("c.org", "situada en el campo de Marte"),
    ])
    monkeypatch.setattr(retrieve, "buscar_web", lambda consulta, **kw: [
        _ev("e.org", f"pasaje nuevo para {consulta[:30]}"),
    ])
    resultado = investigar(AFIRMACION, nivel=2, verificador=_Verificador())
    # Forced level runs both escalation rounds even though tier-0 was confident.
    assert resultado.nivel == 2
    assert len(resultado.angulos) >= 1
    assert resultado.informe.veredicto is Veredicto.SUSTENTADO


def test_busqueda_rota_no_tumba(monkeypatch):
    monkeypatch.setattr(retrieve, "recuperar", lambda hecho, **kw: [
        _ev("a.org", "dato inconcluso sobre el tema"),
    ])
    def _explota(*a, **kw):
        raise RuntimeError("motor caído")
    monkeypatch.setattr(retrieve, "buscar_web", _explota)

    resultado = investigar(AFIRMACION, verificador=_Verificador())
    # Escalation found nothing (search down) but the investigation survives.
    assert resultado.informe.veredicto is Veredicto.INSUFICIENTE
    assert resultado.nivel == 2  # it tried both levels before giving up

"""Investigation angles: negation heuristics, pair inversion, level caps."""

from __future__ import annotations

from aidam.agente.angulos import Angulo, generar_angulos, invertir_pares, negar_afirmacion
from aidam.models import EtiquetaPar, Evidencia, HechoAtomico, VeredictoPar


def _par(etiqueta, prob=0.9):
    hecho = HechoAtomico("la torre está en París", "test")
    evidencia = Evidencia("texto", "https://x", "t", "x.com", "web")
    return VeredictoPar(hecho, evidencia, etiqueta, prob)


# ───────── negación ─────────

def test_negar_espanol_inserta_no():
    assert negar_afirmacion("La torre Eiffel es de hierro") == "La torre Eiffel no es de hierro"


def test_negar_espanol_quita_no():
    assert negar_afirmacion("La torre no es de hierro") == "La torre es de hierro"


def test_negar_ingles():
    assert negar_afirmacion("The tower is made of iron") == "The tower is not made of iron"
    assert negar_afirmacion("The tower is not made of iron") == "The tower is made of iron"


def test_negar_sin_regla_devuelve_none():
    # No copula/auxiliary to hook onto: better no negation than an invented one.
    assert negar_afirmacion("¡Vaya con el fútbol!") is None


# ───────── inversión de pares ─────────

def test_invertir_pares_mapea_y_no_muta():
    originales = [_par(EtiquetaPar.SUSTENTA), _par(EtiquetaPar.REFUTA),
                  _par(EtiquetaPar.NO_CONCLUYE)]
    invertidos = invertir_pares(originales)
    assert [p.etiqueta for p in invertidos] == [
        EtiquetaPar.REFUTA, EtiquetaPar.SUSTENTA, EtiquetaPar.NO_CONCLUYE
    ]
    assert [p.etiqueta for p in originales] == [
        EtiquetaPar.SUSTENTA, EtiquetaPar.REFUTA, EtiquetaPar.NO_CONCLUYE
    ]
    assert invertidos[0].prob == originales[0].prob


# ───────── generación ─────────

class _Generador:
    def preguntas(self, texto, n=3, lang="es"):
        return [f"reformulación {i} de {texto}" for i in range(n)]


def test_nivel_cero_no_genera():
    assert generar_angulos("la torre es de hierro", 0) == []


def test_nivel_uno_sin_generador_solo_negacion():
    angulos = generar_angulos("la torre es de hierro", 1)
    assert [a.nombre for a in angulos] == ["negacion"]
    assert angulos[0].invertido is True


def test_nivel_dos_con_generador_mas_angulos_y_dedup():
    angulos = generar_angulos("la torre es de hierro", 2, generador=_Generador())
    assert len(angulos) <= 6
    nombres = {a.nombre for a in angulos}
    assert "negacion" in nombres and "reformulacion" in nombres
    consultas = [a.consulta.casefold() for a in angulos]
    assert len(consultas) == len(set(consultas))
    assert "la torre es de hierro" not in consultas


def test_generador_que_falla_no_tumba():
    class _Roto:
        def preguntas(self, *args, **kwargs):
            raise RuntimeError("worker muerto")

    angulos = generar_angulos("la torre es de hierro", 1, generador=_Roto())
    assert [a.nombre for a in angulos] == ["negacion"]

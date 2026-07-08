"""Tests for the question parser and the omission judge (no model)."""

from aidam.questions import _extraer_preguntas, _parsear_omision


def test_parsear_omision():
    assert _parsear_omision("MISLEADING") == "enganosa"
    assert _parsear_omision("COMPLETE.") == "completa"
    assert _parsear_omision("<think>hmm MISLEADING?</think>COMPLETE") == "completa"
    assert _parsear_omision("no estoy seguro") is None


def test_extrae_preguntas_numeradas():
    salida = "1. ¿Dónde está la Torre Eiffel?\n2. ¿Cuándo se construyó la Torre Eiffel?"
    assert _extraer_preguntas(salida, 3) == [
        "¿Dónde está la Torre Eiffel?",
        "¿Cuándo se construyó la Torre Eiffel?",
    ]


def test_descarta_bloque_de_razonamiento():
    salida = (
        "<think>El usuario quiere preguntas. ¿Debería pensar más?</think>\n"
        "- ¿Quién diseñó la Torre Eiffel?"
    )
    assert _extraer_preguntas(salida, 3) == ["¿Quién diseñó la Torre Eiffel?"]


def test_descarta_bloque_de_razonamiento_sin_cerrar():
    salida = "<think>hmm esto no termina nunca y pregunta cosas ¿verdad?"
    assert _extraer_preguntas(salida, 3) == []


def test_descarta_lineas_sin_interrogacion_y_duplicados():
    salida = (
        "Aquí están las preguntas:\n"
        "* ¿Qué altura tiene la torre?\n"
        "* ¿Qué altura tiene la torre?\n"
        "Espero que sirvan."
    )
    assert _extraer_preguntas(salida, 3) == ["¿Qué altura tiene la torre?"]


def test_separa_varias_preguntas_en_una_linea():
    salida = "¿Cuál es la distancia a la Luna? ¿Qué altura tiene la muralla?"
    assert _extraer_preguntas(salida, 3) == [
        "¿Cuál es la distancia a la Luna?",
        "¿Qué altura tiene la muralla?",
    ]


def test_acepta_consultas_de_busqueda_sin_interrogacion():
    """DeepSeek-R1 emits `search "..."`-style queries instead of questions."""
    salida = 'search "Sean Connery letter Steve Jobs"\nsearch "Connery Apple commercial"'
    assert _extraer_preguntas(salida, 3) == [
        "Sean Connery letter Steve Jobs",
        "Connery Apple commercial",
    ]


def test_respeta_el_limite():
    salida = "\n".join(f"{i}. ¿Pregunta número {i} de prueba?" for i in range(1, 6))
    assert len(_extraer_preguntas(salida, 2)) == 2

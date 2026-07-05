"""Tests del parser de preguntas (sin modelo)."""

from aidam.preguntas import _extraer_preguntas


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


def test_respeta_el_limite():
    salida = "\n".join(f"{i}. ¿Pregunta número {i} de prueba?" for i in range(1, 6))
    assert len(_extraer_preguntas(salida, 2)) == 2

"""Tests del router de categorías (nivel de palabras clave, sin modelo)."""

from aidam.router import CATEGORIAS, clasificar, clasificar_por_palabras


def test_programacion():
    assert clasificar_por_palabras("El bug está en la función de Python") == "programacion"


def test_medicina():
    assert clasificar_por_palabras("La vacuna reduce los síntomas del virus") == "medicina"


def test_ciencia():
    assert clasificar_por_palabras("Un estudio de la NASA sobre el clima") == "ciencia"


def test_actualidad():
    assert clasificar_por_palabras("El presidente firmó la ley en el congreso") == "actualidad"


def test_general_por_defecto():
    assert clasificar_por_palabras("La Torre Eiffel está en París") == "general"


def test_funciona_en_ingles():
    assert clasificar_por_palabras("The president won the election") == "actualidad"
    assert clasificar_por_palabras("This drug treats the disease") == "medicina"


def test_medicina_cubre_cardiologia():
    """Regresión medida en /verify: aspirina/infarto caía en 'general' y
    perdía las fuentes biomédicas."""
    assert clasificar_por_palabras("Aspirin reduces the risk of heart attack") == "medicina"
    assert clasificar_por_palabras("La aspirina reduce el riesgo de infarto") == "medicina"


def test_sin_verificador_no_explota():
    assert clasificar("La Torre Eiffel está en París", verificador=None) == "general"


def test_todas_las_categorias_declaradas():
    assert set(CATEGORIAS) == {"programacion", "medicina", "ciencia", "actualidad", "general"}

"""Category router tests (keyword level, no model)."""

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


def test_infraestructura_es_programacion():
    """Commands and cloud go to the certified technical sources."""
    assert clasificar_por_palabras("aws s3 cp copia archivos a un bucket") == "programacion"
    assert clasificar_por_palabras("kubectl get pods lista los pods de Kubernetes") == "programacion"


def test_matematicas():
    assert clasificar_por_palabras("La integral de x es x²/2 más una constante") == "matematicas"
    assert clasificar_por_palabras("There are infinitely many prime numbers by Euclid's theorem") == "matematicas"


def test_medicina_cubre_cardiologia():
    """Regression measured in /verify: aspirin/heart attack fell into
    'general' and lost the biomedical sources."""
    assert clasificar_por_palabras("Aspirin reduces the risk of heart attack") == "medicina"
    assert clasificar_por_palabras("La aspirina reduce el riesgo de infarto") == "medicina"


def test_sin_verificador_no_explota():
    assert clasificar("La Torre Eiffel está en París", verificador=None) == "general"


def test_todas_las_categorias_declaradas():
    assert set(CATEGORIAS) == {
        "programacion", "matematicas", "medicina", "ciencia", "actualidad", "general"
    }

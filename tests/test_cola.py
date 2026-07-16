"""Work-queue tests: atomic claims under threads and file persistence."""

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from aidam.agente.cola import ColaTrabajo, EstadoTarea


def _estado_en_bd(ruta, id_tarea: int) -> tuple:
    """Reads (estado, resultado, error) straight from the SQLite file."""
    conexion = sqlite3.connect(str(ruta))
    fila = conexion.execute(
        "SELECT estado, resultado, error FROM tareas WHERE id = ?", (id_tarea,)
    ).fetchone()
    conexion.close()
    return fila


def test_ciclo_encolar_tomar_completar():
    cola = ColaTrabajo()
    id_tarea = cola.encolar("verificar", {"texto": "la torre está en París"})
    assert cola.pendientes() == 1

    tarea = cola.tomar()
    assert tarea is not None
    assert tarea.id == id_tarea
    assert tarea.tipo == "verificar"
    assert tarea.carga == {"texto": "la torre está en París"}
    assert tarea.estado is EstadoTarea.EN_CURSO
    assert cola.pendientes() == 0

    cola.completar(tarea.id, {"veredicto": "sustentado"})
    assert cola.tomar() is None  # done tasks are never re-claimed
    cola.cerrar()


def test_tomar_sin_tareas_devuelve_none():
    cola = ColaTrabajo()
    assert cola.tomar() is None
    cola.cerrar()


def test_fallar_saca_la_tarea_de_la_cola():
    cola = ColaTrabajo()
    id_tarea = cola.encolar("verificar", {"n": 1})
    tarea = cola.tomar()
    cola.fallar(tarea.id, "sin red")
    assert cola.tomar() is None
    assert cola.pendientes() == 0
    # A failed task is not an orphan: it must not be requeued.
    assert cola.reanudar_huerfanas() == 0
    assert id_tarea == tarea.id
    cola.cerrar()


def test_tomar_es_atomico_bajo_hilos():
    """8 threads draining 200 tasks: each task claimed exactly once."""
    cola = ColaTrabajo()
    total = 200
    for i in range(total):
        cola.encolar("t", {"n": i})

    reclamadas: list[int] = []
    candado = threading.Lock()

    def trabajador() -> None:
        while True:
            tarea = cola.tomar()
            if tarea is None:
                return
            with candado:
                reclamadas.append(tarea.id)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for futuro in [pool.submit(trabajador) for _ in range(8)]:
            futuro.result()

    assert len(reclamadas) == total  # nothing lost
    assert len(set(reclamadas)) == total  # nothing claimed twice
    assert cola.pendientes() == 0
    cola.cerrar()


def test_filtro_por_tipo():
    cola = ColaTrabajo()
    cola.encolar("a", {"n": 1})
    id_b = cola.encolar("b", {"n": 2})
    cola.encolar("a", {"n": 3})

    assert cola.pendientes("a") == 2
    assert cola.pendientes("b") == 1
    assert cola.tomar("c") is None

    tarea = cola.tomar("b")
    assert tarea.id == id_b
    assert cola.pendientes("b") == 0
    assert cola.pendientes("a") == 2  # the other type is untouched
    cola.cerrar()


def test_reanudar_huerfanas():
    cola = ColaTrabajo()
    for i in range(3):
        cola.encolar("t", {"n": i})
    primera = cola.tomar()
    cola.tomar()
    cola.completar(primera.id, {"ok": True})
    # One EN_CURSO orphan (simulated dead process) and one still pending.
    assert cola.reanudar_huerfanas() == 1
    assert cola.pendientes() == 2
    assert cola.reanudar_huerfanas() == 0  # idempotent once recovered
    cola.cerrar()


def test_persistencia_en_archivo(tmp_path):
    ruta = tmp_path / "cola.db"
    cola = ColaTrabajo(ruta)
    id_a = cola.encolar("verificar", {"texto": "a"})
    id_b = cola.encolar("verificar", {"texto": "b"})
    id_c = cola.encolar("verificar", {"texto": "c"})

    cola.completar(cola.tomar().id, {"veredicto": "sustentado"})  # a (FIFO)
    cola.fallar(cola.tomar().id, "sin evidencia")  # b
    cola.cerrar()

    reabierta = ColaTrabajo(ruta)
    assert reabierta.pendientes() == 1
    restante = reabierta.tomar()
    assert restante.id == id_c
    assert restante.carga == {"texto": "c"}
    reabierta.cerrar()

    estado, resultado, error = _estado_en_bd(ruta, id_a)
    assert estado == "hecha"
    assert json.loads(resultado) == {"veredicto": "sustentado"}
    assert error is None
    estado, resultado, error = _estado_en_bd(ruta, id_b)
    assert estado == "fallida"
    assert error == "sin evidencia"

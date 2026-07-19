"""The task reasoner (ReAct cycle): parsing, budgets, grounding, audit.

No GPU, no network, no real models: the generator is a scripted fake, the
tools are recording lambdas, the verifier returns scripted entailment.
"""

import json

from aidam.agente.auditoria import RegistroAuditoria
from aidam.agente.herramientas import Herramienta
from aidam.agente.razonador import (
    _extraer_accion,
    ejecutar_tarea,
    interpretar_tarea,
    revisar_respuesta,
)


class FakeGenerador:
    """Returns scripted completions in order; repeats the last one after."""

    def __init__(self, salidas):
        self.salidas = list(salidas)
        self.prompts = []

    def completar(self, prompt, max_tokens, temperature, stop=None):
        self.prompts.append(prompt)
        if len(self.salidas) > 1:
            return self.salidas.pop(0)
        return self.salidas[0]


class FakeVerificador:
    def __init__(self, puntaje=0.9):
        self.puntaje = puntaje

    def puntuar_entailment(self, premisa, hipotesis):
        return [self.puntaje for _ in hipotesis]


def _herramientas(registro):
    def leer(ruta):
        registro.append(("leer", ruta))
        return f"contenido de {ruta}"

    def rota(**_kwargs):
        raise RuntimeError("boom")

    return {
        "leer_archivo": Herramienta("leer_archivo", "lee", {"ruta": "str"}, leer),
        "rota": Herramienta("rota", "siempre falla", {}, rota),
    }


def _accion(nombre, **argumentos):
    return json.dumps({"herramienta": nombre, "argumentos": argumentos})


# ── parsing ────────────────────────────────────────────────────────────────────

def test_parsea_json_limpio():
    p, h, a = _extraer_accion('{"herramienta": "leer_archivo", "argumentos": {"ruta": "x"}}')
    assert h == "leer_archivo" and a == {"ruta": "x"}


def test_parsea_tras_bloque_think_y_prosa():
    texto = ("<think>largo razonamiento</think>Voy a leer el archivo.\n"
             '{"herramienta": "leer_archivo", "argumentos": {"ruta": "x"}}')
    p, h, a = _extraer_accion(texto)
    assert h == "leer_archivo" and "razonamiento" in p


def test_gana_la_primera_accion_y_el_plan_se_descarta():
    # Measured on the real 8B: the model plans the whole sequence in one
    # step; only the FIRST action runs, the imagined rest is discarded.
    texto = ('{"herramienta": "leer_archivo", "argumentos": {"ruta": "y"}}\n'
             '{"herramienta": "responder", "argumentos": {"texto": "he leído"}}'
             " y más divagación")
    _, h, a = _extraer_accion(texto)
    assert h == "leer_archivo" and a == {"ruta": "y"}


def test_texto_roto_devuelve_none():
    assert _extraer_accion("no hay json aquí") is None
    assert _extraer_accion('{"otra_cosa": 1}') is None


# ── the cycle ──────────────────────────────────────────────────────────────────

def test_ciclo_actua_y_responde(tmp_path):
    registro = []
    generador = FakeGenerador([
        _accion("leer_archivo", ruta="a.txt"),
        _accion("responder", texto="El archivo dice: contenido de a.txt"),
    ])
    auditoria = RegistroAuditoria(ruta=tmp_path / "a.jsonl")
    resultado = ejecutar_tarea(
        "lee a.txt", _herramientas(registro), generador, auditoria,
        verificador=FakeVerificador(),
    )
    assert resultado.terminado_por == "respuesta"
    assert registro == [("leer", "a.txt")]
    assert "contenido de a.txt" in resultado.respuesta
    lineas = (tmp_path / "a.jsonl").read_text().strip().splitlines()
    assert len(lineas) == 2  # one audit line per step
    assert all(json.loads(l)["herramienta"] == "Razonador" for l in lineas)


def test_reintento_unico_y_error_llm_visible(tmp_path):
    generador = FakeGenerador(["bla sin json"])
    resultado = ejecutar_tarea(
        "haz algo", _herramientas([]), generador,
        RegistroAuditoria(ruta=tmp_path / "a.jsonl"),
    )
    assert resultado.terminado_por == "error_llm"
    assert len(generador.prompts) == 2  # original + one corrective retry
    assert "no produjo acciones válidas" in resultado.respuesta


def test_presupuesto_termina_el_codigo(tmp_path):
    generador = FakeGenerador([_accion("leer_archivo", ruta="a.txt")])
    resultado = ejecutar_tarea(
        "lee sin parar", _herramientas([]), generador,
        RegistroAuditoria(ruta=tmp_path / "a.jsonl"), max_pasos=3,
    )
    assert resultado.terminado_por == "presupuesto"
    assert len(resultado.pasos) == 3
    assert "presupuesto de 3 pasos" in resultado.respuesta


def test_herramienta_rota_no_mata_el_ciclo(tmp_path):
    generador = FakeGenerador([
        _accion("rota"),
        _accion("responder", texto="hubo un error con la herramienta"),
    ])
    resultado = ejecutar_tarea(
        "prueba", _herramientas([]), generador,
        RegistroAuditoria(ruta=tmp_path / "a.jsonl"),
    )
    assert resultado.terminado_por == "respuesta"
    assert resultado.pasos[0].observacion.startswith("error:")


def test_herramienta_desconocida_se_contiene(tmp_path):
    generador = FakeGenerador([
        _accion("inventada", x=1),
        _accion("responder", texto="listo"),
    ])
    resultado = ejecutar_tarea(
        "prueba", _herramientas([]), generador,
        RegistroAuditoria(ruta=tmp_path / "a.jsonl"),
    )
    assert "herramienta desconocida" in resultado.pasos[0].observacion


# ── grounding gate ─────────────────────────────────────────────────────────────

def test_frase_verbatim_pasa_sin_marca():
    observaciones = ["El Louvre exhibe la Mona Lisa desde 1797 en París."]
    texto, marcadas = revisar_respuesta(
        "El Louvre exhibe la Mona Lisa desde 1797 en París.",
        observaciones, FakeVerificador(puntaje=0.0),
    )
    assert marcadas == []
    assert "sin verificar" not in texto


def test_frase_sin_sustento_se_marca_no_se_borra():
    observaciones = ["El museo abre de martes a domingo por la mañana."]
    frase = "La pintura fue robada tres veces durante el siglo veinte."
    texto, marcadas = revisar_respuesta(
        frase, observaciones, FakeVerificador(puntaje=0.1),
    )
    assert marcadas == [frase]
    assert frase in texto and "«[sin verificar]»" in texto


def test_frase_con_sustento_nli_pasa():
    observaciones = ["La Gioconda cuelga en el museo del Louvre de París."]
    texto, marcadas = revisar_respuesta(
        "La Mona Lisa se encuentra en el Louvre, en la capital francesa.",
        observaciones, FakeVerificador(puntaje=0.95),
    )
    assert marcadas == []


def test_sin_observaciones_marca_todo_lo_factual():
    # T4 run #2, probe 15: a confident fabrication with zero tool use
    # skipped the gate entirely. Now: no observations → factual-shaped
    # sentences are marked and the answer leads with the warning.
    texto, marcadas = revisar_respuesta(
        "El verdanio es un elemento químico.", [], FakeVerificador(),
    )
    assert marcadas == ["El verdanio es un elemento químico."]
    assert texto.startswith("Aviso: respondí sin consultar ninguna fuente.")
    assert "«[sin verificar]»" in texto


def test_sin_verificador_solo_chequeo_extractivo():
    texto, marcadas = revisar_respuesta(
        "Una frase factual cualquiera que no está en lo observado.",
        ["otra cosa completamente distinta en la observación"], None,
    )
    assert marcadas == []  # nothing marked on grounds it could not measure


# ── task-act detection (chat surface) ─────────────────────────────────────────

def test_detecta_tareas_imperativas():
    assert interpretar_tarea("resume los archivos de esta carpeta") is not None
    assert interpretar_tarea("analiza el rendimiento del servidor y proponme mejoras") is not None
    assert interpretar_tarea("escribe un guion de bienvenida para el equipo") is not None


def test_no_captura_afirmaciones_ni_preguntas():
    assert interpretar_tarea("La Torre Eiffel está en París") is None
    assert interpretar_tarea("¿dónde está la muralla china?") is None
    assert interpretar_tarea("tienes un ejemplo de codigo") is None
    assert interpretar_tarea("El muro de Berlín cayó en 1989.") is None
    assert interpretar_tarea("corre") is None  # too short to be a task

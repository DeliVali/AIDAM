"""Resource-profile harness: the measured quality↔latency↔memory curve.

Program B (docs/AGENT.md §resource program). One invocation measures ONE
configuration (the current environment + any --entorno overrides) and
appends a JSON row to data/local/perfiles_recursos.jsonl:

- reasoner tokens/s (fixed 200-token completion, warm run),
- 6 offline micro-tasks (file ops, no web): pass rate, steps, s/step,
- peak worker RSS and GPU VRAM (nvidia-smi, worker pid),
- NLI verifier: pairs/s and label agreement vs the run tagged --referencia
  on 50 fixed template pairs (agreement, not gold: sweeps measure
  degradation against the baseline config, which is what GATE PERF needs).

GATE PERF (pre-registered): promote a config only at quality >=98% of the
profile's current default AND (latency -20% OR memory -25%); the harness
must first show <5% run-to-run variance on a repeated config.

Usage:
  .venv/bin/python evaluation/perfil_recursos.py --nombre base [--referencia]
  .venv/bin/python evaluation/perfil_recursos.py --nombre kv-q8 \
      --entorno AIDAM_MIMO_KV_TIPO=q8_0
  ... --sin-llm    # NLI-only (CPU profiles without the 8B)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SALIDA = Path("data/local/perfiles_recursos.jsonl")

# 50 fixed template pairs (deterministic; diversity matters, gold does not —
# the metric is agreement with the reference run's labels).
_CIUDADES = ["París", "Roma", "Lima", "Oslo", "Quito"]
_OBJETOS = ["el puente", "la torre", "el museo", "la catedral", "el estadio"]


def _pares_nli() -> list[tuple[str, str]]:
    pares = []
    for ciudad in _CIUDADES:
        for objeto in _OBJETOS:
            pares.append((f"{objeto.capitalize()} más famoso está en {ciudad}.",
                          f"{objeto} está en {ciudad}"))
            pares.append((f"{objeto.capitalize()} más famoso está en {ciudad}.",
                          f"{objeto} nunca estuvo en {ciudad}"))
    return pares[:50]


def _vram_pid(pid: int) -> int:
    try:
        salida = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        for linea in salida.splitlines():
            partes = [p.strip() for p in linea.split(",")]
            if len(partes) == 2 and partes[0] == str(pid):
                return int(partes[1])
    except Exception:
        pass
    return 0


def _rss_pid(pid: int) -> int:
    try:
        for linea in Path(f"/proc/{pid}/status").read_text().splitlines():
            if linea.startswith("VmRSS:"):
                return int(linea.split()[1]) // 1024  # MiB
    except OSError:
        pass
    return 0


class _Monitor(threading.Thread):
    """Polls the worker's RSS/VRAM peaks while measurements run."""

    def __init__(self, pid: int):
        super().__init__(daemon=True)
        self.pid, self.rss, self.vram, self._parar = pid, 0, 0, threading.Event()

    def run(self):
        while not self._parar.wait(1.0):
            self.rss = max(self.rss, _rss_pid(self.pid))
            self.vram = max(self.vram, _vram_pid(self.pid))


def _medir_llm(fila: dict) -> None:
    from aidam.questions import GeneradorPreguntas
    from aidam.agente.auditoria import RegistroAuditoria
    from aidam.agente.herramientas import crear_herramientas
    from aidam.agente.permisos import ModoPermisos, MotorPermisos
    from aidam.agente.razonador import ejecutar_tarea

    generador = GeneradorPreguntas()
    monitor = _Monitor(generador._proceso.pid)
    monitor.start()

    prompt = ("<|im_start|>user\nEscribe una lista numerada de veinte "
              "ciudades europeas con una frase sobre cada una.<|im_end|>\n"
              "<|im_start|>assistant\n<think>\n\n</think>\n")
    generador.completar(prompt, max_tokens=16, temperature=0.0)  # warm-up
    inicio = time.perf_counter()
    texto = generador.completar(prompt, max_tokens=200, temperature=0.0)
    duracion = time.perf_counter() - inicio
    # llama.cpp emits ~1 token per ~4 chars in Spanish; measure by chars to
    # avoid a tokenizer dependency — comparable ACROSS configs, which is all
    # the sweep needs.
    fila["llm_chars_s"] = round(len(texto) / duracion, 1)
    fila["llm_s_completar"] = round(duracion, 2)

    raiz = Path(tempfile.mkdtemp(prefix="aidam_perfil_"))
    (raiz / "datos.txt").write_text("uno\ndos\ntres\n", encoding="utf-8")
    motor = MotorPermisos(
        modo=ModoPermisos.LOTE,
        reglas={"permitir": [f"Escribir({raiz}/*)", f"Leer({raiz}/*)"]},
        raiz=raiz,
    )
    auditoria = RegistroAuditoria(ruta=raiz / "auditoria.jsonl")
    herramientas = crear_herramientas(motor, auditoria, raiz)
    micro = [
        (f"crea un archivo {raiz}/a.txt con el texto: hola", lambda: (raiz / "a.txt").exists()),
        (f"lee {raiz}/datos.txt y dime cuántas líneas tiene", lambda: True),
        (f"crea {raiz}/b.txt con dos colores, uno por línea", lambda: (raiz / "b.txt").exists()),
        (f"lee {raiz}/datos.txt y escribe su primera línea en {raiz}/c.txt",
         lambda: (raiz / "c.txt").exists()),
        (f"crea {raiz}/d.txt con el número cuarenta y dos", lambda: (raiz / "d.txt").exists()),
        (f"lee {raiz}/a.txt y dime qué contiene", lambda: True),
    ]
    pasadas, pasos_total, inicio = 0, 0, time.perf_counter()
    for tarea, chequeo in micro:
        resultado = ejecutar_tarea(tarea, herramientas, generador, auditoria, max_pasos=5)
        pasos_total += len(resultado.pasos)
        try:
            pasadas += bool(chequeo()) and resultado.terminado_por != "error_llm"
        except Exception:
            pass
    duracion = time.perf_counter() - inicio
    fila["tareas_pasadas"] = f"{pasadas}/6"
    fila["tareas_s_paso"] = round(duracion / max(pasos_total, 1), 1)
    fila["tareas_pasos"] = pasos_total

    monitor._parar.set()
    fila["llm_rss_mib"] = monitor.rss
    fila["llm_vram_mib"] = monitor.vram
    generador.cerrar()


def _medir_nli(fila: dict, referencia: bool) -> None:
    from aidam.models import Evidencia, HechoAtomico
    from aidam.verify import crear_verificador

    verificador = crear_verificador()
    pares = _pares_nli()
    inicio = time.perf_counter()
    etiquetas = []
    for premisa, hipotesis in pares:
        par = verificador.juzgar(
            HechoAtomico(texto=hipotesis, origen="sonda"),
            [Evidencia(texto=premisa, url="", titulo="", dominio="sonda", fuente="sonda")],
        )
        etiquetas.append(par[0].etiqueta.value if par else "?")
    duracion = time.perf_counter() - inicio
    fila["nli_pares_s"] = round(len(pares) / duracion, 1)
    fila["nli_etiquetas"] = etiquetas

    ruta_ref = Path("data/local/perfil_nli_referencia.json")
    if referencia:
        ruta_ref.parent.mkdir(parents=True, exist_ok=True)
        ruta_ref.write_text(json.dumps(etiquetas), encoding="utf-8")
        fila["nli_acuerdo"] = 1.0
    elif ruta_ref.exists():
        ref = json.loads(ruta_ref.read_text(encoding="utf-8"))
        fila["nli_acuerdo"] = round(
            sum(a == b for a, b in zip(etiquetas, ref)) / len(ref), 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nombre", required=True, help="etiqueta de la configuración")
    parser.add_argument("--entorno", default="",
                        help="overrides VAR=valor separados por comas")
    parser.add_argument("--referencia", action="store_true",
                        help="fija esta corrida como referencia de acuerdo NLI")
    parser.add_argument("--sin-llm", action="store_true")
    args = parser.parse_args()

    for par in filter(None, args.entorno.split(",")):
        variable, _, valor = par.partition("=")
        os.environ[variable.strip()] = valor.strip()

    fila: dict = {"config": args.nombre, "entorno": args.entorno,
                  "ts": time.strftime("%Y-%m-%d %H:%M")}
    if not args.sin_llm:
        _medir_llm(fila)
    _medir_nli(fila, args.referencia)

    _SALIDA.parent.mkdir(parents=True, exist_ok=True)
    visible = {k: v for k, v in fila.items() if k != "nli_etiquetas"}
    with open(_SALIDA, "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(json.dumps(visible, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

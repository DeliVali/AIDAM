"""Generador de preguntas de búsqueda (técnica ganadora de AVeriTeC 2.0).

En vez de buscar la afirmación literal (que devuelve páginas que la repiten),
un modelo de razonamiento genera las preguntas cuya respuesta la confirmaría
o refutaría, y esas preguntas se convierten en consultas de búsqueda. Los
sistemas ganadores del shared task AVeriTeC 2025 (CTU AIC, HerO 2) usan esta
técnica con LLMs abiertos.

Backend: MiMo-7B-RL de Xiaomi cuantizado (GGUF Q4, ~4.7 GB) vía llama.cpp —
razonamiento nivel o1-mini que corre en una GPU de consumo o CPU. Es opcional:
sin el modelo instalado, el pipeline funciona igual que antes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_RUTA_DEFECTO = Path(__file__).resolve().parent.parent / "modelos" / "mimo" / "MiMo-7B-RL-Q4_K_M.gguf"
_BLOQUE_PENSAMIENTO = re.compile(r"<think>.*?(</think>|$)", re.DOTALL)
_NUMERACION = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def _parsear_omision(texto: str) -> str | None:
    """Interpreta la respuesta de una palabra del juez de omisión."""
    texto = _BLOQUE_PENSAMIENTO.sub("", texto).upper()
    if "MISLEADING" in texto:
        return "enganosa"
    if "COMPLETE" in texto:
        return "completa"
    return None


def _extraer_preguntas(texto: str, n: int) -> list[str]:
    """Extrae las preguntas de la salida del modelo (que puede traer bloques
    de razonamiento <think> y numeración)."""
    texto = _BLOQUE_PENSAMIENTO.sub("", texto)
    preguntas = []
    for linea in texto.splitlines():
        linea = _NUMERACION.sub("", linea).strip()
        # una línea puede traer varias preguntas seguidas
        for parte in re.split(r"(?<=\?)\s+", linea):
            parte = parte.strip()
            if parte.endswith("?") and len(parte) > 10 and parte not in preguntas:
                preguntas.append(parte)
    return preguntas[:n]


def _precargar_cuda() -> None:
    """Precarga las librerías CUDA del venv (paquetes nvidia-*-cu12) para que
    el wheel CUDA de llama.cpp las encuentre sin configurar LD_LIBRARY_PATH."""
    import ctypes
    import glob
    import sys

    for patron in (
        "nvidia/cuda_runtime/lib/libcudart.so.*",
        "nvidia/cublas/lib/libcublas.so.*",
    ):
        for lib in glob.glob(f"{sys.prefix}/lib/python*/site-packages/{patron}"):
            try:
                ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


def ruta_modelo() -> Path | None:
    """Ruta del modelo generador si está disponible."""
    if entorno := os.environ.get("AIDAM_MODELO_PREGUNTAS"):
        ruta = Path(entorno)
        return ruta if ruta.exists() else None
    return _RUTA_DEFECTO if _RUTA_DEFECTO.exists() else None


class GeneradorPreguntas:
    """Cliente del LLM local (MiMo) corriendo en un worker aislado.

    llama.cpp vive en su propio proceso (`aidam.mimo_worker`): si corrompe
    memoria — medido cohabitando con PyTorch — muere el worker, no la
    verificación, y este cliente lo reinicia en la siguiente llamada.
    """

    _TIMEOUT_CARGA = 300  # cargar 4.7 GB puede tardar; en GPU son segundos
    _TIMEOUT_RESPUESTA = 180

    def __init__(self, ruta: Path | None = None, n_gpu_layers: int = -1):
        ruta = ruta or ruta_modelo()
        if ruta is None:
            raise FileNotFoundError(
                "No hay modelo generador de preguntas; descarga MiMo-7B-RL GGUF "
                "a modelos/mimo/ o define AIDAM_MODELO_PREGUNTAS"
            )
        self._ruta = ruta
        self._n_gpu_layers = n_gpu_layers
        self._proceso = None
        self._arrancar()

    def _arrancar(self) -> None:
        import subprocess
        import sys

        self.cerrar()
        entorno = os.environ.copy()
        entorno["AIDAM_MODELO_PREGUNTAS"] = str(self._ruta)
        entorno["AIDAM_MIMO_GPU_LAYERS"] = str(self._n_gpu_layers)
        self._proceso = subprocess.Popen(
            [sys.executable, "-m", "aidam.mimo_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=entorno,
        )
        saludo = self._leer(self._TIMEOUT_CARGA)
        if not saludo or not saludo.get("listo"):
            detalle = (saludo or {}).get("error", "sin respuesta del worker")
            self.cerrar()
            raise RuntimeError(f"el worker de MiMo no arrancó: {detalle}")

    def _leer(self, timeout: float) -> dict | None:
        import json as _json
        import select

        if self._proceso is None or self._proceso.stdout is None:
            return None
        listos, _, _ = select.select([self._proceso.stdout], [], [], timeout)
        if not listos:
            return None
        linea = self._proceso.stdout.readline()
        if not linea:
            return None
        try:
            return _json.loads(linea)
        except ValueError:
            return None

    def cerrar(self) -> None:
        if self._proceso is not None:
            self._proceso.kill()
            self._proceso.wait()
            self._proceso = None

    def completar(self, prompt: str, max_tokens: int, temperature: float,
                  stop: list[str] | None = None) -> str:
        """Completa un prompt crudo en el worker, reiniciándolo si cayó."""
        import json as _json

        pedido = _json.dumps(
            {"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature,
             "stop": stop or []},
            ensure_ascii=False,
        )
        for _intento in range(2):
            try:
                if self._proceso is None or self._proceso.poll() is not None:
                    self._arrancar()
                assert self._proceso is not None and self._proceso.stdin is not None
                self._proceso.stdin.write(pedido + "\n")
                self._proceso.stdin.flush()
                respuesta = self._leer(self._TIMEOUT_RESPUESTA)
                if respuesta is None:  # caído o colgado: reiniciar y reintentar
                    self.cerrar()
                    continue
                return respuesta.get("texto", "")
            except Exception:
                self.cerrar()
        return ""

    def preguntas(self, afirmacion: str, n: int = 3, lang: str = "es") -> list[str]:
        idioma = "español" if lang == "es" else "the claim's language"
        prompt = (
            "You are a fact-checker. For the claim below, write exactly "
            f"{n} short, independent search questions whose answers would "
            "confirm or refute it. Reply ONLY with the questions, one per "
            f"line, in {idioma}. No explanations.\n"
            f"Claim: {afirmacion}"
        )
        texto = self._responder(prompt, max_tokens=160, temperature=0.3)
        return _extraer_preguntas(texto, n)

    def _responder(self, prompt: str, max_tokens: int, temperature: float) -> str:
        # Prefill de pensamiento vacío: MiMo-7B-RL es un modelo de razonamiento
        # y gasta cientos de tokens en <think> antes de responder; para salidas
        # cortas eso es latencia sin valor. El bloque vacío lo fuerza a
        # responder directo (mismo truco que el /no_think de Qwen).
        plantilla = (
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n"
        )
        return self.completar(plantilla, max_tokens, temperature, stop=["<|im_end|>"])

    def juzgar_omision(
        self,
        afirmacion: str,
        sustentos: list[str],
        contexto: list[str],
    ) -> str | None:
        """¿La afirmación, aunque sustentada, engaña por omisión (cherry-picking)?

        Solo se invoca con contexto contrario recuperado: el juicio se basa en
        la evidencia de la mesa, nunca en la memoria paramétrica del modelo
        (principio del proyecto: el conocimiento vive en las fuentes).
        Devuelve "enganosa", "completa" o None (no concluyente).
        """
        if not sustentos or not contexto:
            return None
        lineas_s = "\n".join(f"- {s[:300]}" for s in sustentos[:3])
        lineas_c = "\n".join(f"- {c[:300]}" for c in contexto[:3])
        prompt = (
            "You are a fact-checking judge. The claim below is supported by "
            "evidence, but it may still mislead by omitting essential context "
            "(cherry-picking).\n"
            f"Claim: {afirmacion}\n"
            f"Supporting evidence:\n{lineas_s}\n"
            f"Contrary or contextual evidence:\n{lineas_c}\n"
            "Based ONLY on the evidence above: does the claim give a fair "
            "picture, or does it mislead by omission? Answer with exactly one "
            "word: COMPLETE or MISLEADING."
        )
        return _parsear_omision(self._responder(prompt, max_tokens=12, temperature=0.0))

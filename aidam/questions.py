"""Search-question generator (winning technique from AVeriTeC 2.0).

Instead of searching the literal claim (which returns pages that repeat it),
a reasoning model generates the questions whose answers would confirm or
refute it, and those questions become search queries. The winning systems of
the AVeriTeC 2025 shared task (CTU AIC, HerO 2) use this technique with
open LLMs.

Backend: a quantized open reasoning LLM (GGUF Q4, ~5 GB) via llama.cpp —
o1-mini-level reasoning that runs on a consumer GPU or CPU. It's optional:
without the model installed, the pipeline works as before.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_RUTA_DEFECTO = Path(__file__).resolve().parent.parent / "models" / "mimo" / "MiMo-7B-RL-Q4_K_M.gguf"
_BLOQUE_PENSAMIENTO = re.compile(r"<think>.*?(</think>|$)", re.DOTALL)
_NUMERACION = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def _parsear_omision(texto: str) -> str | None:
    """Interprets the one-word answer of the omission judge."""
    texto = _BLOQUE_PENSAMIENTO.sub("", texto).upper()
    if "MISLEADING" in texto:
        return "enganosa"
    if "COMPLETE" in texto:
        return "completa"
    return None


def _extraer_preguntas(texto: str, n: int) -> list[str]:
    """Extracts the questions from the model output (which may carry <think>
    reasoning blocks and numbering)."""
    texto = _BLOQUE_PENSAMIENTO.sub("", texto)
    preguntas = []
    lineas_limpias = []
    for linea in texto.splitlines():
        # strip numbering and markdown decoration (DeepSeek adds bold)
        linea = _NUMERACION.sub("", linea).strip().strip("*_`\"").strip()
        if linea:
            lineas_limpias.append(linea)
        # one line may carry several questions in a row
        for parte in re.split(r"(?<=\?)\s+", linea):
            parte = parte.strip().strip("*_`\"").strip()
            if parte.endswith("?") and len(parte) > 10 and parte not in preguntas:
                preguntas.append(parte)
    if preguntas:
        return preguntas[:n]
    # Some models (DeepSeek-R1) emit search queries instead of questions:
    # `search "..."`. For our use (they go to a search engine) they work just
    # as well or better — accepted as a second style.
    consultas = []
    for linea in lineas_limpias:
        linea = re.sub(r"^search\s*:?\s*", "", linea, flags=re.IGNORECASE)
        linea = linea.strip().strip("*_`\"").strip()
        if len(linea) > 10 and linea not in consultas:
            consultas.append(linea)
    return consultas[:n]


def _precargar_cuda() -> None:
    """Preloads the venv's CUDA libraries (nvidia-*-cu12 packages) so the
    llama.cpp CUDA wheel finds them without configuring LD_LIBRARY_PATH."""
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
    """Path of the generator model if available."""
    if entorno := os.environ.get("AIDAM_MODELO_PREGUNTAS"):
        ruta = Path(entorno)
        return ruta if ruta.exists() else None
    return _RUTA_DEFECTO if _RUTA_DEFECTO.exists() else None


class GeneradorPreguntas:
    """Client of the local LLM running in an isolated worker.

    llama.cpp lives in its own process (`aidam.llm_worker`): if it corrupts
    memory — measured while cohabiting with PyTorch — the worker dies, not
    the verification, and this client restarts it on the next call.
    """

    _TIMEOUT_CARGA = 300  # loading ~5 GB can take a while; on GPU it's seconds
    _TIMEOUT_RESPUESTA = 180

    def __init__(self, ruta: Path | None = None, n_gpu_layers: int = -1):
        ruta = ruta or ruta_modelo()
        if ruta is None:
            raise FileNotFoundError(
                "No hay modelo generador de preguntas; descarga MiMo-7B-RL GGUF "
                "a models/mimo/ o define AIDAM_MODELO_PREGUNTAS"
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
            [sys.executable, "-m", "aidam.llm_worker"],
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
        """Completes a raw prompt in the worker, restarting it if it died."""
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
                if respuesta is None:  # dead or hung: restart and retry
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
        # Empty-thinking prefill: MiMo-7B-RL is a reasoning model and spends
        # hundreds of tokens in <think> before answering; for short outputs
        # that's latency without value. The empty block forces it to answer
        # directly (same trick as Qwen's /no_think).
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
        """Is the claim, though supported, deceptive by omission (cherry-picking)?

        Only invoked when contrary context was retrieved: the judgement is
        based on the evidence on the table, never on the model's parametric
        memory (project principle: knowledge lives in the sources).
        Returns "enganosa", "completa" or None (inconclusive).
        """
        if not sustentos or not contexto:
            return None
        lineas_s = "\n".join(f"- {s[:300]}" for s in sustentos[:3])
        lineas_c = "\n".join(f"- {c[:300]}" for c in contexto[:3])
        # Prompt calibrated against over-firing (measured on AVeriTeC-500:
        # 109 predicted "conflicting" vs 38 real): the omission must undermine
        # the CENTRAL point; minor disagreement doesn't turn truth into deceit.
        prompt = (
            "You are a strict fact-checking judge. The claim below is supported "
            "by evidence. Most supported claims are simply TRUE; cherry-picking "
            "is rare.\n"
            f"Claim: {afirmacion}\n"
            f"Supporting evidence:\n{lineas_s}\n"
            f"Contrary or contextual evidence:\n{lineas_c}\n"
            "Based ONLY on the evidence above: answer MISLEADING only if the "
            "contrary evidence directly undermines the CENTRAL point of the "
            "claim, making it deceptive as stated. Minor caveats, exceptions "
            "or side details do NOT count. Otherwise answer COMPLETE. "
            "Answer with exactly one word: COMPLETE or MISLEADING."
        )
        return _parsear_omision(self._responder(prompt, max_tokens=12, temperature=0.0))

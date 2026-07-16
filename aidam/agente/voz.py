"""Optional local voice interface (extra `voz`): faster-whisper (STT),
Kokoro ONNX (TTS) and Silero VAD via RealtimeSTT.

Everything heavy is imported lazily: this module must import — and its
capability probes must answer — with only the core dependencies installed.
Audio never leaves the machine: both recognition and synthesis run locally.
"""

from __future__ import annotations

import importlib.util
import os
import threading
from functools import lru_cache
from pathlib import Path

# ───────── capacidades ─────────


def hay_voz() -> bool:
    """True when the speech-to-text backend (faster-whisper) is installed."""
    return importlib.util.find_spec("faster_whisper") is not None


def hay_tts() -> bool:
    """True when the text-to-speech backend (Kokoro ONNX) is installed."""
    return importlib.util.find_spec("kokoro_onnx") is not None


def _hay_escucha() -> bool:
    """True when live microphone capture (RealtimeSTT) is installed."""
    return importlib.util.find_spec("RealtimeSTT") is not None


# ───────── singletons ─────────


def _dispositivo() -> str:
    """Best ctranslate2 device: CUDA when visible, CPU otherwise."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


@lru_cache(maxsize=1)
def _modelo_stt():
    """Loads the faster-whisper model ONCE per process.

    Same pattern as `pipeline._generador_preguntas`: loading per call leaks
    memory until the process dies. `AIDAM_MODELO_VOZ` overrides the model
    name or local path (default: large-v3-turbo, INT8).
    """
    from faster_whisper import WhisperModel

    nombre = os.environ.get("AIDAM_MODELO_VOZ", "large-v3-turbo")
    return WhisperModel(nombre, device=_dispositivo(), compute_type="int8")


@lru_cache(maxsize=1)
def _grabadora(lang: str | None = None):
    """Builds the RealtimeSTT recorder ONCE per process (it owns a whisper
    model plus the Silero VAD; rebuilding per call leaks both)."""
    from RealtimeSTT import AudioToTextRecorder

    nombre = os.environ.get("AIDAM_MODELO_VOZ", "large-v3-turbo")
    return AudioToTextRecorder(model=nombre, language=lang or "", compute_type="int8")


@lru_cache(maxsize=1)
def _modelo_tts():
    """Loads the Kokoro ONNX voice ONCE per process, or None if unavailable.

    The weights are searched in ./models/, the working directory and
    ~/.cache/aidam/. Returning None instead of raising lets `hablar()`
    degrade to a silent no-op — a missing voice must never kill the agent.
    """
    try:
        from kokoro_onnx import Kokoro
    except Exception:
        return None
    bases = (Path.cwd() / "models", Path.cwd(), Path.home() / ".cache" / "aidam")
    for base in bases:
        onnx = base / "kokoro-v1.0.onnx"
        voces = base / "voices-v1.0.bin"
        if onnx.exists() and voces.exists():
            try:
                return Kokoro(str(onnx), str(voces))
            except Exception:
                return None
    return None


# ───────── interfaz ─────────


def transcribir(ruta_audio: str | Path, lang: str | None = None) -> str:
    """Transcribes an audio file locally with faster-whisper.

    `lang` is an ISO code ("es", "en", …); None lets the model detect it.
    """
    if not hay_voz():
        raise RuntimeError(
            "faster-whisper no está instalado: instala el extra de voz con "
            "`pip install aidam[voz]`"
        )
    segmentos, _info = _modelo_stt().transcribe(str(ruta_audio), language=lang)
    return " ".join(s.text.strip() for s in segmentos).strip()


def escuchar_una_vez(timeout: float = 30.0, lang: str | None = None) -> str:
    """Listens once on the default microphone and returns the transcription.

    Capture and voice-activity detection run through RealtimeSTT (bundles
    Silero VAD). If nothing was transcribed within `timeout` seconds,
    returns "".
    """
    if not _hay_escucha():
        raise RuntimeError(
            "RealtimeSTT no está instalado: instala el extra de voz con "
            "`pip install aidam[voz]`"
        )
    grabadora = _grabadora(lang)
    resultado: list[str] = []

    def _capturar() -> None:
        try:
            resultado.append(grabadora.text() or "")
        except Exception:
            resultado.append("")

    # The recorder blocks with no timeout of its own; a daemon thread bounds
    # the wait (repo policy: threads, never asyncio).
    hilo = threading.Thread(target=_capturar, daemon=True)
    hilo.start()
    hilo.join(timeout)
    return resultado[0].strip() if resultado else ""


def hablar(texto: str, voz: str | None = None) -> None:
    """Speaks `texto` aloud with Kokoro; silent no-op when TTS is unavailable.

    Deliberate asymmetry with `transcribir`: a missing OUTPUT capability
    degrades silently (the text was already rendered on screen), while a
    missing INPUT capability fails loudly — there is nothing to fall back
    to when the user expects to be heard.
    """
    if not texto or not hay_tts():
        return
    modelo = _modelo_tts()
    if modelo is None:
        return
    try:
        nombre_voz = voz or os.environ.get("AIDAM_VOZ_TTS", "ef_dora")
        muestras, frecuencia = modelo.create(texto, voice=nombre_voz)
        import sounddevice

        sounddevice.play(muestras, frecuencia)
        sounddevice.wait()
    except Exception:
        return  # a broken audio stack must never take the agent down

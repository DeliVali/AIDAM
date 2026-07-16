"""Optional image understanding (extra `imagen`): local OCR plus C2PA
provenance through the external `c2patool` binary.

OCR backends, in order: RapidOCR (the extra this repo already declares —
ONNX-based like the CPU verifier, light) and PaddleOCR as an alternative if
it happens to be installed. The claim-in-an-image flow: extract the visible
text, decompose it into atomic facts and run the normal verification
pipeline over it. All heavy imports are lazy — the module imports with core
dependencies only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from ..models import Informe

# ───────── capacidades ─────────


def hay_ocr() -> bool:
    """True when some OCR backend (RapidOCR or PaddleOCR) is installed."""
    return (
        importlib.util.find_spec("rapidocr_onnxruntime") is not None
        or importlib.util.find_spec("paddleocr") is not None
    )


@lru_cache(maxsize=1)
def _motor_ocr():
    """Loads the OCR engine ONCE per process (same singleton pattern as
    `pipeline._generador_preguntas`; loading per call leaks memory).

    Returns ("rapid", motor) or ("paddle", motor). `AIDAM_OCR_LANG` picks the
    PaddleOCR language pack (default "es"); RapidOCR is multilingual as-is.
    """
    if importlib.util.find_spec("rapidocr_onnxruntime") is not None:
        from rapidocr_onnxruntime import RapidOCR

        return "rapid", RapidOCR()
    from paddleocr import PaddleOCR

    idioma = os.environ.get("AIDAM_OCR_LANG", "es")
    return "paddle", PaddleOCR(lang=idioma, use_angle_cls=True)


# ───────── interfaz ─────────


def extraer_texto(ruta_imagen: str | Path) -> str:
    """Extracts the visible text of an image, one detected line per line."""
    if not hay_ocr():
        raise RuntimeError(
            "no hay OCR instalado: instala el extra de imagen con "
            "`pip install aidam[imagen]`"
        )
    tipo, motor = _motor_ocr()
    lineas: list[str] = []
    if tipo == "rapid":
        # RapidOCR shape: (list of [caja, texto, confianza], tiempos).
        resultado, _tiempos = motor(str(ruta_imagen))
        for deteccion in resultado or []:
            try:
                texto = str(deteccion[1]).strip()
            except (IndexError, TypeError):
                continue
            if texto:
                lineas.append(texto)
        return "\n".join(lineas)
    resultado = motor.ocr(str(ruta_imagen), cls=True)
    for pagina in resultado or []:
        for deteccion in pagina or []:
            # Classic PaddleOCR shape: [caja, (texto, confianza)].
            try:
                texto = str(deteccion[1][0]).strip()
            except (IndexError, TypeError):
                continue
            if texto:
                lineas.append(texto)
    return "\n".join(lineas)


def extraer_afirmaciones(ruta_imagen: str | Path) -> list[str]:
    """OCRs the image and splits its text into verifiable atomic facts."""
    texto = extraer_texto(ruta_imagen)
    if not texto.strip():
        return []
    from ..decompose import descomponer

    return [hecho.texto for hecho in descomponer(texto)]


def verificar_imagen(ruta_imagen: str | Path, lang: str = "es", **kwargs) -> Informe:
    """Verifies the claim(s) printed in an image end to end.

    Extra keyword arguments are forwarded to `pipeline.verificar`
    (`verificador=`, `progreso=`, …).
    """
    texto = extraer_texto(ruta_imagen)
    if not texto.strip():
        raise ValueError("no se detectó texto en la imagen")
    from ..pipeline import verificar

    return verificar(texto, lang=lang, **kwargs)


def procedencia(ruta_imagen: str | Path) -> dict | None:
    """Reads the image's C2PA provenance manifest via `c2patool`, if any.

    Returns None when c2patool is not on PATH, the tool fails, or the image
    carries no manifest. IMPORTANT: almost no legitimate image carries C2PA
    credentials today, so the ABSENCE of a manifest is NOT evidence of
    manipulation — never interpret None as "fake".
    """
    if shutil.which("c2patool") is None:
        return None
    try:
        proceso = subprocess.run(
            ["c2patool", str(ruta_imagen), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proceso.returncode != 0 or not proceso.stdout.strip():
        return None
    try:
        datos = json.loads(proceso.stdout)
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, dict) else None

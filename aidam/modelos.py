"""First-run model acquisition: makes `pip install` (or the installer) enough.

The repo distributes code; the verifier weights live on HuggingFace
(`DeliVali/aidam-verificador`). On machines without a local model — packaged
installs (PyInstaller has no `models/` next to `__file__`) or fresh CPU
installs — `asegurar_verificador()` downloads the ONNX-mini variant (~300 MB,
int4+int8) once into a user directory and points `AIDAM_MODELOS` at it so
`verify.crear_verificador()` finds it. Torch installs are untouched: that
backend already resolves its own weights.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Callable

REPO_HF = "DeliVali/aidam-verificador"
CARPETA_HF = "onnx-mini"  # subfolder in the HF repo with the quantized export


def _base_modelos() -> Path:
    """Where ONNX models live. Priority: env override > repo checkout >
    per-user dir (the only writable option for frozen/packaged builds)."""
    if entorno := os.environ.get("AIDAM_MODELOS"):
        return Path(entorno).expanduser()
    repo = Path(__file__).resolve().parent.parent / "models"
    if not getattr(sys, "frozen", False) and repo.is_dir():
        return repo
    return Path("~/.aidam/modelos").expanduser()


def _modelo_onnx_presente(base: Path) -> bool:
    return any(
        (base / nombre / "config.json").exists()
        for nombre in ("verificador-onnx", "verificador-onnx-mini")
    )


def asegurar_verificador(progreso: Callable[[str], None] | None = None) -> bool:
    """Guarantees a verifier backend will load; downloads on first run if
    needed. Returns False only when there is no model AND the download failed
    (the caller decides how to surface that).
    """
    avisar = progreso or (lambda _m: None)
    base = _base_modelos()

    if _modelo_onnx_presente(base):
        os.environ.setdefault("AIDAM_MODELOS", str(base))
        return True

    # With torch available (and not forced to ONNX), VerificadorNLI resolves
    # its own weights — nothing to download here.
    forzado = os.environ.get("AIDAM_BACKEND", "").lower()
    if forzado not in ("onnx", "onnx-mini") and importlib.util.find_spec("torch"):
        return True

    destino = base / "verificador-onnx-mini"
    avisar("Descargando el verificador (~300 MB, solo la primera vez)…")
    try:
        from huggingface_hub import snapshot_download

        temporal = base / "_descarga"
        snapshot_download(
            repo_id=REPO_HF,
            allow_patterns=[f"{CARPETA_HF}/*"],
            local_dir=str(temporal),
        )
        origen = temporal / CARPETA_HF
        if not (origen / "config.json").exists():
            raise RuntimeError(f"la descarga no trajo {CARPETA_HF}/config.json")
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            shutil.rmtree(destino)
        # move, not copy: the .onnx pesa ~300 MB
        shutil.move(str(origen), str(destino))
        shutil.rmtree(temporal, ignore_errors=True)
    except Exception as exc:
        avisar(f"No se pudo descargar el modelo: {exc}")
        return False

    os.environ["AIDAM_MODELOS"] = str(base)
    avisar("Verificador descargado y listo.")
    return True

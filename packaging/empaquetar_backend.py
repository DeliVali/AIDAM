"""Builds the self-contained backend binary for the desktop installers.

PyInstaller (onedir) over the ONNX/CPU backend: no PyTorch, no Python needed
on the target machine. The verifier weights are NOT bundled — they download
from HuggingFace on first run (aidam/modelos.py), keeping installers light.

Output lands in escritorio/backend/ — the exact contract escritorio/main.js
expects (resources/backend/aidam[.exe] inside the packaged Electron app).

Run from the repo root, in an env with the runtime deps installed:

    pip install .[verificador-cpu,interfaz,imagen] pyinstaller
    python packaging/empaquetar_backend.py

Works the same on Linux, Windows and macOS (that's what the release CI does).
"""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "escritorio" / "backend"

# Heavy or irrelevant for the CPU backend. Building from a dev venv (where
# torch & friends ARE installed) balloons the binary to 1.2+ GB without these:
# triton alone is 685 MB, pyarrow 146 MB — none of it used at runtime
# (measured 2026-07-16; with the excludes the bundle drops to ~350 MB).
EXCLUIR = [
    "torch", "torchvision", "torchaudio", "triton",
    "llama_cpp", "faster_whisper", "kokoro_onnx", "sounddevice", "RealtimeSTT",
    "crawl4ai", "datasets", "accelerate", "cairosvg",
    "pyarrow", "pandas", "babel", "ml_dtypes", "scipy", "sympy", "networkx",
    "jax", "jaxlib", "numba", "onnx", "optimum", "evaluate",
    "pytest", "IPython", "matplotlib", "tkinter",
]

# uvicorn picks these at runtime via strings; PyInstaller can't see them.
OCULTOS = [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
]


def main() -> int:
    from PyInstaller import __main__ as pyinstaller

    separador = ";" if platform.system() == "Windows" else ":"
    trabajo = RAIZ / "build" / "pyinstaller"

    argumentos = [
        str(RAIZ / "packaging" / "lanzador.py"),
        "--name", "aidam",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--console",  # es un CLI; Electron lo lanza sin ventana propia
        "--distpath", str(trabajo / "dist"),
        "--workpath", str(trabajo / "build"),
        "--specpath", str(trabajo),
        # la UI web viaja dentro, donde RUTA_INTERFAZ la espera
        # (Path(servidor.__file__).parent / "interfaz")
        "--add-data", f"{RAIZ / 'aidam' / 'interfaz'}{separador}aidam/interfaz",
    ]
    for modulo in OCULTOS:
        argumentos += ["--hidden-import", modulo]
    for modulo in EXCLUIR:
        argumentos += ["--exclude-module", modulo]

    print(f"[empaquetar] PyInstaller → {trabajo / 'dist' / 'aidam'}")
    pyinstaller.run(argumentos)

    origen = trabajo / "dist" / "aidam"
    if not origen.is_dir():
        print("[empaquetar] ERROR: PyInstaller no produjo el directorio esperado")
        return 1

    if DESTINO.exists():
        # conserva el README del contrato, limpia el resto
        for hijo in DESTINO.iterdir():
            if hijo.name == "README.md":
                continue
            shutil.rmtree(hijo) if hijo.is_dir() else hijo.unlink()
    DESTINO.mkdir(parents=True, exist_ok=True)
    for hijo in origen.iterdir():
        shutil.move(str(hijo), str(DESTINO / hijo.name))

    ejecutable = DESTINO / ("aidam.exe" if platform.system() == "Windows" else "aidam")
    if not ejecutable.exists():
        print(f"[empaquetar] ERROR: falta el ejecutable {ejecutable}")
        return 1
    print(f"[empaquetar] listo: {ejecutable}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

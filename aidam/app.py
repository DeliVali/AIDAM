"""Native desktop window: `aidam app` (plus its app-menu installer).

Not a browser tab: a real window (pywebview over Qt/GTK) embedding the same
local interface `aidam interfaz` serves — the Ollama/Claude Desktop shape.
The HTTP server runs on a random localhost port in a daemon thread and dies
with the window.

`aidam app --instalar` registers AIDAM in the desktop menu (freedesktop
.desktop entry + icon), so launching it from the applications menu starts
everything: that entry, not this module, is what a packaged release ships.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

RUTA_DESKTOP = Path("~/.local/share/applications/aidam.desktop")
RUTA_ICONO = Path("~/.local/share/icons/hicolor/scalable/apps/aidam.svg")


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar_servidor(url: str, intentos: int = 100) -> bool:
    for _ in range(intentos):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def abrir_ventana(puerto: int = 0) -> None:
    """Serves the interface on localhost and opens it in a native window."""
    import uvicorn
    import webview

    from .servidor import crear_app

    puerto = puerto or _puerto_libre()
    config = uvicorn.Config(
        crear_app(), host="127.0.0.1", port=puerto, log_level="warning"
    )
    servidor = uvicorn.Server(config)
    threading.Thread(target=servidor.run, daemon=True, name="aidam-servidor").start()

    base = f"http://127.0.0.1:{puerto}"
    if not _esperar_servidor(f"{base}/api/capacidades"):
        raise RuntimeError("el servidor interno no arrancó")

    webview.create_window(
        "AIDAM — verificación abierta de información",
        base,
        width=1100,
        height=780,
        min_size=(720, 520),
    )
    webview.start()          # blocks until the window closes
    servidor.should_exit = True


def _contenido_desktop(ejecutable: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=AIDAM\n"
        "Comment=Verificación abierta de información\n"
        f"Exec={ejecutable} app\n"
        "Icon=aidam\n"
        "Terminal=false\n"
        "Categories=Utility;Network;\n"
        "Keywords=fact-checking;verificación;noticias;\n"
    )


def instalar_escritorio() -> Path:
    """Registers AIDAM in the desktop applications menu (freedesktop)."""
    ejecutable = Path(sys.executable).with_name("aidam")
    if not ejecutable.exists():  # e.g. running via `python -m aidam`
        ejecutable = Path(sys.argv[0]).resolve()

    icono_origen = Path(__file__).parent / "interfaz" / "icono.svg"
    ruta_icono = RUTA_ICONO.expanduser()
    ruta_icono.parent.mkdir(parents=True, exist_ok=True)
    ruta_icono.write_text(icono_origen.read_text(encoding="utf-8"), encoding="utf-8")

    ruta = RUTA_DESKTOP.expanduser()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(_contenido_desktop(ejecutable), encoding="utf-8")
    return ruta

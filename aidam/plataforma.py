"""Per-OS data locations, dependency-free.

The «General» workspace is a real folder that always exists: it is created on
first server start (more robust across installers than post-install hooks) in
the platform's per-user data directory — the place each OS designates for an
app's persistent data, NOT temp (temp gets wiped):

    Windows  %APPDATA%\\aidam            (Roaming)
    macOS    ~/Library/Application Support/aidam
    Linux    $XDG_DATA_HOME/aidam  or  ~/.local/share/aidam

`AIDAM_DATOS` overrides everything (tests, portable installs).
"""

from __future__ import annotations

import os
import platform
from pathlib import Path


def directorio_datos() -> Path:
    """The app's per-user data directory for this OS (not created here)."""
    if entorno := os.environ.get("AIDAM_DATOS"):
        return Path(entorno).expanduser()
    sistema = platform.system()
    if sistema == "Windows":
        base = Path(os.environ.get("APPDATA") or "~/AppData/Roaming").expanduser()
    elif sistema == "Darwin":
        base = Path("~/Library/Application Support").expanduser()
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME") or "~/.local/share"
        ).expanduser()
    return base / "aidam"


def carpeta_general() -> Path:
    """The General workspace folder; created on demand so it always exists."""
    carpeta = directorio_datos() / "general"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta

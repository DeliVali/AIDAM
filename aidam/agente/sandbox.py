"""Confined command execution with bubblewrap (Claude Code / Codex CLI pattern).

Every command the agent runs is wrapped in bwrap: the whole filesystem is
mounted read-only, /tmp is a throwaway tmpfs, only the declared write root
is writable, and the network is unshared unless explicitly requested. The
.git directory of the write root is re-mounted read-only on top, so a
confined command can edit the working tree but never rewrite repo history.
`construir_comando_bwrap` is a pure argv builder — auditable and testable
on machines without bubblewrap installed.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_MAX_SALIDA = 50_000  # chars kept per stream before truncation
_MARCA_TRUNCADO = "… [truncado]"


@dataclass
class ResultadoEjecucion:
    """Outcome of a confined command."""

    stdout: str
    stderr: str
    codigo: int
    agotado: bool  # True if the timeout killed the process


# ───────── disponibilidad ─────────


def hay_bwrap() -> bool:
    """Whether bubblewrap is available on this machine."""
    return shutil.which("bwrap") is not None


# ───────── construcción del argv (pura) ─────────


def construir_comando_bwrap(comando: list[str], raiz_escritura: Path,
                            red: bool = False, ro_extra: list[Path] | None = None) -> list[str]:
    """Builds the complete bwrap argv for a confined command.

    Layout: fresh user/pid/ipc/uts namespaces (plus net when `red` is
    False), the whole filesystem read-only, private /dev, /proc and /tmp,
    `raiz_escritura` bound read-write with its .git re-mounted read-only
    when present, HOME and cwd inside the write root, and the command after
    the `--` separator. Extra read-only binds go through `ro_extra`.
    """
    raiz = str(raiz_escritura)
    argv = [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
    ]
    if not red:
        argv.append("--unshare-net")
    argv += [
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--bind", raiz, raiz,
    ]
    git = Path(raiz_escritura) / ".git"
    if git.exists():
        argv += ["--ro-bind", str(git), str(git)]
    for ruta in ro_extra or []:
        argv += ["--ro-bind", str(ruta), str(ruta)]
    argv += ["--setenv", "HOME", raiz, "--chdir", raiz, "--"]
    argv += list(comando)
    return argv


# ───────── ejecución ─────────


def _truncar(texto: str) -> str:
    if len(texto) <= _MAX_SALIDA:
        return texto
    return texto[:_MAX_SALIDA] + _MARCA_TRUNCADO


def _a_texto(salida: bytes | str | None) -> str:
    """TimeoutExpired may carry bytes (or nothing) even in text mode."""
    if salida is None:
        return ""
    if isinstance(salida, bytes):
        return salida.decode("utf-8", errors="replace")
    return salida


def ejecutar_confinado(comando: list[str] | str, raiz_escritura: Path | str,
                       timeout: float = 60.0, red: bool = False) -> ResultadoEjecucion:
    """Runs a command inside the bwrap sandbox and captures its output.

    A string command runs through `bash -lc`. Raises RuntimeError when
    bubblewrap is missing. A timeout does not raise: it returns
    codigo=124 with agotado=True (bwrap's --die-with-parent guarantees
    the sandboxed process dies with it). Both streams are truncated to
    50 000 chars with an explicit marker.
    """
    if not hay_bwrap():
        raise RuntimeError("bubblewrap no está instalado (pacman -S bubblewrap)")
    if isinstance(comando, str):
        comando = ["bash", "-lc", comando]
    argv = construir_comando_bwrap(comando, Path(raiz_escritura), red=red)
    try:
        proceso = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return ResultadoEjecucion(
            stdout=_truncar(_a_texto(exc.stdout)),
            stderr=_truncar(_a_texto(exc.stderr)),
            codigo=124,
            agotado=True,
        )
    return ResultadoEjecucion(
        stdout=_truncar(proceso.stdout),
        stderr=_truncar(proceso.stderr),
        codigo=proceso.returncode,
        agotado=False,
    )

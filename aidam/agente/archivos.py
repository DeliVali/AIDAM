"""Native computer control: file operations from plain conversation.

Jeffrey's requirement (2026-07-16): the agent should manage the user's
files natively — «mueve la carpeta X a Y» typed in the chat — with zero
configuration and maximum friendliness. Pure stdlib (shutil/pathlib), no
external tools, and three factory safety rules that are not options:

1. Everything stays inside the user's HOME (no /etc, no system paths).
2. Nothing is ever truly deleted: «borra/elimina» moves to the
   freedesktop trash (gio trash when available, manual Trash dir
   otherwise) — always recoverable.
3. Every operation is permission-gated by the caller and the prompt
   states EXACTLY what will happen, before it happens.

Parsing is deliberately strict: clear imperatives with clear paths. An
ambiguous order gets a how-to-phrase-it reply instead of a guess — the
same no-silent-guessing contract as the context resolver.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_CASA = Path.home()


@dataclass
class OrdenArchivos:
    accion: str          # mover | copiar | renombrar | crear_carpeta | listar | papelera
    origen: Path | None
    destino: Path | None
    descripcion: str     # human sentence for the permission prompt


_PATRONES = [
    ("mover", re.compile(
        r"^\s*(?:mueve|mover|move)\s+(?:la carpeta |el archivo |the folder |the file )?"
        r"[«\"']?(?P<origen>[^«»\"']+?)[»\"']?\s+(?:a|hacia|to)\s+"
        r"[«\"']?(?P<destino>[^«»\"'?!]+?)[»\"']?[?!\s]*$", re.IGNORECASE)),
    ("copiar", re.compile(
        r"^\s*(?:copia|copiar|copy)\s+(?:la carpeta |el archivo )?"
        r"[«\"']?(?P<origen>[^«»\"']+?)[»\"']?\s+(?:a|en|to)\s+"
        r"[«\"']?(?P<destino>[^«»\"'?!]+?)[»\"']?[?!\s]*$", re.IGNORECASE)),
    ("renombrar", re.compile(
        r"^\s*(?:renombra|renombrar|rename)\s+"
        r"[«\"']?(?P<origen>[^«»\"']+?)[»\"']?\s+(?:a|como|to)\s+"
        r"[«\"']?(?P<destino>[^«»\"'?!]+?)[»\"']?[?!\s]*$", re.IGNORECASE)),
    ("crear_carpeta", re.compile(
        r"^\s*(?:crea|crear|create)\s+(?:una |la )?(?:carpeta|folder|directorio)\s+"
        r"(?:llamada? )?[«\"']?(?P<origen>[^«»\"'?!]+?)[»\"']?[?!\s]*$", re.IGNORECASE)),
    ("listar", re.compile(
        r"^\s*(?:lista|listar|list|muestra|qu[eé] hay en)\s+(?:la carpeta |el contenido de )?"
        r"[«\"']?(?P<origen>[^«»\"'?!]+?)[»\"']?[?!\s]*$", re.IGNORECASE)),
    ("papelera", re.compile(
        r"^\s*(?:borra|borrar|elimina|eliminar|delete)\s+(?:la carpeta |el archivo )?"
        r"[«\"']?(?P<origen>[^«»\"'?!]+?)[»\"']?[?!\s]*$", re.IGNORECASE)),
]

_VERBOS = re.compile(
    r"^\s*(mueve|mover|move|copia|copiar|copy|renombra|renombrar|rename"
    r"|crea|crear|create|lista|listar|muestra|borra|borrar|elimina|eliminar|delete)\b",
    re.IGNORECASE,
)

AYUDA_ORDEN = (
    "Entendí que quieres manejar archivos, pero necesito la orden clara. "
    "Ejemplos: «mueve Descargas/fotos a Documentos», «crea la carpeta proyectos», "
    "«lista Documentos», «borra Descargas/viejo.txt» (va a la papelera, recuperable)."
)


def _resolver_ruta(cruda: str) -> Path | None:
    """User path → absolute path inside HOME, or None if it escapes."""
    limpia = cruda.strip().strip("'\"«»")
    ruta = Path(limpia).expanduser()
    if not ruta.is_absolute():
        ruta = _CASA / ruta
    ruta = ruta.resolve()
    try:
        ruta.relative_to(_CASA)
    except ValueError:
        return None  # outside HOME: refused by design
    return ruta


def interpretar_orden(texto: str) -> OrdenArchivos | str | None:
    """None = not a file order; str = it is, but unclear (help message);
    OrdenArchivos = parsed and ready for the permission gate."""
    if not _VERBOS.match(texto.strip()) or len(texto) > 160:
        return None
    for accion, patron in _PATRONES:
        m = patron.match(texto)
        if not m:
            continue
        origen = _resolver_ruta(m.group("origen"))
        destino = (_resolver_ruta(m.group("destino"))
                   if "destino" in m.groupdict() and m.group("destino") else None)
        if origen is None or ("destino" in m.groupdict() and m.group("destino") and destino is None):
            return ("Solo manejo archivos dentro de tu carpeta personal "
                    f"({_CASA}); esa ruta queda fuera.")
        etiquetas = {
            "mover": f"Mover {origen} → {destino}",
            "copiar": f"Copiar {origen} → {destino}",
            "renombrar": f"Renombrar {origen} → {destino}",
            "crear_carpeta": f"Crear la carpeta {origen}",
            "listar": f"Listar el contenido de {origen}",
            "papelera": f"Enviar {origen} a la papelera (recuperable)",
        }
        return OrdenArchivos(accion=accion, origen=origen, destino=destino,
                             descripcion=etiquetas[accion])
    return AYUDA_ORDEN


def _a_papelera(ruta: Path) -> str:
    """freedesktop trash via gio when present; manual Trash dir otherwise."""
    if shutil.which("gio"):
        subprocess.run(["gio", "trash", str(ruta)], check=True, timeout=30)
        return "papelera del sistema"
    papelera = _CASA / ".local/share/Trash/files"
    papelera.mkdir(parents=True, exist_ok=True)
    destino = papelera / f"{ruta.name}.{datetime.now():%Y%m%d%H%M%S}"
    shutil.move(str(ruta), destino)
    return str(destino)


def ejecutar_orden(orden: OrdenArchivos) -> str:
    """Executes an ALREADY-AUTHORIZED order; returns the human result."""
    o, d = orden.origen, orden.destino
    if orden.accion in ("mover", "copiar", "renombrar") and d is not None:
        if not o.exists():
            return f"No existe: {o}"
        if d.exists() and d.is_dir() and orden.accion != "renombrar":
            d = d / o.name
        if d.exists():
            return f"Ya existe {d}; no sobrescribo. Elige otro nombre."
        d.parent.mkdir(parents=True, exist_ok=True)
        if orden.accion == "copiar":
            if o.is_dir():
                shutil.copytree(o, d)
            else:
                shutil.copy2(o, d)
        else:
            shutil.move(str(o), str(d))
        return f"Hecho: {o.name} → {d}"
    if orden.accion == "crear_carpeta":
        if o.exists():
            return f"Ya existía: {o}"
        o.mkdir(parents=True)
        return f"Carpeta creada: {o}"
    if orden.accion == "listar":
        if not o.is_dir():
            return f"No es una carpeta: {o}"
        entradas = sorted(o.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lineas = [f"{'📁' if p.is_dir() else '📄'} {p.name}" for p in entradas[:40]]
        extra = f"\n… y {len(entradas) - 40} más" if len(entradas) > 40 else ""
        return f"{o} ({len(entradas)} elementos):\n" + "\n".join(lineas) + extra
    if orden.accion == "papelera":
        if not o.exists():
            return f"No existe: {o}"
        donde = _a_papelera(o)
        return f"{o.name} está en la papelera ({donde}) — recuperable."
    return "Orden no reconocida."

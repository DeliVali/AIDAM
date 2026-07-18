"""Permission engine for the AIDAM agent: deny-first rules, four modes.

Design follows the 2026 convergence of CLI agents (Claude Code semantics on
a Codex-style OS-sandbox floor): explicit deny/ask/allow rule arrays evaluated
deny-first, global modes that scale from read-only to unattended, and the
deliberate asymmetry that command grants may persist across sessions while
file-edit grants never do. Agent-level policy is advisory for subprocesses —
real containment is `sandbox.ejecutar_confinado` (bubblewrap); this module
decides *whether* to run, the sandbox decides *what it can touch*.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ModoPermisos(str, Enum):
    PLAN = "plan"                            # read-only: writes/commands always denied
    PREGUNTAR = "preguntar"                  # default: reads free, everything else asks
    ACEPTAR_EDICIONES = "aceptar_ediciones"  # writes inside the workspace auto-approved
    LOTE = "lote"                            # unattended: anything not allowed by rule is denied


class Decision(str, Enum):
    PERMITIR = "permitir"
    DENEGAR = "denegar"
    PREGUNTAR = "preguntar"


@dataclass
class ResultadoPermiso:
    decision: Decision
    motivo: str


_HERRAMIENTAS = ("Leer", "Escribir", "Ejecutar")
_ORDEN_TIPOS = ("denegar", "preguntar", "permitir")  # deny-first, first match wins
_REGLA = re.compile(r"(\w+)\((.*)\)\s*\Z", re.DOTALL)

# Circuit breaker, never configurable (normalized whitespace, both flag orders).
_DENEGACIONES_INTEGRADAS = frozenset(
    f"rm {flags} {objetivo}"
    for flags in ("-rf", "-fr", "-r -f", "-f -r")
    for objetivo in ("/", "~", "$HOME", str(Path.home()))
)

_REGLAS_DEFECTO = {
    "permitir": [
        "Ejecutar(git status)",
        "Ejecutar(git diff *)",
        "Ejecutar(git log *)",
        "Ejecutar(ls *)",
        "Ejecutar(ls)",
    ],
}


# ───────── parsing y patrones ─────────

def _parsear_regla(regla: str) -> tuple[str, str]:
    """"Ejecutar(git status)" -> ("Ejecutar", "git status"). Raises on malformed rules."""
    coincide = _REGLA.match(regla.strip())
    if not coincide or coincide.group(1) not in _HERRAMIENTAS:
        raise ValueError(f"regla de permiso inválida: «{regla}»")
    return coincide.group(1), coincide.group(2).strip()


def _glob_a_regex(glob: str) -> re.Pattern[str]:
    """Path glob → regex: `**` crosses directories, `*`/`?` stay within one."""
    partes: list[str] = []
    i = 0
    while i < len(glob):
        if glob.startswith("**", i):
            partes.append(".*")
            i += 2
        elif glob[i] == "*":
            partes.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            partes.append("[^/]")
            i += 1
        else:
            partes.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(partes) + r"\Z")


def _normalizar_comando(comando: str) -> str:
    return " ".join(comando.split())


def _dividir_comando(comando: str) -> list[str]:
    """Splits a compound command on &&, ||, ;, |, & outside quotes.

    Conservative on purpose: an unbalanced quote means we can't reason about
    the pieces, so the whole command is treated as one opaque unit (it will
    only auto-approve if a rule matches it verbatim).
    """
    trozos: list[str] = []
    actual: list[str] = []
    comilla: str | None = None
    i = 0
    while i < len(comando):
        c = comando[i]
        if comilla:
            actual.append(c)
            if c == comilla:
                comilla = None
            i += 1
        elif c in "'\"":
            comilla = c
            actual.append(c)
            i += 1
        elif comando.startswith(("&&", "||"), i):
            trozos.append("".join(actual))
            actual = []
            i += 2
        elif c in ";|&":
            trozos.append("".join(actual))
            actual = []
            i += 1
        else:
            actual.append(c)
            i += 1
    if comilla is not None:
        return [_normalizar_comando(comando)]
    trozos.append("".join(actual))
    return [t for t in (_normalizar_comando(t) for t in trozos) if t]


def _casa_comando(patron: str, comando: str) -> bool:
    """Prefix glob: `git commit *` matches `git commit -m x`; bare patterns match exactly."""
    patron = _normalizar_comando(patron)
    comando = _normalizar_comando(comando)
    if patron == "*":
        return True
    if patron.endswith(" *"):
        prefijo = patron[:-2]
        return comando == prefijo or comando.startswith(prefijo + " ")
    return comando == patron


def _resolver_patron_ruta(patron: str, raiz: Path) -> str:
    if patron.startswith("//"):
        return patron[1:]
    if patron.startswith("~/"):
        return str(Path.home() / patron[2:])
    if patron.startswith("./"):
        return str(raiz / patron[2:])
    return str(raiz / patron)


def _casa_ruta(patron: str, ruta: str, raiz: Path) -> bool:
    return _glob_a_regex(_resolver_patron_ruta(patron, raiz)).match(ruta) is not None


# ───────── motor ─────────

class MotorPermisos:
    """Deny-first rule evaluation over Leer/Escribir/Ejecutar, plus mode defaults."""

    def __init__(
        self,
        modo: ModoPermisos | str = ModoPermisos.PREGUNTAR,
        reglas: dict | None = None,
        raiz: Path | None = None,
    ) -> None:
        self.modo = ModoPermisos(modo)
        self.raiz = (raiz or Path.cwd()).resolve()
        self.reglas: dict[str, list[str]] = {tipo: [] for tipo in _ORDEN_TIPOS}
        for tipo, lista in (reglas or {}).items():
            if tipo not in _ORDEN_TIPOS:
                raise ValueError(f"tipo de regla desconocido: «{tipo}»")
            for regla in lista:
                _parsear_regla(regla)  # validate eagerly: a typo must not fail open at use time
                self.reglas[tipo].append(regla)
        self._persistentes: list[str] = []

    # ── evaluación ──

    def evaluar(self, herramienta: str, argumento: str) -> ResultadoPermiso:
        if herramienta in ("Consultar", "Buscar"):
            # Read-only consultations (resident NLI, web search) — the task
            # reasoner's consultant pattern. Allowed in every acting mode so
            # checking facts is never friction; denied only in plan (dry-run).
            if self.modo is ModoPermisos.PLAN:
                return ResultadoPermiso(Decision.DENEGAR, f"modo:{self.modo.value}")
            return ResultadoPermiso(Decision.PERMITIR, "consulta de solo lectura")
        if herramienta not in _HERRAMIENTAS:
            return ResultadoPermiso(Decision.DENEGAR, f"herramienta desconocida: {herramienta}")
        if herramienta == "Ejecutar":
            return self._evaluar_comando(argumento)
        return self._evaluar_ruta(herramienta, argumento)

    def _evaluar_comando(self, comando: str) -> ResultadoPermiso:
        subcomandos = _dividir_comando(comando)
        for sub in subcomandos:
            if sub in _DENEGACIONES_INTEGRADAS:
                return ResultadoPermiso(Decision.DENEGAR, f"integrada:{sub}")
        for tipo, decision in (("denegar", Decision.DENEGAR), ("preguntar", Decision.PREGUNTAR)):
            for regla in self.reglas[tipo]:
                nombre, patron = _parsear_regla(regla)
                if nombre != "Ejecutar":
                    continue
                for sub in subcomandos:
                    if _casa_comando(patron, sub):
                        return ResultadoPermiso(decision, f"regla:{regla}")
        permitidos = []
        for sub in subcomandos:
            regla_ok = self._regla_permitir_comando(sub)
            if regla_ok is None:
                break
            permitidos.append(regla_ok)
        else:
            return ResultadoPermiso(Decision.PERMITIR, f"regla:{permitidos[0]}")
        return self._defecto("Ejecutar", comando)

    def _regla_permitir_comando(self, sub: str) -> str | None:
        for regla in self.reglas["permitir"]:
            nombre, patron = _parsear_regla(regla)
            if nombre == "Ejecutar" and _casa_comando(patron, sub):
                return regla
        return None

    def _evaluar_ruta(self, herramienta: str, argumento: str) -> ResultadoPermiso:
        # Symlinks are evaluated by their target: policy applies to what would
        # actually be touched, not to the name used to reach it.
        ruta = str(Path(argumento).expanduser().resolve())
        if (
            self.modo is ModoPermisos.LOTE
            and herramienta == "Escribir"
            and not ruta.startswith(str(self.raiz) + os.sep)
            and ruta != str(self.raiz)
        ):
            return ResultadoPermiso(Decision.DENEGAR, "integrada:escritura fuera de raiz en lote")
        for tipo, decision in (
            ("denegar", Decision.DENEGAR),
            ("preguntar", Decision.PREGUNTAR),
            ("permitir", Decision.PERMITIR),
        ):
            for regla in self.reglas[tipo]:
                nombre, patron = _parsear_regla(regla)
                if nombre == herramienta and _casa_ruta(patron, ruta, self.raiz):
                    return ResultadoPermiso(decision, f"regla:{regla}")
        return self._defecto(herramienta, ruta)

    def _defecto(self, herramienta: str, argumento: str) -> ResultadoPermiso:
        motivo = f"modo:{self.modo.value}"
        if herramienta == "Leer":
            return ResultadoPermiso(Decision.PERMITIR, motivo)
        if self.modo is ModoPermisos.PLAN:
            return ResultadoPermiso(Decision.DENEGAR, motivo)
        if self.modo is ModoPermisos.LOTE:
            return ResultadoPermiso(Decision.DENEGAR, motivo)
        if self.modo is ModoPermisos.ACEPTAR_EDICIONES and herramienta == "Escribir":
            dentro = argumento.startswith(str(self.raiz) + os.sep) or argumento == str(self.raiz)
            if dentro:
                return ResultadoPermiso(Decision.PERMITIR, motivo)
        return ResultadoPermiso(Decision.PREGUNTAR, motivo)

    # ── concesiones ──

    def conceder(self, herramienta: str, patron: str, persistente: bool = False) -> None:
        """Grants an allow rule. Deliberate asymmetry (mirrors Claude Code):

        command grants may persist across sessions; file-edit grants are
        session-only — writes are the higher-risk surface.
        """
        if herramienta not in _HERRAMIENTAS:
            raise ValueError(f"herramienta desconocida: {herramienta}")
        if persistente and herramienta != "Ejecutar":
            raise ValueError("solo las reglas de Ejecutar pueden ser persistentes")
        regla = f"{herramienta}({patron})"
        _parsear_regla(regla)
        self.reglas["permitir"].append(regla)
        if persistente:
            self._persistentes.append(regla)

    def guardar(self, ruta: Path | None = None) -> None:
        """Persists the file-backed rules (loaded ones + persistent grants)."""
        destino = ruta or _ruta_permisos()
        destino.parent.mkdir(parents=True, exist_ok=True)
        actuales: dict[str, list[str]] = {}
        if destino.exists():
            actuales = json.loads(destino.read_text(encoding="utf-8"))
        permitidas = list(dict.fromkeys((actuales.get("permitir") or []) + self._persistentes))
        actuales["permitir"] = permitidas
        destino.write_text(
            json.dumps(actuales, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


# ───────── carga ─────────

def _ruta_permisos() -> Path:
    entorno = os.environ.get("AIDAM_PERMISOS")
    if entorno:
        return Path(entorno).expanduser()
    return Path.home() / ".config" / "aidam" / "permisos.json"


def cargar_motor(
    modo: ModoPermisos | str = ModoPermisos.PREGUNTAR,
    ruta: Path | None = None,
    raiz: Path | None = None,
) -> MotorPermisos:
    """Builds the engine from the rules file (env AIDAM_PERMISOS or
    ~/.config/aidam/permisos.json); falls back to safe defaults if absent."""
    origen = ruta or _ruta_permisos()
    if origen.exists():
        try:
            reglas = json.loads(origen.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise RuntimeError(f"archivo de permisos inválido ({origen}): {error}") from error
    else:
        reglas = dict(_REGLAS_DEFECTO)
    return MotorPermisos(modo=modo, reglas=reglas, raiz=raiz)

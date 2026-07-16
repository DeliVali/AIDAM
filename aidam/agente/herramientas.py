"""Agent tools: permission-gated, audited, sandboxed.

Every tool returns a plain string for the agent history (structured handback,
never raw context). Failures come back as "error: …" strings instead of
exceptions so one bad call never kills the loop.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .auditoria import hash_contenido
from .permisos import Decision

_MAX_LECTURA = 20_000


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict
    funcion: Callable[..., str]


def crear_herramientas(
    permisos,
    auditoria,
    raiz: Path,
    confirmar: Callable[[str], bool] | None = None,
    progreso: Callable[[str], None] | None = None,
) -> dict[str, Herramienta]:
    """Builds the tool registry bound to one permission engine + audit log."""
    raiz = Path(raiz).resolve()
    preguntar = confirmar or (lambda _texto: False)  # unattended default: unconfirmed = refused
    avisar = progreso or (lambda _mensaje: None)

    def _resolver(herramienta: str, argumento: str) -> tuple[bool, str]:
        """Permission gate shared by all tools; returns (allowed, motive)."""
        resultado = permisos.evaluar(herramienta, argumento)
        decision, motivo = resultado.decision, resultado.motivo
        aprobado_por = motivo
        if decision is Decision.PREGUNTAR:
            if preguntar(f"{herramienta}: {argumento}"):
                decision, aprobado_por = Decision.PERMITIR, "usuario"
            else:
                decision, aprobado_por = Decision.DENEGAR, "usuario"
        auditoria.registrar(
            herramienta, argumento, decision.value, permisos.modo.value, aprobado_por
        )
        return decision is Decision.PERMITIR, aprobado_por

    # ── herramientas ──

    def leer_archivo(ruta: str) -> str:
        permitido, _ = _resolver("Leer", ruta)
        if not permitido:
            return f"error: lectura denegada: {ruta}"
        try:
            texto = Path(ruta).expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            return f"error: {error}"
        if len(texto) > _MAX_LECTURA:
            return texto[:_MAX_LECTURA] + "\n… [truncado]"
        return texto

    def escribir_archivo(ruta: str, contenido: str) -> str:
        destino = Path(ruta).expanduser()
        resultado = permisos.evaluar("Escribir", str(destino))
        decision, aprobado_por = resultado.decision, resultado.motivo
        if decision is Decision.PREGUNTAR:
            actual = ""
            if destino.exists():
                try:
                    actual = destino.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    actual = ""
            diff = "\n".join(
                difflib.unified_diff(
                    actual.splitlines(), contenido.splitlines(),
                    fromfile=f"a/{destino.name}", tofile=f"b/{destino.name}", lineterm="",
                )
            )
            if preguntar(f"Escribir {destino}\n{diff}"):
                decision, aprobado_por = Decision.PERMITIR, "usuario"
            else:
                decision, aprobado_por = Decision.DENEGAR, "usuario"
        auditoria.registrar(
            "Escribir", str(destino), decision.value, permisos.modo.value, aprobado_por,
            exito=decision is Decision.PERMITIR, hash_resultado=hash_contenido(contenido),
        )
        if decision is not Decision.PERMITIR:
            return f"error: escritura denegada: {destino}"
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(contenido, encoding="utf-8")
        except OSError as error:
            return f"error: {error}"
        return f"escrito: {destino} ({len(contenido)} caracteres)"

    def ejecutar_comando(comando: str) -> str:
        permitido, _ = _resolver("Ejecutar", comando)
        if not permitido:
            return f"error: comando denegado: {comando}"
        from .sandbox import ejecutar_confinado

        avisar(f"ejecutando en sandbox: {comando}")
        try:
            resultado = ejecutar_confinado(comando, raiz)
        except RuntimeError as error:
            return f"error: {error}"
        estado = "agotado (timeout)" if resultado.agotado else f"código {resultado.codigo}"
        return f"{estado}\n{resultado.stdout}\n{resultado.stderr}".strip()

    def verificar_afirmacion(afirmacion: str, lang: str = "es") -> str:
        from ..models import informe_a_dict
        from ..pipeline import verificar

        informe = verificar(afirmacion, lang=lang, progreso=avisar)
        return _compactar(informe_a_dict(informe))

    def investigar_afirmacion(afirmacion: str, nivel: int | None = None, lang: str = "es") -> str:
        from ..models import informe_a_dict
        from .orquestador import investigar

        resultado = investigar(afirmacion, nivel=nivel, lang=lang, progreso=avisar)
        salida = _compactar(informe_a_dict(resultado.informe))
        return (
            f"{salida}\nnivel: {resultado.nivel} · ángulos: {len(resultado.angulos)}"
            f" · desacuerdo: {resultado.senales.desacuerdo}"
        )

    return {
        "leer_archivo": Herramienta(
            "leer_archivo", "lee un archivo de texto", {"ruta": "str"}, leer_archivo
        ),
        "escribir_archivo": Herramienta(
            "escribir_archivo", "escribe un archivo (con diff y permiso)",
            {"ruta": "str", "contenido": "str"}, escribir_archivo,
        ),
        "ejecutar_comando": Herramienta(
            "ejecutar_comando", "ejecuta un comando en el sandbox (bubblewrap, sin red)",
            {"comando": "str"}, ejecutar_comando,
        ),
        "verificar_afirmacion": Herramienta(
            "verificar_afirmacion", "verifica una afirmación con el pipeline completo",
            {"afirmacion": "str", "lang": "str"}, verificar_afirmacion,
        ),
        "investigar_afirmacion": Herramienta(
            "investigar_afirmacion", "verificación en cascada con escalado por señales",
            {"afirmacion": "str", "nivel": "int|None", "lang": "str"}, investigar_afirmacion,
        ),
    }


def ejecutar_herramienta(
    herramientas: dict[str, Herramienta], nombre: str, argumentos: dict
) -> str:
    """Dispatch with error containment: unknown tool / bad args → 'error: …'."""
    herramienta = herramientas.get(nombre)
    if herramienta is None:
        return f"error: herramienta desconocida: {nombre}"
    try:
        return herramienta.funcion(**argumentos)
    except TypeError as error:
        return f"error: argumentos inválidos para {nombre}: {error}"
    except Exception as error:  # one bad call must never kill the loop
        return f"error: {nombre} falló: {error}"


def _compactar(informe_dict: dict, max_citas: int = 3) -> str:
    """Compact JSON-ish rendering: verdicts plus at most N citations per fact."""
    import json as _json

    for hecho in informe_dict.get("hechos", []):
        for lado in ("a_favor", "en_contra"):
            hecho[lado] = [
                {
                    "etiqueta": par.get("etiqueta"),
                    "prob": par.get("prob"),
                    "url": (par.get("evidencia") or {}).get("url"),
                    "dominio": (par.get("evidencia") or {}).get("dominio"),
                }
                for par in (hecho.get(lado) or [])[:max_citas]
            ]
    return _json.dumps(informe_dict, ensure_ascii=False)

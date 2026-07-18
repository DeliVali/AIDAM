"""Interactive agent REPL: one while loop, flat history, permission-gated tools.

The loop is deliberately code-driven (the pipeline decides, not an LLM
planner): free text is a claim to investigate, slash commands do the rest.
Voice, when available, is an input/output convenience that never touches the
verdict path.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .auditoria import RegistroAuditoria
from .permisos import ModoPermisos, cargar_motor

_AYUDA = """\
Comandos:
  /verificar <texto>              verificación estándar (pipeline completo)
  /investigar [--nivel N] <texto> verificación en cascada (escala por señales)
  /leer <ruta>                    leer un archivo (con permisos)
  /escribir <ruta>                escribir un archivo (pide el contenido, con diff)
  /ejecutar <comando>             ejecutar en el sandbox (bubblewrap, sin red)
  /tarea <descripción>            modo tarea (ReAct): el razonador actúa con herramientas
  /fuentes                        listar fuentes de evidencia
  /permisos                       reglas de permisos vigentes
  /modo [nuevo]                   ver o cambiar el modo de permisos
  /ayuda                          esta ayuda
  /salir                          terminar
Texto libre = afirmación a investigar (nivel automático)."""


def _parsear_comando(linea: str) -> tuple[str, str]:
    """"/investigar --nivel 2 x" -> ("investigar", "--nivel 2 x"); free text -> ("", linea)."""
    linea = linea.strip()
    if not linea.startswith("/"):
        return "", linea
    partes = linea[1:].split(None, 1)
    if not partes:
        return "", ""
    return partes[0].casefold(), partes[1].strip() if len(partes) > 1 else ""


def _extraer_nivel(resto: str) -> tuple[int | None, str]:
    """"--nivel 2 texto" -> (2, "texto"); no flag -> (None, resto)."""
    trozos = resto.split()
    if len(trozos) >= 2 and trozos[0] == "--nivel" and trozos[1] in ("0", "1", "2"):
        return int(trozos[1]), " ".join(trozos[2:])
    return None, resto


def bucle_agente(
    modo: ModoPermisos | str = ModoPermisos.PREGUNTAR,
    lang: str = "es",
    voz: bool = False,
    nivel: int | None = None,
    preguntas: bool = False,
) -> int:
    from rich.console import Console
    from rich.panel import Panel

    consola = Console()
    motor = cargar_motor(modo)
    auditoria = RegistroAuditoria()
    avisar = lambda m: print(f"[aidam] {m}", file=sys.stderr)  # noqa: E731

    hablar = lambda _texto: None  # noqa: E731
    escuchar = None
    if voz:
        from . import voz as modulo_voz

        if modulo_voz.hay_voz():
            escuchar = modulo_voz.escuchar_una_vez
            if modulo_voz.hay_tts():
                hablar = modulo_voz.hablar
            avisar("voz activa: Enter en vacío para hablar")
        else:
            avisar("voz no disponible (instala aidam[voz]); sigo en texto")

    def confirmar(texto: str) -> bool:
        consola.print(Panel(texto[:2000], title="Aprobación requerida", border_style="yellow"))
        respuesta = input("¿Aprobar? [s/N/siempre] ").strip().casefold()
        if respuesta == "siempre":
            _conceder_siempre(motor, texto)
            return True
        return respuesta in ("s", "si", "sí", "y", "yes")

    from .herramientas import crear_herramientas

    herramientas = crear_herramientas(
        motor, auditoria, Path.cwd(), confirmar=confirmar, progreso=avisar
    )

    consola.print(
        Panel(
            f"AIDAM agente · modo [bold]{motor.modo.value}[/bold] · "
            f"escribe /ayuda para los comandos",
            border_style="cyan",
        )
    )

    verificador = None  # loaded once, reused across turns
    while True:
        try:
            linea = input("aidam> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not linea.strip() and escuchar is not None:
            try:
                linea = escuchar()
                consola.print(f"[dim]oído:[/dim] {linea}")
            except Exception as error:
                avisar(f"voz falló: {error}")
                continue
        if not linea.strip():
            continue

        comando, resto = _parsear_comando(linea)
        try:
            if comando in ("salir", "exit", "quit"):
                return 0
            if comando == "ayuda":
                consola.print(_AYUDA, markup=False)  # [nuevo] is help text, not a rich tag
            elif comando == "modo":
                if resto:
                    motor.modo = ModoPermisos(resto.replace("-", "_"))
                consola.print(f"modo: {motor.modo.value}")
            elif comando == "permisos":
                consola.print(f"modo: {motor.modo.value}")
                for tipo in ("denegar", "preguntar", "permitir"):
                    for regla in motor.reglas.get(tipo, []):
                        consola.print(f"  {tipo:10s} {regla}")
            elif comando == "fuentes":
                from ..retrieve import FUENTES

                for nombre, (descripcion, _categorias, _funcion) in FUENTES.items():
                    consola.print(f"{nombre:22s} {descripcion}")
            elif comando == "leer":
                consola.print(herramientas["leer_archivo"].funcion(resto))
            elif comando == "escribir":
                consola.print("contenido (termina con una línea sola con «.»):")
                lineas = []
                while (fila := input()) != ".":
                    lineas.append(fila)
                consola.print(
                    herramientas["escribir_archivo"].funcion(resto, "\n".join(lineas) + "\n")
                )
            elif comando == "ejecutar":
                consola.print(herramientas["ejecutar_comando"].funcion(resto))
            elif comando == "tarea":
                if not resto:
                    consola.print("[dim]uso: /tarea <descripción>[/dim]")
                    continue
                from ..pipeline import _generador_preguntas
                from .razonador import ejecutar_tarea

                generador = _generador_preguntas()
                if generador is None:
                    avisar("el modo tarea requiere el modelo razonador local")
                    continue
                if verificador is None:
                    avisar("Cargando el núcleo verificador…")
                    from ..verify import crear_verificador

                    verificador = crear_verificador()
                resultado_tarea = ejecutar_tarea(
                    resto, herramientas, generador, auditoria,
                    verificador=verificador, lang=lang, progreso=avisar,
                )
                from rich.text import Text

                consola.print(Panel(
                    Text(resultado_tarea.respuesta),  # not rich markup
                    title=f"Tarea · {len(resultado_tarea.pasos)} paso(s)",
                    border_style="cyan" if resultado_tarea.terminado_por == "respuesta" else "yellow",
                ))
                hablar(resultado_tarea.respuesta[:200])
            elif comando in ("verificar", "investigar", ""):
                texto = resto
                nivel_pedido = nivel
                if comando == "investigar":
                    nivel_pedido, texto = _extraer_nivel(resto)
                    if nivel_pedido is None:
                        nivel_pedido = nivel
                if not texto:
                    consola.print("[dim]nada que verificar[/dim]")
                    continue
                if verificador is None:
                    avisar("Cargando el núcleo verificador…")
                    from ..verify import crear_verificador

                    verificador = crear_verificador()
                from ..cli import _imprimir

                if comando == "verificar":
                    from ..pipeline import verificar

                    informe = verificar(
                        texto, lang=lang, preguntas=preguntas,
                        verificador=verificador, progreso=avisar,
                    )
                    resultado_sintesis = None
                else:
                    from .orquestador import investigar

                    resultado = investigar(
                        texto, nivel=nivel_pedido, lang=lang, preguntas=preguntas,
                        verificador=verificador, progreso=avisar,
                        sintetizar_final=preguntas,
                    )
                    informe = resultado.informe
                    resultado_sintesis = resultado.sintesis
                    avisar(
                        f"nivel {resultado.nivel} · ángulos {len(resultado.angulos)}"
                        f" · desacuerdo {resultado.senales.desacuerdo}"
                    )
                _imprimir(informe)
                if resultado_sintesis:
                    consola.print(Panel(resultado_sintesis, title="Síntesis (LLM, no juez)"))
                hablar(f"{informe.veredicto.value}, confianza {informe.confianza:.0%}")
            else:
                consola.print(f"[dim]comando desconocido: /{comando} — /ayuda[/dim]")
        except Exception as error:  # one bad turn must never kill the REPL
            consola.print(f"[red]error:[/red] {error}")
    return 0


def _conceder_siempre(motor, texto: str) -> None:
    """"siempre" on an approval panel becomes a session grant on the engine."""
    primera = texto.splitlines()[0] if texto else ""
    if primera.startswith("Ejecutar: "):
        motor.conceder("Ejecutar", primera.removeprefix("Ejecutar: ") + " *")
    elif primera.startswith("Escribir "):
        motor.conceder("Escribir", primera.removeprefix("Escribir ").strip())

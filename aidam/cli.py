"""AIDAM CLI: `aidam verificar "claim"`."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .models import Informe, Veredicto, informe_a_dict

_ESTILO = {
    Veredicto.SUSTENTADO: ("green", "✓ SUSTENTADO"),
    Veredicto.REFUTADO: ("red", "✗ REFUTADO"),
    Veredicto.CONTRADICTORIO: ("yellow", "⚡ EVIDENCIA CONTRADICTORIA"),
    Veredicto.INSUFICIENTE: ("bright_black", "? EVIDENCIA INSUFICIENTE"),
}


def _imprimir(informe: Informe) -> None:
    from rich.console import Console
    from rich.panel import Panel

    consola = Console()
    if informe.tipo in ("pregunta", "aclaracion"):
        consola.print(Panel(
            f"[bold]{informe.afirmacion}[/bold]\n\n{informe.respuesta}",
            title="AIDAM · Respuesta", border_style="cyan",
        ))
        return
    color, titulo = _ESTILO[informe.veredicto]
    respuesta = f"\n\n{informe.respuesta}" if informe.respuesta else ""
    consola.print(
        Panel(
            f"[bold]{informe.afirmacion}[/bold]\n\n"
            f"[{color} bold]{titulo}[/] · confianza {informe.confianza:.0%}{respuesta}",
            title="AIDAM",
            border_style=color,
        )
    )
    for vh in informe.hechos:
        color_h, titulo_h = _ESTILO[vh.veredicto]
        consola.print(f"\n[bold]Hecho:[/bold] {vh.hecho.texto}")
        consola.print(f"  [{color_h}]{titulo_h}[/] · confianza {vh.confianza:.0%}")
        for etiqueta, pares in (("A favor", vh.a_favor), ("En contra", vh.en_contra)):
            for par in pares[:3]:
                idioma = f" · {par.evidencia.idioma}" if par.evidencia.idioma else ""
                consola.print(
                    f"  [{color_h}]•[/] {etiqueta} ({par.prob:.0%}) "
                    f"[dim]{par.evidencia.dominio}{idioma}[/dim]\n"
                    f"    «{par.evidencia.texto[:200]}…»\n"
                    f"    [dim underline]{par.evidencia.url}[/dim underline]"
                )
        if not vh.a_favor and not vh.en_contra:
            consola.print("  [dim]Sin evidencia concluyente en las fuentes consultadas.[/dim]")


def _a_json(informe: Informe) -> str:
    return json.dumps(informe_a_dict(informe), ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aidam",
        description="Agente de lógica comparativa: verificación multi-fuente.",
    )
    parser.add_argument("--version", action="version", version=f"aidam {__version__}")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_verificar = sub.add_parser("verificar", help="verificar una afirmación")
    p_verificar.add_argument("afirmacion", help="texto de la afirmación a verificar")
    p_verificar.add_argument("--lang", default="es", help="idioma de la afirmación (es, en, …)")
    p_verificar.add_argument(
        "--max-idiomas",
        type=int,
        default=5,
        help="Wikipedias adicionales a consultar vía enlaces interlingüísticos "
        "(0 = solo el idioma de la afirmación; un valor alto consulta todas las que existan)",
    )
    p_verificar.add_argument(
        "--preguntas",
        action="store_true",
        help="generar preguntas de búsqueda con un LLM local (MiMo) para dirigir "
        "la recuperación — técnica ganadora de AVeriTeC 2.0; requiere el modelo "
        "en models/mimo/",
    )
    p_verificar.add_argument("--json", action="store_true", help="salida en JSON")
    p_verificar.add_argument(
        "--sin-memoria",
        action="store_true",
        help="no guardar esta verificación ni consultar el historial "
        "(la memoria vive en ~/.aidam/memoria.db o $AIDAM_MEMORIA)",
    )

    sub.add_parser("fuentes", help="listar las fuentes de evidencia registradas")

    p_historial = sub.add_parser(
        "historial", help="últimas verificaciones guardadas en la memoria del agente"
    )
    p_historial.add_argument("--limite", type=int, default=20)

    p_recordar = sub.add_parser(
        "recordar",
        help="buscar por significado en la evidencia recordada "
        "(vectores calculados una sola vez, sin re-procesar texto)",
    )
    p_recordar.add_argument("consulta", help="qué buscar en la evidencia guardada")
    p_recordar.add_argument("--limite", type=int, default=5)

    p_investigar = sub.add_parser(
        "investigar",
        help="verificación en cascada: escala la investigación según señales medidas",
    )
    p_investigar.add_argument("afirmacion", help="texto de la afirmación a investigar")
    p_investigar.add_argument("--lang", default="es", help="idioma de la afirmación (es, en, …)")
    p_investigar.add_argument(
        "--max-idiomas",
        type=int,
        default=5,
        help="Wikipedias adicionales a consultar vía enlaces interlingüísticos",
    )
    p_investigar.add_argument(
        "--nivel",
        type=int,
        choices=(0, 1, 2),
        default=None,
        help="forzar el nivel de investigación (por defecto: automático por señales medidas)",
    )
    p_investigar.add_argument(
        "--preguntas",
        action="store_true",
        help="usar el LLM local para reformular consultas en los ángulos de escalado",
    )
    p_investigar.add_argument(
        "--sintesis",
        action="store_true",
        help="redactar una síntesis con el LLM local — nunca cambia el veredicto; "
        "requiere --preguntas (usa el mismo modelo)",
    )
    p_investigar.add_argument("--json", action="store_true", help="salida en JSON")
    p_investigar.add_argument(
        "--sin-memoria",
        action="store_true",
        help="no usar la evidencia recordada como fuente del nivel 0",
    )

    p_agente = sub.add_parser(
        "agente", help="REPL interactivo del agente (permisos, herramientas, voz opcional)"
    )
    p_agente.add_argument(
        "--modo",
        choices=("plan", "preguntar", "aceptar-ediciones", "lote"),
        default="preguntar",
        help="modo de permisos (plan = solo lectura; lote = deniega lo no listado)",
    )
    p_agente.add_argument("--lang", default="es", help="idioma de trabajo")
    p_agente.add_argument(
        "--voz", action="store_true", help="entrada/salida de voz local (requiere aidam[voz])"
    )
    p_agente.add_argument(
        "--preguntas", action="store_true", help="activar el LLM local para ángulos y síntesis"
    )
    p_agente.add_argument("--nivel", type=int, choices=(0, 1, 2), default=None)

    p_imagen = sub.add_parser(
        "imagen", help="verificar el texto extraído de una imagen (OCR local)"
    )
    p_imagen.add_argument("ruta", help="ruta de la imagen")
    p_imagen.add_argument("--lang", default="es", help="idioma esperado del texto")
    p_imagen.add_argument("--json", action="store_true", help="salida en JSON")

    p_codigo = sub.add_parser(
        "codigo",
        help="comparar implementaciones MIDIENDO su rendimiento en el sandbox "
        "(el ganador sale de datos, no de opiniones)",
    )
    p_codigo.add_argument(
        "archivos", nargs="*",
        help="dos o más .py candidatos que definen la misma función "
        "(o ninguno, si se usa --tarea)",
    )
    p_codigo.add_argument(
        "--tarea", default="",
        help="descripción de la tarea: el LLM local propone las candidatas "
        "y el arnés las mide — el cronómetro decide, no el modelo",
    )
    p_codigo.add_argument("--candidatos", type=int, default=3,
                          help="cuántas candidatas propone el LLM con --tarea")
    p_codigo.add_argument(
        "--web", action="store_true",
        help="cosechar candidatas de la web (Stack Overflow y web abierta) "
        "además de las locales/LLM — el cronómetro sigue decidiendo",
    )
    p_codigo.add_argument(
        "--llamada", required=True,
        help="expresión a medir, p. ej. \"ordenar(datos)\"",
    )
    p_codigo.add_argument(
        "--preparacion", default="",
        help="código de preparación común (crear datos de prueba, imports)",
    )
    p_codigo.add_argument("--repeticiones", type=int, default=7)
    p_codigo.add_argument("--json", action="store_true", help="salida en JSON")

    sub.add_parser("permisos", help="mostrar las reglas de permisos vigentes del agente")

    p_interfaz = sub.add_parser(
        "interfaz", help="interfaz gráfica en el navegador (servidor local)"
    )
    p_interfaz.add_argument("--host", default="127.0.0.1", help="dirección de escucha")
    p_interfaz.add_argument("--puerto", type=int, default=8236, help="puerto de escucha")
    p_interfaz.add_argument(
        "--sin-navegador",
        action="store_true",
        help="no abrir el navegador automáticamente",
    )

    args = parser.parse_args(argv)

    if args.comando == "interfaz":
        try:
            from .servidor import servir
        except ImportError:
            print(
                "[aidam] la interfaz gráfica necesita dependencias extra: "
                "uv pip install -e '.[interfaz]'",
                file=sys.stderr,
            )
            return 1
        print(
            f"[aidam] interfaz en http://{args.host}:{args.puerto} (Ctrl+C para salir)",
            file=sys.stderr,
        )
        servir(host=args.host, puerto=args.puerto, abrir=not args.sin_navegador)
        return 0

    if args.comando == "investigar":
        import dataclasses as _dc

        from .agente.orquestador import investigar

        if args.sintesis and not args.preguntas:
            print("[aidam] --sintesis requiere --preguntas; sigo sin síntesis", file=sys.stderr)
        progreso = None if args.json else lambda m: print(f"[aidam] {m}", file=sys.stderr)
        resultado = investigar(
            args.afirmacion,
            nivel=args.nivel,
            lang=args.lang,
            max_idiomas=args.max_idiomas,
            preguntas=args.preguntas,
            progreso=progreso,
            sintetizar_final=args.sintesis,
            memoria_evidencia=not args.sin_memoria,
        )
        if args.json:
            salida = informe_a_dict(resultado.informe)
            salida["investigacion"] = {
                "nivel": resultado.nivel,
                "senales": _dc.asdict(resultado.senales),
                "angulos": [_dc.asdict(a) for a in resultado.angulos],
                "sintesis": resultado.sintesis,
                "respuesta": resultado.respuesta,
            }
            print(json.dumps(salida, ensure_ascii=False, indent=2))
        else:
            from rich.console import Console
            from rich.panel import Panel

            _imprimir(resultado.informe)
            print(
                f"\n[aidam] nivel de investigación: {resultado.nivel}"
                f" · ángulos: {len(resultado.angulos)}",
                file=sys.stderr,
            )
            if resultado.respuesta:
                titulo = "Respuesta" + (" (LLM, no juez)" if resultado.sintesis else "")
                Console().print(Panel(resultado.respuesta, title=titulo, border_style="cyan"))
        return 0

    if args.comando == "agente":
        from .agente.bucle import bucle_agente

        return bucle_agente(
            modo=args.modo.replace("-", "_"),
            lang=args.lang,
            voz=args.voz,
            nivel=args.nivel,
            preguntas=args.preguntas,
        )

    if args.comando == "imagen":
        from .agente.vision import verificar_imagen

        progreso = None if args.json else lambda m: print(f"[aidam] {m}", file=sys.stderr)
        informe = verificar_imagen(args.ruta, lang=args.lang, progreso=progreso)
        if args.json:
            print(_a_json(informe))
        else:
            _imprimir(informe)
        return 0

    if args.comando == "permisos":
        from .agente.permisos import cargar_motor

        motor = cargar_motor()
        print(f"modo: {motor.modo.value}")
        for tipo in ("denegar", "preguntar", "permitir"):
            for regla in (motor.reglas.get(tipo) or []):
                print(f"  {tipo:10s} {regla}")
        return 0

    if args.comando == "codigo":
        import dataclasses as _dc
        from pathlib import Path as _Path

        from .agente.codigo import comparar_candidatos

        candidatos = {}
        for ruta in args.archivos:
            p = _Path(ruta)
            candidatos[p.stem] = p.read_text()
        if args.tarea and args.web:
            from .agente.codigo import candidatos_desde_web

            print("[aidam] cosechando candidatas de la web…", file=sys.stderr)
            candidatos.update(candidatos_desde_web(args.tarea))
        if args.tarea and not args.web:
            from .agente.codigo import proponer_candidatos

            print("[aidam] el LLM local propone candidatas…", file=sys.stderr)
            candidatos.update(proponer_candidatos(args.tarea, n=args.candidatos))
        if len(candidatos) < 2:
            print("[aidam] hacen falta al menos 2 candidatas (archivos y/o --tarea "
                  "con el LLM local disponible)", file=sys.stderr)
            return 1
        resultado = comparar_candidatos(
            candidatos, args.llamada,
            preparacion=args.preparacion, repeticiones=args.repeticiones,
        )
        if args.json:
            print(json.dumps(_dc.asdict(resultado), ensure_ascii=False, indent=2, default=str))
        else:
            from rich.console import Console
            from rich.panel import Panel

            for m in resultado.mediciones:
                estado_m = (f"{m.mediana_ms:.3f} ms" if m.ok
                            else f"FALLÓ: {m.error.splitlines()[-1] if m.error else '?'}")
                print(f"  {m.nombre:20s} {estado_m}")
            Console().print(Panel(resultado.respuesta, title="Medición (sandbox, sin red)",
                                  border_style="cyan"))
        return 0

    if args.comando == "historial":
        from .memoria import MemoriaAgente

        memoria = MemoriaAgente()
        for fila in memoria.historial(args.limite):
            print(f"{fila['fecha']}  {fila['veredicto']:22s} "
                  f"({fila['confianza']:.2f})  {fila['afirmacion']}")
        memoria.cerrar()
        return 0

    if args.comando == "recordar":
        from .memoria import RUTA_DEFECTO
        from .vectores import IndiceEvidencia

        indice = IndiceEvidencia(RUTA_DEFECTO)
        resultados = indice.buscar(args.consulta, args.limite)
        if not resultados:
            print("[aidam] la memoria de evidencia está vacía todavía", file=sys.stderr)
        for r in resultados:
            print(f"({r['puntaje']:.2f}) {r['dominio']} · {r['fecha'][:10]}\n"
                  f"  «{r['texto'][:180]}…»\n  {r['url']}")
        indice.cerrar()
        return 0

    if args.comando == "fuentes":
        from .retrieve import FUENTES

        for nombre, (descripcion, categorias, _funcion) in FUENTES.items():
            ambito = ", ".join(sorted(categorias)) if categorias else "todas las categorías"
            print(f"{nombre:22s} {descripcion}  [{ambito}]")
        return 0

    from .pipeline import verificar

    memoria = None
    if not args.sin_memoria:
        from .memoria import MemoriaAgente

        memoria = MemoriaAgente()
        # Remembered verdicts are CONTEXT for the user, never a shortcut:
        # the claim is re-verified below regardless (facts change).
        for previa in memoria.buscar(args.afirmacion):
            print(
                f"[aidam] memoria: verificada el {previa['fecha']} → "
                f"{previa['veredicto']} ({previa['confianza']:.2f})",
                file=sys.stderr,
            )

    progreso = None if args.json else lambda m: print(f"[aidam] {m}", file=sys.stderr)
    informe = verificar(
        args.afirmacion,
        lang=args.lang,
        max_idiomas=args.max_idiomas,
        preguntas=args.preguntas,
        progreso=progreso,
    )

    if memoria is not None:
        memoria.guardar(informe)
        memoria.cerrar()

    if args.json:
        print(_a_json(informe))
    else:
        _imprimir(informe)
    return 0


if __name__ == "__main__":
    sys.exit(main())

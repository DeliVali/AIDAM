"""CLI de AIDAM: `aidam verificar "afirmación"`."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from . import __version__
from .models import Informe, Veredicto

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
    color, titulo = _ESTILO[informe.veredicto]
    consola.print(
        Panel(
            f"[bold]{informe.afirmacion}[/bold]\n\n"
            f"[{color} bold]{titulo}[/] · confianza {informe.confianza:.0%}",
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
    def limpiar(obj):
        if dataclasses.is_dataclass(obj):
            return {k: limpiar(v) for k, v in dataclasses.asdict(obj).items()}
        if isinstance(obj, list):
            return [limpiar(x) for x in obj]
        if hasattr(obj, "value"):
            return obj.value
        return obj

    return json.dumps(limpiar(informe), ensure_ascii=False, indent=2)


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
        "en modelos/mimo/",
    )
    p_verificar.add_argument("--json", action="store_true", help="salida en JSON")

    sub.add_parser("fuentes", help="listar las fuentes de evidencia registradas")

    args = parser.parse_args(argv)

    if args.comando == "fuentes":
        from .retrieve import FUENTES

        for nombre, (descripcion, categorias, _funcion) in FUENTES.items():
            ambito = ", ".join(sorted(categorias)) if categorias else "todas las categorías"
            print(f"{nombre:22s} {descripcion}  [{ambito}]")
        return 0

    from .pipeline import verificar

    progreso = None if args.json else lambda m: print(f"[aidam] {m}", file=sys.stderr)
    informe = verificar(
        args.afirmacion,
        lang=args.lang,
        max_idiomas=args.max_idiomas,
        preguntas=args.preguntas,
        progreso=progreso,
    )

    if args.json:
        print(_a_json(informe))
    else:
        _imprimir(informe)
    return 0


if __name__ == "__main__":
    sys.exit(main())

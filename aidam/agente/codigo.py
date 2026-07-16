"""Code path: candidate implementations, measured — never opined — winners.

Jeffrey's product rule (2026-07-16): when the user asks for code, the
agent must not pick the "best" implementation by taste. It measures.
Each candidate runs inside the bubblewrap sandbox (no network, read-only
filesystem, wall-clock timeout) under the same timing harness; the
measurements become Evidencia rows (fuente="medicion-local") so claims
about performance are verified against DATA the agent produced itself —
the generate→verify→select loop applied to code.

The comparison itself is deterministic arithmetic (fastest correct
candidate wins); the verifier's role is judging textual claims («X es
más rápido que Y») against the measurement evidence, not replacing the
stopwatch.
"""

from __future__ import annotations

import json
import statistics
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..models import Evidencia
from .sandbox import ejecutar_confinado, hay_bwrap

_PLANTILLA_ARNES = """
import json, statistics, timeit, traceback

candidato = {ruta_candidato!r}
llamada = {llamada!r}
preparacion = {preparacion!r}
repeticiones = {repeticiones}

espacio = {{}}
try:
    with open(candidato) as f:
        exec(compile(f.read(), candidato, "exec"), espacio)
    if preparacion:
        exec(preparacion, espacio)
    # correctness first: one call, capture the result fingerprint
    resultado = eval(llamada, espacio)
    huella = repr(resultado)[:200]
    tiempos = timeit.repeat(llamada, globals=espacio, number=1, repeat=repeticiones)
    print(json.dumps({{
        "ok": True,
        "huella": huella,
        "mediana_ms": statistics.median(tiempos) * 1000,
        "mejor_ms": min(tiempos) * 1000,
        "repeticiones": repeticiones,
    }}))
except Exception:
    print(json.dumps({{"ok": False, "error": traceback.format_exc()[-500:]}}))
"""


@dataclass
class MedicionCandidato:
    nombre: str
    ok: bool
    mediana_ms: float = 0.0
    mejor_ms: float = 0.0
    huella: str = ""
    error: str = ""


@dataclass
class ComparacionCodigo:
    """Measured comparison across candidates, ready for user and verifier."""

    llamada: str
    mediciones: list[MedicionCandidato] = field(default_factory=list)
    ganador: str = ""
    respuesta: str = ""
    evidencias: list[Evidencia] = field(default_factory=list)


def medir_candidato(nombre: str, codigo: str, llamada: str, preparacion: str = "",
                    repeticiones: int = 7, timeout: float = 60.0) -> MedicionCandidato:
    """Runs one candidate in the sandbox and returns its measurement."""
    if not hay_bwrap():
        raise RuntimeError("bubblewrap no está instalado (pacman -S bubblewrap)")
    with tempfile.TemporaryDirectory(prefix="aidam-codigo-") as raiz:
        raiz_p = Path(raiz)
        (raiz_p / "candidato.py").write_text(codigo)
        arnes = _PLANTILLA_ARNES.format(
            ruta_candidato=str(raiz_p / "candidato.py"),
            llamada=llamada, preparacion=preparacion, repeticiones=repeticiones,
        )
        (raiz_p / "arnes.py").write_text(arnes)
        resultado = ejecutar_confinado(
            ["python3", str(raiz_p / "arnes.py")], raiz_p, timeout=timeout,
        )
    if resultado.agotado:
        return MedicionCandidato(nombre=nombre, ok=False,
                                 error=f"tiempo agotado ({timeout:.0f}s)")
    try:
        datos = json.loads(resultado.stdout.strip().splitlines()[-1])
    except Exception:
        return MedicionCandidato(nombre=nombre, ok=False,
                                 error=(resultado.stderr or resultado.stdout)[-500:])
    if not datos.get("ok"):
        return MedicionCandidato(nombre=nombre, ok=False, error=datos.get("error", ""))
    return MedicionCandidato(
        nombre=nombre, ok=True, mediana_ms=datos["mediana_ms"],
        mejor_ms=datos["mejor_ms"], huella=datos["huella"],
    )


def comparar_candidatos(candidatos: dict[str, str], llamada: str,
                        preparacion: str = "", repeticiones: int = 7) -> ComparacionCodigo:
    """Measures every candidate and builds the answer + evidence rows.

    Winner = fastest median among candidates that ran correctly AND agree
    on the result fingerprint with the majority (a fast wrong answer is
    not an optimization). Disagreement is reported, never hidden.
    """
    mediciones = [
        medir_candidato(nombre, codigo, llamada, preparacion, repeticiones)
        for nombre, codigo in candidatos.items()
    ]
    correctas = [m for m in mediciones if m.ok]
    comparacion = ComparacionCodigo(llamada=llamada, mediciones=mediciones)

    if not correctas:
        comparacion.respuesta = (
            "Ninguna implementación corrió correctamente en el sandbox; "
            "no hay medición que comparar."
        )
        return comparacion

    huellas = [m.huella for m in correctas]
    moda = max(set(huellas), key=huellas.count)
    coincidentes = [m for m in correctas if m.huella == moda]
    discrepantes = [m for m in correctas if m.huella != moda]

    ganadora = min(coincidentes, key=lambda m: m.mediana_ms)
    comparacion.ganador = ganadora.nombre

    fecha_iso = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(timespec="seconds")
    for m in coincidentes:
        comparacion.evidencias.append(Evidencia(
            texto=(f"Medición local ({fecha_iso}): la implementación «{m.nombre}» "
                   f"ejecutó {llamada} en {m.mediana_ms:.3f} ms de mediana "
                   f"({m.mejor_ms:.3f} ms mejor caso, {len(coincidentes)} candidatas "
                   "con resultado idéntico, sandbox sin red)"),
            url=f"local://medicion/{m.nombre}",
            titulo=f"medición {m.nombre}",
            dominio="medicion.local",
            fuente="medicion-local",
            idioma="es",
        ))

    linea_ganadora = (
        f"La más rápida con resultado correcto es «{ganadora.nombre}»: "
        f"{ganadora.mediana_ms:.3f} ms de mediana sobre {llamada}"
    )
    otras = [
        f"{m.nombre} {m.mediana_ms:.3f} ms ({m.mediana_ms / ganadora.mediana_ms:.1f}×)"
        for m in sorted(coincidentes, key=lambda m: m.mediana_ms)[1:]
    ]
    partes = [linea_ganadora + (f"; después: {', '.join(otras)}." if otras else ".")]
    if discrepantes:
        partes.append(
            "OJO: " + ", ".join(f"«{m.nombre}»" for m in discrepantes)
            + " devolvió un resultado DISTINTO al de la mayoría — descalificada(s)."
        )
    fallidas = [m for m in mediciones if not m.ok]
    if fallidas:
        partes.append(
            "No corrieron: " + ", ".join(f"«{m.nombre}»" for m in fallidas) + "."
        )
    comparacion.respuesta = " ".join(partes)
    return comparacion

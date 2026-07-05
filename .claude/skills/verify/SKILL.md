---
name: verify
description: Cómo verificar cambios de AIDAM en runtime — conducir la CLI real, no los tests.
---

# Verificar AIDAM en runtime

La superficie es la CLI (`aidam`). El entorno vive en `.venv` (uv, Python 3.12).

## Handle

```bash
uv venv --python 3.12 && uv pip install -e ".[dev,verificador]"   # solo la primera vez
.venv/bin/aidam fuentes                                            # sanity: registro de fuentes
.venv/bin/aidam verificar "afirmación" [--lang en] [--max-idiomas N] [--json]
```

- Primera ejecución descarga el modelo (~1 GB); con `modelos/verificador-v0/`
  presente usa el modelo local entrenado.
- **`--json` apaga las líneas de progreso** (categoría del router incluida).
  Para observar el enrutamiento, correr SIN `--json` y mirar stderr:
  `[aidam] Buscando evidencia [categoria]: «…»`.
- Con `--json`, resumir evidencia con python: campos
  `hechos[].a_favor/en_contra[].evidencia.{dominio,fuente,idioma}`.

## Flujos que vale la pena conducir

- Afirmación de programación en inglés → debe enrutar `[programacion]` y traer
  `stackoverflow.com [stackexchange]`.
- Afirmación médica → NO debe traer stackexchange; vigilar si el router la
  manda a `[general]` (pierde europepmc — gap conocido de keywords).
- Mito viral («La Gran Muralla China es visible desde la Luna») → debe salir
  REFUTADO con evidencia `[desmentidos]` en contra.
- Sondas que aguantan: afirmación vacía (INSUFICIENTE 0%, sin crash),
  `--lang xx` (degrada a web, sin crash), `--max-idiomas 0` (monolingüe),
  sin argumentos (exit 2).

## Gotchas

- La recuperación es red viva (DDG, Wikipedia, APIs): resultados varían entre
  corridas; juzgar patrones (fuentes presentes, clase de veredicto), no textos
  exactos.
- El verificador emite warning de tokenizer regex al cargar el modelo local —
  ruido conocido, no es fallo.
- Los procesos largos (evals, entrenamientos) corren detached escribiendo a
  logs; no compiten con la CLI salvo por VRAM (~2 GB por proceso).

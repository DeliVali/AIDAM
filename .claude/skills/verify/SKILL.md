---
name: verify
description: How to verify AIDAM changes at runtime — drive the real CLI, not the tests.
---

# Verifying AIDAM at runtime

The surface is the CLI (`aidam`). The environment lives in `.venv` (uv, Python 3.12).

## Handle

```bash
uv venv --python 3.12 && uv pip install -e ".[dev,verificador]"   # first time only
.venv/bin/aidam fuentes                                            # sanity: source registry
.venv/bin/aidam verificar "claim" [--lang en] [--max-idiomas N] [--json]
```

- The first run downloads the model (~1 GB); with `modelos/verificador-v0/`
  present it uses the locally trained model.
- **`--json` turns off the progress lines** (router category included).
  To observe routing, run WITHOUT `--json` and watch stderr:
  `[aidam] Buscando evidencia [categoria]: «…»`.
- With `--json`, summarize evidence with python: fields
  `hechos[].a_favor/en_contra[].evidencia.{dominio,fuente,idioma}`.

## Flows worth driving

- Programming claim in English → must route `[programacion]` and bring
  `stackoverflow.com [stackexchange]`.
- Medical claim → must NOT bring stackexchange; watch whether the router
  sends it to `[general]` (loses europepmc — known keyword gap).
- Viral myth («La Gran Muralla China es visible desde la Luna») → must come
  out REFUTADO with `[desmentidos]` evidence against.
- Probes that must hold: empty claim (INSUFICIENTE 0%, no crash),
  `--lang xx` (degrades to web, no crash), `--max-idiomas 0` (monolingual),
  no arguments (exit 2).

## Gotchas

- Retrieval is live network (DDG, Wikipedia, APIs): results vary between
  runs; judge patterns (sources present, verdict class), not exact texts.
- The verifier emits a tokenizer regex warning when loading the local model —
  known noise, not a failure.
- Long processes (evals, trainings) run detached writing to logs; they don't
  compete with the CLI except for VRAM (~2 GB per process).

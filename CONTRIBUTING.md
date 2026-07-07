# Contributing to AIDAM

AIDAM is an open project: knowledge is free and the tools to verify it should be
too. Every contribution is welcome — code, data, evaluations, documentation,
translations or ideas in the issues.

## Setting up

Requirements: Python ≥ 3.10 and [uv](https://docs.astral.sh/uv/) (recommended).

```bash
git clone https://github.com/DeliVali/AIDAM.git
cd AIDAM
uv venv --python 3.12
uv pip install -e ".[dev]"           # core + tests
uv pip install -e ".[verificador]"   # + verifier model (torch, transformers)
```

Run the tests (no GPU or network needed):

```bash
.venv/bin/python -m pytest
```

Try the full system (downloads the model on first run):

```bash
.venv/bin/aidam verificar "The Eiffel Tower is in Paris" --lang en
```

## Where to help

The [roadmap](docs/ROADMAP.md) rules. Open areas by difficulty:

| Level | Area |
|---|---|
| Easy | More retriever sources: write a `(query, lang) -> list[Evidencia]` function and register it in `FUENTES` (`aidam/retrieve.py`) — there are 10 examples |
| Easy | Better CLI output, translations, documentation |
| Medium | Decomposer heuristics; tests for hard cases |
| Medium | Aggregator metrics (source independence, temporality) |
| Hard | AVeriTeC / LLM-AggreFact evaluation improvements |
| Hard | Synthetic data generation and verifier training |

## Ground rules

1. **Every verdict cites its evidence.** No change may make the system assert
   anything without a traceable source.
2. **The aggregator stays auditable.** Explicit, tested logic; no black boxes in
   Module 4.
3. **Consumer hardware first.** If your improvement demands a datacenter GPU, it
   doesn't belong in this repo (or it goes behind an optional flag).
4. **Tests for the logic.** Deterministic modules (decomposer, aggregator) carry
   unit tests; model-backed modules carry at least a smoke test.

## Workflow

1. Open an issue describing the change (or pick an existing one).
2. Branch from `main`, small focused changes.
3. `pytest` green.
4. Pull request explaining *what* and *why*; CI and review do the rest.

## License

By contributing you agree that your work is published under
[Apache 2.0](LICENSE), the project's license: free to use, modify and
redistribute, with an explicit patent grant. Your code belongs to everyone,
forever.

<img src="assets/aidamlogo.svg" alt="AIDAM" width="100%">

# AIDAM

An open **general-purpose local agent**: it reasons, acts and verifies on your
machine — as close to a Claude Code as free, open-source, local pieces allow,
with as little hallucination as measurement can enforce. Its distinguishing
architecture is the **trust layer**: a small specialized fact-checking core (a
280M NLI verifier plus auditable aggregation) that the reasoning models
**consult many times** while they work. That core is a fundamental component —
verdicts always come from it, never from an LLM — but it does not dictate the
whole project: tasks, code, files and conversation are driven by a quantized
local reasoning model that checks its facts against evidence before asserting
them. Every verdict cites its sources.

## How it works

1. **Decomposes** the claim into verifiable facts.
2. **Retrieves** evidence in parallel from 22 source families: the Wikipedia
   family (multilingual articles, Wikidata facts, Wikinews, Wikiquote,
   Wikisource, Wiktionary), the open web with a search aimed specifically at
   fact-checkers, global press (GDELT), academic literature (Semantic Scholar,
   OpenAlex, arXiv, Europe PMC, Crossref), official registries (openFDA,
   ClinicalTrials.gov, NIST NVD, US court records), official technical and
   mathematical documentation, and Stack Exchange. A router picks sources
   based on the claim's topic.
3. **Judges** each (fact, passage) pair with a multilingual 280M-parameter NLI
   verifier trained for this task.
4. **Aggregates** with explicit, auditable rules: one domain is one voice,
   fact-checkers and academia weigh more, repeating the claim does not count
   as evidence, and misread debunking articles are discounted.
5. Returns the verdict — **supported / refuted / conflicting evidence /
   not enough evidence** — with the citations that justify it.

Optional: a local reasoning LLM (DeepSeek-R1-Qwen3-8B quantized, isolated
process) generates search questions to guide retrieval, resolves claims the
aggregator can't decide, and detects claims that mislead by omission.

## Usage

```bash
git clone https://github.com/DeliVali/AIDAM.git && cd AIDAM
uv venv --python 3.12
uv pip install -e ".[verificador]"
.venv/bin/aidam verificar "The Eiffel Tower is in Paris" --lang en
```

Or as a graphical interface — live progress, per-search permission prompts
(or full-auto mode), verification history, and optional local voice dictation
and image OCR (see [docs/INTERFAZ.md](docs/INTERFAZ.md)). In the browser:

```bash
uv pip install -e ".[verificador,interfaz]"
.venv/bin/aidam interfaz
```

Or as a desktop app with its own window (Electron, in [escritorio/](escritorio/)):

```bash
cd escritorio && npm install && npm start
```

The agent understands conversation, not just claims (each behavior born
from a measured product failure — see [docs/AGENT.md](docs/AGENT.md)):

- **Questions get answers**, not verdicts: the sentence that answers,
  cited («La Mona Lisa cuelga en el Louvre. Fuente: …»); code questions
  get a copy-ready example extracted verbatim from the evidence.
- **Ambiguity gets a question back**: «¿qué es lora?» splits the evidence
  into senses (IoT radio vs ML fine-tuning) and the agent asks which one
  you mean — your reply joins the same context block and refines the search.
- **Context sticks**: follow-ups («y en ese contexto…», «volviendo a la
  muralla…») resolve against the right earlier turn via a three-tier
  RAM-only memory (verbatim window, compacted terms, keyword graph).
- **Your computer, natively**: «mueve Descargas/fotos a Documentos» shows
  a permission card with the exact action; HOME-only, deletions always go
  to the trash.
- **Code is measured, never opined**: candidates (yours, the local LLM's,
  or web-harvested) race in a sandbox; a fast wrong answer is disqualified
  by its result fingerprint before speed counts.
- **Plugs into assistant infrastructure**: an OpenAI-compatible endpoint
  (`/v1/chat/completions`) lets OpenClaw-style gateways use AIDAM from
  WhatsApp/Telegram — no messenger bridges to maintain here.
- **Task mode (ReAct)**: `aidam tarea "resume los README de esta carpeta"`
  — the local reasoning model runs a thought→action→observation cycle over
  permission-gated tools (read/write/sandboxed commands/evidence search),
  consulting the NLI verifier before asserting facts; unsupported sentences
  in the final answer are visibly marked «sin verificar», never hidden.

Runs on GPU, on CPU without PyTorch (`aidam[verificador-cpu]`, ONNX Runtime),
or on low-RAM machines (319 MB quantized model, `AIDAM_BACKEND=onnx-mini`).
The model is published on
[HuggingFace](https://huggingface.co/DeliVali/aidam-verificador).

## Technology

- **Verifier**: mDeBERTa-v3 (280M) fine-tuned on VitaminC, MNLI and our own
  synthetic data — including shortcut-proofed contrast sets that teach
  specific traced failures (denial patterns, scientific hedged language).
  PyTorch for training; ONNX Runtime for CPU; weight-only quantization
  (block-wise int4 + int8 embeddings) for the mini variant.
- **Local LLM**: DeepSeek-R1-0528-Qwen3-8B as GGUF Q4 via llama.cpp
  (selectable via `AIDAM_MODELO_PREGUNTAS`).
- **Continuous evaluation**: every change is measured before it lands, on
  four public benchmarks, with rejected experiments documented alongside
  promoted ones (see [docs/ROADMAP.md](docs/ROADMAP.md)).

## Results

One 280M-parameter verifier, measured simultaneously on four public benchmarks:

| Benchmark | Domain | Result |
|---|---|---|
| FEVER (dev, balanced) | Wikipedia claims | **77.7%** accuracy (a FEVER-specialized variant reaches **86.0%**) |
| SciFact (dev) | Scientific claims | **63.7%** accuracy, F1 macro 0.611 |
| AVeriTeC (full dev, 500) | Real-world viral claims, 4-class | **62.6%** accuracy — above the 61% majority baseline |
| LLM-AggreFact | LLM grounding | 65.1% balanced accuracy |

AVeriTeC is evaluated against the shared task's official knowledge store
(reproducible, ~11 s per claim). Against the same reasoning LLM answering
from memory alone: +37 accuracy points. Full history — including every
rejected experiment and why — lives in [docs/ROADMAP.md](docs/ROADMAP.md).

Findings from this research that transfer beyond AIDAM: synthetic training
contrast sets only work when every template appears with all labels in
identical surface structure (otherwise the model learns the vocabulary, not
the skill); a verified pair-level mechanism does not guarantee claim-level
gains unless corrective evidence exists in retrieval; and live search engines
degrade cumulatively within a single evaluation run, so reproducible
fact-checking evaluation needs frozen evidence.

## Support

AIDAM is developed independently on consumer hardware. Donations via
[GitHub Sponsors](https://github.com/sponsors/DeliVali) fund the compute for
training and evaluation — every number in the results table above was
measured on a single consumer GPU.

## Contributing

Apache 2.0 license — © 2026 [Jeffrey Romero Del Val](https://github.com/DeliVali).
Free to use, modify and redistribute; keep the [NOTICE](NOTICE) attribution.
Contribution guide in [CONTRIBUTING.md](CONTRIBUTING.md); code of conduct in
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

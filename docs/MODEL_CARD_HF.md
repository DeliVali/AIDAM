---
language:
  - es
  - en
  - multilingual
license: apache-2.0
tags:
  - fact-checking
  - natural-language-inference
  - claim-verification
  - text-classification
base_model: jhu-clsp/mmBERT-base
pipeline_tag: text-classification
---

<!-- Source of truth for the Hub model card at DeliVali/aidam-verificador.
     Upload after `huggingface-cli login` with:
     .venv/bin/python -c "from huggingface_hub import HfApi; HfApi().upload_file(
         path_or_fileobj='docs/MODEL_CARD_HF.md',
         path_in_repo='README.md', repo_id='DeliVali/aidam-verificador')" -->

# AIDAM verifier — small comparative-logic NLI core

The verification core of [AIDAM](https://github.com/DeliVali/AIDAM), an
open fact-checking agent by **Jeffrey Romero Del Val**: a ~0.3B
multilingual NLI model that judges *(evidence, claim)* pairs —
supports / neutral / refutes — and an auditable aggregation layer that
turns pair judgments into verdicts with citations. Verdicts always come
from this core plus explicit math; LLMs assist retrieval and narration
but never judge (measured: LLM-as-sole-judge 24.0% vs the aggregator's
58.0% on AVeriTeC-100).

## Benchmarks (honest, all measured; details in the repo ROADMAP)

| Benchmark | AIDAM best | Reference |
|---|---|---|
| LLM-AggreFact (BAcc, 11 subsets) | **71.0** (v20, 0.3B) | MiniCheck-FT5 (0.77B): 74.7 |
| FEVER (label acc., oracle evidence) | **86.0** (v11 specialist) | large fine-tuned models: ~88-92 |
| SciFact (label acc., oracle) | **66.3** (v15) | — |
| AVeriTeC dev-500 (offline store) | **62.6** (v10, production) | majority baseline: 61.0 |

Every promoted version passed pre-registered gates; rejected experiments
are documented alongside the promotions (label-poisoning audits, register
interference laws, backbone trade-offs) in
[docs/ROADMAP.md](https://github.com/DeliVali/AIDAM/blob/main/docs/ROADMAP.md).

## The agent around the core

The model ships inside a full local agent (GPU, CPU/ONNX, or 319 MB
quantized): multi-source multilingual retrieval with a calibrated
meaning-level evidence filter, question answering with cited sentences,
clarification questions when evidence splits into distinct senses,
conversational context (keyword-graph memory), sandboxed measured code
comparison, native file control with permission cards, and an
OpenAI-compatible endpoint so assistant gateways (OpenClaw-style) can use
AIDAM from any messenger.

## Training

mDeBERTa-v3 and mmBERT lineages fine-tuned on VitaminC + MNLI/ANLI plus
purpose-built, shortcut-proofed pair sets (denial patterns, scientific
register, FEVER register, D2C long-document and summary-shaped pairs,
cross-claim abstention pairs) — each dataset promoted only after moving a
benchmark behind pre-set bars. Recipes and generators are open in
[`training/`](https://github.com/DeliVali/AIDAM/tree/main/training).

## License and credit

Apache-2.0. Please keep visible credit to **Jeffrey Romero Del Val**
(NOTICE file; citation in CITATION.cff). Information is free: the only
arbiter is evidence.

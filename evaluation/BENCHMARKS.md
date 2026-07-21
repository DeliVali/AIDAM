# External benchmarks and the information-fidelity protocol

Owner's directive (2026-07-19): survey the benchmark landscape for agents
of AIDAM's kind and define how to test information fidelity against other
systems. Comparison policy stands: published numbers, no paid-API spend.

## Tier 1 — BFCL V4 (Berkeley Function-Calling Leaderboard): the Program-A reference

Why: the standard public comparison for tool-call reliability, exactly the
reasoner's arena. Verified first-hand (2026-07-19, live leaderboard CSV):

| Anchor (BFCL V4, overall acc) | Score |
|---|---|
| Claude-Opus-4.5 (FC) — #1 | **77.47%** |
| Claude-Sonnet-4.5 (FC) — #2 | 73.24% |
| Gemini-3-Pro-Preview — #3 | 72.51% |
| GLM-4.6 (open, MIT) — #4 | 72.38% |
| **xLAM-2-8b-fc-r — best published 8B** (rank 34) | **46.68%** |
| Qwen3-8B (FC) | 42.57% |
| ToolACE-2-8B | 42.44% |
| Hammer2.1-7b | 31.67% |

The honest competitive statement Program A aims for: close the gap from
the 8B ceiling (~46.7) toward the frontier ceiling (~77.5) on the pinned
version. Two hard honesty rules: (1) **pin the BFCL version and date** —
mid-2024 numbers (xLAM-7b 88.24%, Hammer-7B 83.92%) are NOT comparable to
V4; (2) Fable 5 does not appear on BFCL — the highest published Anthropic
entry is Opus 4.5, so that is the frontier anchor we cite.

Local reproducibility (verified): dataset on HF
(`gorilla-llm/Berkeley-Function-Calling-Leaderboard`, Apache-2.0, 11.7 MB
JSON — do NOT use `load_dataset`); harness in
`ShishirPatil/gorilla/berkeley-function-call-leaderboard` (pip
`bfcl-eval`). Serving plan for our reasoner: llama.cpp server exposing the
GGUF (with/without adapters) behind an OpenAI-compatible endpoint. V4's
category columns map to our programs: Multi-Turn ↔ ReAct loop,
Irrelevance Detection ↔ abstention discipline, Web Search ↔ evidence
tools.

### First local run of the base reasoner — measured 2026-07-20

Base reasoner **DeepSeek-R1-0528-Qwen3-8B, Q4_K_M GGUF**, served on
`llama_cpp.server` (all layers on GPU), **prompt mode** (no native FC
format), temperature 0.001. Ran the **non-live single-turn subset** —
5 categories, 1235 cases — via `bfcl generate`/`evaluate`
(`evaluation/bfcl/correr_fase1.sh`):

| Category (BFCL V4, non-live) | Accuracy |
|---|---|
| Simple (Python) AST | 70.75% |
| Multiple AST | 67.50% |
| Parallel AST | 59.00% |
| Parallel-Multiple AST | 48.00% |
| Irrelevance Detection | 85.42% |
| **Non-Live Overall** | **49.52%** |

**Read this with the harness's own honesty rules — it is NOT yet comparable
to the anchor table:**
- The anchors are **Overall V4 accuracy**, which folds in Live, Multi-Turn,
  Web-Search and Memory. This run is the **non-live single-turn subset only**,
  so 49.52% and the anchors' 46.68/77.47 are **different metrics** — do not
  put them head to head yet.
- The harness's `data_overall.csv` printed **9.22%**, and that number is
  **invalid**: unrun sections (Multi-Turn especially — the one that maps to
  our ReAct loop) count as zero, deflating the mean. Neither 49.52% nor 9.22%
  is the leaderboard-comparable Overall figure.
- Comparison is **prompt-mode vs the anchors' FC mode** (xLAM-2-8b-fc-r is
  function-calling-native). A fair 8B-vs-8B read needs either the anchors'
  non-live sub-scores or our own full-Overall run.

Honest next step for a true head-to-head: run the remaining V4 sections
(multi-turn, live, web-search) on the same model to produce an Overall
number, then compare to the 46.7 8B ceiling. Parallel-Multiple (48%) and the
multi-turn gap are where the base 8B will hurt most — exactly what the
fine-tuning program (docs/AGENT.md, R-rounds) targets. This run is the
**baseline before any adapter**, per GATE FT.

## Tier 2 — τ²-bench: agentic task completion with pass^k

MIT-licensed simulator (sierra-research/tau2-bench: airline, retail,
telecom domains), provider-agnostic via LiteLLM → plugs into our
`/v1/chat/completions` endpoint directly. Its **pass^k** metric (success
in ALL k trials — verified in arXiv:2507.21504) measures the consistency
dimension our temperature-0 loop claims; leaderboard at taubench.com.
Phase 2, after BFCL lands.

## Tier 3 — Information fidelity: our protocol + the comparison we already own

- **End-to-end fact-checking**: we already run AVeriTeC dev-500 (62.6,
  v10) — the shared-task ecosystem is the published comparison set for
  whole-system verification. Keep as-is.
- **Citation-support protocol (ALCE-style), self-implemented**: for the
  answer mode, measure **citation recall/precision** — every factual
  sentence in an answer vs the passage(s) it cites, judged by the resident
  NLI (the same instrument as the grounding gate, so the metric audits the
  product mechanism directly). Report both: % answer sentences supported
  by their cited source (recall) and % citations that actually support
  their sentence (precision). Published ALCE-protocol numbers from RAG
  papers are the reference frame; ours are directly comparable in method.

  **Measured 2026-07-20** (`evaluation/eval_citation_support.py`, 261 answers
  over AVeriTeC dev questions + the offline knowledge store, threshold 0.6 —
  the grounding gate's own):

  | Metric | Result |
  |---|---|
  | citation recall | **95.0%** (248/261 sentences entailed by a cited source) |
  | precision, **primary** citation (`Source:`) | **94.6%** (247/261) |
  | precision, **secondary** citation (`Also covered by:`) | **5.6%** (29/522) |

  Read honestly, three ways:
  - Recall is high **by construction**, not by merit: this answer mode is
    extractive (it quotes a retrieved sentence verbatim). The number only
    becomes load-bearing once `sintesis.sintetizar` writes the answer.
  - Primary-citation precision (94.6%) is the genuinely good signal: when
    AIDAM says «Source: X», X almost always backs the sentence.
  - **Secondary citations are decorative — a measured product defect.**
    `responder_pregunta` picks the «Also covered by» domains by their
    *retrieval rank against the question*, and never checks them against the
    *sentence the answer actually asserts*: topical relevance is not support.
    Verified not to be a harness artifact (all secondary domains resolve to
    real passages in the evidence; the 5.6% comes from the NLI, not a failed
    lookup). Failure traces: `--salida`. Uncorrected as of this entry — the
    natural fix (filter those domains by entailment against the chosen
    sentence, reusing the already-loaded NLI) is a product change and needs
    its own A/B before promotion.
- **Rejected for cause — SimpleQA Verified** (DeepMind, 1,000 prompts):
  its authors bar tool use (search makes it trivial), and grading requires
  a paid GPT-4.1 autorater. Both clauses disqualify it for a tool-using,
  no-paid-API agent. Documented so we don't relitigate it.

## Execution order

1. ~~BFCL V4 local run of the base reasoner (llama-server + bfcl-eval)~~
   **non-live subset done 2026-07-20** (49.52%, see above); full-Overall run
   still pending for anchor comparison. Every R-round adapter candidate runs
   it as part of GATE FT.
2. ~~Citation-support harness over the answer mode~~ **done 2026-07-20**
   (`evaluation/eval_citation_support.py`; numbers and the secondary-citation
   defect in Tier 3 above).
3. τ²-bench subset via the OpenAI endpoint; pass^k reported.

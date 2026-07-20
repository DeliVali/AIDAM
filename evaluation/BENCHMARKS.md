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
- **Rejected for cause — SimpleQA Verified** (DeepMind, 1,000 prompts):
  its authors bar tool use (search makes it trivial), and grading requires
  a paid GPT-4.1 autorater. Both clauses disqualify it for a tool-using,
  no-paid-API agent. Documented so we don't relitigate it.

## Execution order

1. BFCL V4 local run of the base reasoner (llama-server + bfcl-eval),
   score recorded next to the anchors above; then every R-round adapter
   candidate runs it as part of GATE FT.
2. Citation-support harness over the answer mode (reuses the NLI; ~small).
3. τ²-bench subset via the OpenAI endpoint; pass^k reported.

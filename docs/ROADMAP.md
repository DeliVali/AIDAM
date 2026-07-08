# AIDAM roadmap

General rule: **every phase produces something that works and is measured against a
public benchmark**. No architectures floating in the air for months.

## Phase 0 — Working pipeline from existing pieces (2–4 weeks)

Build the complete end-to-end system using already-published models. This validates
the architecture before training anything, and gives us the baseline to beat.

- [x] Decomposer v0 (heuristic; the neural VeriScore-style one is Phase 1)
- [x] Retriever: Wikipedia + web search, one voice per domain (independence)
- [x] Verifier: multilingual NLI mDeBERTa-v3 (~280M) — chosen over MiniCheck
      because it works in Spanish from day one
- [x] Aggregator v0: auditable weighted majority, 4 verdict classes, with tests
- [x] CLI: `aidam verificar "claim"` → verdict + citations (7.9 s per real claim)
- [x] **AVeriTeC evaluation (2026-07-05, first 100 of dev)**: 30–31% accuracy,
      macro F1 0.21–0.25 (majority baseline: 61%). The number is harsh and that is
      the point: from here on, every change gets measured. Script in
      `evaluation/eval_averitec.py` (live retrieval, not the shared task's official
      track). **Measured diagnosis**: the dominant failure is viral lie → "supported"
      (25/100); in most of those cases the fact-checker never appears in the evidence,
      and when it does, its truncated snippet *repeats* the claim and the verifier
      reads it as support. The bottleneck is evidence quality (snippets), not
      aggregation.

**Success criterion:** the full pipeline verifies a real claim in <1 minute (the
AVeriTeC 2025 shared task standard) and publishes its score.

**Status (2026-07-06) — full dev set (500 claims):**
- **AIDAM: 44.0% accuracy, macro F1 0.318, 17.9 s/claim** (Refuted F1 0.604,
  Supported 0.390). Series on the first 100: 30→31→37→39→41→44→45.
- **Head-to-head against a current (2026) model without retrieval** — same 100
  claims, MiMo-7B-RL with free reasoning and only parametric memory: **25.0% /
  F1 0.186 / 63.7 s**. AIDAM: **41.0% / 0.274 / 20 s** → **+16 points and 3x
  faster**: live evidence beats recall. (`evaluation/eval_baseline_llm.py`)
- Structural pendings: NEI still weak, and the 61% majority ceiling still above.
- **LLM-AggreFact (2026-07-06)**: verifier v3 scores **66.2% average balanced
  accuracy** over the 11 test datasets (29,320 pairs) — above generic NLI
  (roberta-large ≈64%), 8.5 points below MiniCheck-FT5 (≈74-75%). Best: Reveal
  85.1%; weakest: ExpertQA 56.3%, WiCE 58.6%. Honest read: a multilingual model
  competing on an English long-document benchmark — closing the gap is the
  remaining Phase 1 item (synthetic data with long documents and multi-sentence
  composition, the regime MiniCheck trained for).

## Phase 1 — Train our own verifier (1–2 months)

Replicate, then try to beat, the MiniCheck recipe with our own data.

- [x] **v0 trained (2026-07-05)**: contrastive fine-tuning on VitaminC (120k pairs)
      from the multilingual NLI checkpoint, on an RTX 5070 (11 min).
      **VitaminC test: 73.3% → 88.8% accuracy, macro F1 0.664 → 0.845.**
      Script in `training/train_verifier.py`.
      ⚠️ With transformers v5 (5.13) training collapses to a single class
      (DeBERTa-v3 regression); that is why `pyproject.toml` pins `<5`.
- [x] **v1 with neutral restored (2026-07-05)**: training on VitaminC alone
      (contrastive) made the model prone to "refute" with related but non-probative
      passages — caught by driving the CLI, not by the benchmark. Fix: mix 120k
      VitaminC + 60k MNLI. VitaminC test holds (88.75%) and over-refutation drops.
      Known residue: encyclopedic intros still vote "against" at ~70-79% — synthetic
      data goal #1 is hard-neutral pairs (generic intro × specific claim).
- [x] **v2 with hard neutrals (2026-07-05)**: 30k mechanical pairs from VitaminC's
      structure (same page, different fact — Auto-GDA recipe,
      `training/generate_neutrals.py`). The measured spurious refutation dropped
      from 86% to 53% (below the signal threshold); VitaminC test 88.21%.
      "Python lists are mutable": REFUTED 74% → SUPPORTED 100%.
- [x] **v3 with LLM-generated subtle errors (2026-07-06)**: 4k pairs generated with
      a local reasoning LLM (minimal edits that flip the label — MiniCheck recipe);
      VitaminC test 87.8%, macro F1 0.832. Published at
      [huggingface.co/DeliVali/aidam-verificador](https://huggingface.co/DeliVali/aidam-verificador),
      including the 319 MB quantized `onnx-mini` variant.
- [ ] Spanish training data (VitaminC is English; the model keeps the base
      checkpoint's Spanish, but it must be measured — XNLI-es is contaminated for
      this base — and reinforced)
- [x] Probability calibration installed (temperature scaling; finding: the model was
      already calibrated, T=1.007, ECE 1.2% — the AVeriTeC gap is domain shift)
- [x] Published on HuggingFace with open weights (2026-07-06)

**Success criterion:** ≥ MiniCheck-FT5 on LLM-AggreFact; first competitive small
verifier in Spanish.

## Phase 2 — Serious comparative logic (1–2 months)

- [x] **Source expansion (2026-07-05)**: extensible registry with parallel families —
      Wikipedia (mono and multilingual), Wikinews, open web, Semantic Scholar,
      OpenAlex, arXiv and Europe PMC. *Verified: medical claim judged with FDA,
      academic papers on both sides, Wikinews and French Wikipedia, in 7.3 s.*
      Adding a source = one registered function (see CONTRIBUTING).
- [x] **Multilingual retrieval (2026-07-05)**: Wikipedia interlanguage links →
      evidence in en/fr/de/ru/zh/… without a translation model; the verifier judges
      cross-language pairs directly. `--max-idiomas` in the CLI. *Verified: Spanish
      claim supported by the English (96%) and German (95%) Wikipedias.* Pending:
      cross-lingual relevance ranking with multilingual embeddings (distant languages
      currently contribute only their article lead).
- [ ] Source-independence model (syndicated/copied content detection)
- [x] **Reliability priors v0 + anti-echo rule (2026-07-05)**: fact-checkers weigh
      8x, encyclopedias/academia 2.5x, .gov/.edu 2x; a snippet that merely repeats
      the claim barely counts as support ("echo is not evidence"). With tests.
      **A/B on AVeriTeC-100**: correct refutations 13→20, accuracy 30→31%, macro F1
      dropped 0.25→0.21 (some true claims now refuted by partial debunks). It helps,
      but evidence quality sets the ceiling: see next.
- [x] **Full-page evidence + debunk-targeted search (2026-07-05)**: full text of top
      results (trafilatura) and a reformulated query ("<claim> fact check"). With the
      other fixes: AVeriTeC-100 30%→37%, Refuted F1 0.529, and "the Great Wall is
      visible from the Moon" → REFUTED 93%.
- [x] **Category router + probative gate + recalibrated echo (2026-07-05)**: the
      agent picks sources by topic (programming→Stack Overflow, medicine→Europe PMC;
      academic sources are universal: a misroute adds noise, never removes signal);
      passages sharing <2 content words with the fact are not judged (generic intros
      were being read as contradiction); anti-echo only applies to long claims (on
      short ones, coverage ≠ echo). All of it came out of a failed runtime `/verify`
      — each rule has its regression test.
- [x] **Search-question generation (2026-07-05)**: a local quantized reasoning LLM
      (Q4, llama.cpp, isolated worker process) generates the questions whose answers
      would confirm or refute the claim — the technique of the AVeriTeC 2.0 winners.
      `--preguntas` flag. **With verifier v2 + questions: AVeriTeC-100 37% → 39%,
      macro F1 0.254 → 0.308, NEI F1 0.077 → 0.300.** 24.5 s/claim, within the
      shared task's 1-minute budget.
- [ ] Tune priors from data (learned from historical accuracy, not by hand)
- [x] **Reliability tie-breaking (2026-07-05)**: in the tie zone, real conflict only
      if BOTH sides have a reliable voice; web noise tying with a credible debunk =
      refutation (measured: 13/16 predicted "conflicting" were refuted).
      **AVeriTeC-100: 39% → 41%, Refuted F1 0.577.**
- [x] **Omission judge for cherry-picking (2026-07-05/06)**: on SUPPORTED verdicts
      with contrary context on the table, the local LLM judges whether the claim
      misleads by omission — using ONLY retrieved evidence, never parametric memory.
      First version over-fired at scale (109 predicted vs 38 gold on the 500);
      tuned with two brakes (strong contrary signal ≥0.75 required, and the omission
      must undermine the claim's CENTRAL point): **AVeriTeC-100 41% → 44%**,
      over-firing 23→3.
- [x] **The attribution trap (2026-07-06)**: passages that "support" while carrying
      debunk markers ("purportedly", "hoax", "fact check"…) are articles describing
      the myth, not asserting it — their support is discounted.
      **AVeriTeC-100: 44% → 45%, Refuted F1 0.627** (series:
      30→31→37→39→41→44→45).
- [x] **Search-engine rotation (2026-07-07)**: after a day of evaluations,
      DuckDuckGo blocked the machine (73/100 claims with zero evidence, 17%
      accuracy — a retrieval failure, not a reasoning one). `_buscar_ddg` now
      rotates duckduckgo → bing → yahoo; no single engine is a point of failure.
- [ ] **Question-generator A/B (MiMo-7B-RL vs DeepSeek-R1-0528-Qwen3-8B) —
      pending, first attempt invalid (2026-07-07)**: the DeepSeek run scored 16%
      with 75/100 claims at zero evidence voices — during the run every engine
      (including Bing/Yahoo fallbacks) rate-limited the machine's IP, so the
      number measures the starved network, not the brain. MiMo stays as the
      default (`models/mimo/`, the measured 45%); DeepSeek remains selectable
      via `AIDAM_MODELO_PREGUNTAS`. Re-run when the IP cools down, ideally with
      cached or paced retrieval so the A/B isolates the model.
- [ ] Temporal handling: volatile vs. stable facts
- [ ] Active search for contrary evidence (anti-confirmation bias)

**Success criterion:** measurable improvement on AVeriTeC's "conflicting evidence"
class, the hardest in the benchmark.

## Phase 3 — Frontier mode (2–3 months, research)

- [ ] Router: is this evidence-less fact computable, deducible, or only proposable?
- [ ] Code-execution sandbox for computable facts
- [ ] Deduction engine over already-verified facts (explicit rules, auditable)
- [ ] Verification-protocol generator for the non-computable

**Success criterion:** on a set of questions with no direct answer on the web but
computable (e.g. "does a 3 m cube of water fit in X?"), the system solves them by
simulation instead of answering "I don't know".

## Phase 4 — Verified generation (can start after Phase 1, in parallel)

The generate→verify→select loop, starting with the domain where verification is
objective: **code**.

- [ ] Execution sandbox (containers) with automatic tests, benchmark and profiling
- [ ] Code generator: small quantized Qwen3-Coder (Q4) on a consumer GPU
- [ ] Best-of-N loop: N candidates → execution-based score → the best survives;
      if none passes, retry with the failure feedback
- [ ] "Efficiency mode": the score includes measured time and memory, not just
      correctness
- [ ] Anchored writing: all generated text passes through Module 3 before delivery
- [ ] Images: orchestrate local FLUX.2 Klein / Z-Image Turbo + prompt-adherence score

**Success criterion:** on a set of code tasks with tests, AIDAM (small generator +
verifier) matches a frontier assistant's success rate at <10% of the cost per solved
task.

## Phase 5 — Extreme efficiency (ongoing)

- [x] **Verifier on ONNX → any CPU (2026-07-05)**: accuracy identical to PyTorch
      (88.3%), 1.4x faster on CPU, and the runtime weighs ~50 MB instead of ~3 GB
      (`pip install aidam[verificador-cpu]`, automatic backend when torch is absent).
      Export: `training/quantize_verifier.py`.
      ⚠️ Measured finding: dynamic INT8 **breaks** DeBERTa-v3 (88.3% → 51.4%;
      per-channel doesn't rescue it either) — its activation outliers don't tolerate
      activation quantization.
- [x] **Real verifier quantization (2026-07-06)**: the route was weight-only, not
      QAT — block-wise INT4 weights (MatMulNBits) + INT8 embeddings, activations
      untouched in fp32 (DeBERTa-v3's activation outliers were the poison: even
      FFN-only collapsed under dynamic quantization).
      **"mini" model: 1.1 GB → 319 MB (3.4x), 86.1% (−2.2), 39 ms/pair (2x)** —
      `AIDAM_BACKEND=onnx-mini` for low-RAM machines; fp32/ONNX remains the CPU
      default. The same technique family used by current LLMs.
- [ ] BitNet experiment: fine-tune bitnet-b1.58-2B-4T + deploy with bitnet.cpp
- [ ] Distill the decomposer to <500M
- [ ] Fuse decomposition+verification into one pass (VeriFastScore style)

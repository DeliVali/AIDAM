# AIDAM architecture

AIDAM is not a model: it is a **compound system** where a small specialized model
is the core and every other module is deterministic engineering or tooling. This is
deliberate — anything that can be solved with code does not spend parameters.

```
                        ┌─────────────────────────────────────┐
 Claim / Question       │  1. DECOMPOSER                       │
 ──────────────────────▶│  claim → atomic verifiable facts     │
                        │  (VeriScore style)                   │
                        └──────────────┬──────────────────────┘
                                       │ atomic facts
                        ┌──────────────▼──────────────────────┐
                        │  2. MULTI-SOURCE RETRIEVER           │
                        │  web search, Wikipedia, papers,      │
                        │  structured data. Deduplicates and   │
                        │  groups by independent source        │
                        └──────────────┬──────────────────────┘
                                       │ (fact, evidence) pairs
                        ┌──────────────▼──────────────────────┐
                        │  3. VERIFIER CORE  ★the model★       │
                        │  <1B params, MiniCheck style:        │
                        │  does the evidence support the fact? │
                        │  → supports / refutes / inconclusive │
                        └──────────────┬──────────────────────┘
                                       │ per-pair judgments
                        ┌──────────────▼──────────────────────┐
                        │  4. COMPARATIVE-LOGIC AGGREGATOR     │
                        │  weighs source independence,         │
                        │  reliability, recency; detects       │
                        │  contradictions and cherry-picking   │
                        └──────────────┬──────────────────────┘
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 ▼                     ▼                     ▼
         SUPPORTED / REFUTED     CONFLICTING          NO EVIDENCE
         (+ traceable citations) (shows both           │
                                  sides + weights)     ▼
                        ┌─────────────────────────────────────┐
                        │  5. FRONTIER MODE                    │
                        │  produces a verification plan:       │
                        │  simulation (code), symbolic math,   │
                        │  or experiment design.               │
                        │  Never invents an answer.            │
                        └─────────────────────────────────────┘
```

## Module 1 — Decomposer

**What it does:** turns a complex claim into atomic verifiable facts, with
decontextualization (resolving pronouns, relative dates, ellipsis) so each fact
is self-contained.

**How:** in Phase 0, a small open LLM with a prompt (VeriScore/DnDScore style).
Later, distilled into our own <500M model. 2025 literature (VeriFastScore) shows
decomposition + verification can be fused into a single pass — a future optimization.

## Module 2 — Multi-source retriever

**What it does:** for each atomic fact, searches for evidence in as many sources as
possible and prepares it for the verifier. Sources live in a **registry**
(`FUENTES` in `retrieve.py`): adding one means writing a function
`(query, lang) -> list[Evidencia]` — all are queried **in parallel**, and an external
API going down never takes verification down with it.

**The category router (`router.py`):** the agent decides *where* to look based on the
fact's topic — it doesn't go to Wikipedia for a bug nor to Stack Overflow for a medical
claim. Two levels: keywords (deterministic, testable) and zero-shot with the NLI
verifier itself for ambiguous cases — the same comparative skill it uses to verify,
reused to classify. Each source declares its categories in the registry; universal
ones are always queried.

**Full-page evidence:** truncated search snippets repeat headlines; an article's
verdict lives in its body (measured on AVeriTeC: judging snippets was the system's
bottleneck). Top web results are downloaded in full (extraction with trafilatura)
and split into relevance-ranked passages.

**Current families (10, all with free keyless APIs):**

| Source | Categories | Provides |
|---|---|---|
| Wikipedia (claim's language) | all | encyclopedia, relevance-ranked passages |
| Multilingual Wikipedia (langlinks) | all | the same article in other languages |
| Open web (DuckDuckGo) | all | full pages + snippets |
| **Debunks** (targeted search) | all | fact-checker articles, full text |
| Wikinews | news, general | collaborative journalism |
| Stack Exchange | programming | technical Q&A |
| Semantic Scholar | science, medicine, programming | academic abstracts |
| OpenAlex | science, medicine, programming | academic abstracts |
| arXiv | science, programming | scientific preprints |
| Europe PMC | medicine, science | biomedical literature |

Future candidates: PubMed, GDELT (world press headlines), Wikidata (structured facts),
official language/framework documentation, and optional keyed APIs.

**Key design point:** the value of evidence depends on source **independence**.
A hundred sites copying the same press release count as *one* source. The retriever:

- groups documents by probable origin (similarity clustering + domain analysis),
- records metadata: date, source type (primary/secondary/tertiary), domain, language,
- actively searches for evidence **against**, not just for (anti-confirmation bias).

**Information is free regardless of language:** the retriever is not limited to the
claim's language. Via Wikipedia's interlanguage links it fetches the same article in
other languages (English, Chinese, Russian, Arabic…) **without a translation model**,
and the multilingual verifier judges cross-language pairs directly (claim in Spanish,
evidence in German). Independence bonus: each Wikipedia edition is a distinct editorial
community — more voices for the comparative logic. Current limitation: passages in
languages that share no vocabulary with the query are taken from the article's lead
(no cross-lingual lexical ranking); the natural upgrade is multilingual embeddings.

**No training:** this module is pure engineering (search APIs, clustering embeddings,
rules). Zero parameters spent.

## Module 3 — Verifier core (the specialized model)

**The heart of the project.** A small model that takes `(atomic fact, evidence
passage)` and outputs: **supports / refutes / inconclusive**, with a calibrated
probability.

**Why it can be small:** it doesn't need to know whether the claim is true — only
whether *this text* supports it. That is textual inference (NLI), a closed skill that
fits in hundreds of millions of parameters. MiniCheck proved it: 770M ≈ GPT-4 at this
task.

**Training recipe (validated by MiniCheck):**
1. Generate synthetic data with a strong LLM: (fact, evidence) pairs with *challenging*
   factual errors — subtle ones that require composing information across sentences.
2. Fine-tune a small base model on that data + public datasets (ANLI, FEVER,
   LLM-AggreFact).
3. Post-hoc calibration (temperature scaling) so the probabilities mean something.

**Success metric:** match or beat MiniCheck-FT5 on the LLM-AggreFact benchmark.

## Module 4 — Comparative-logic aggregator

**What it does:** combines per-pair judgments into a verdict per fact, and facts into
the verdict for the full claim. This is where the "comparative logic" that names the
project lives.

**It is explicit math, not a neural network** (transparent and auditable). Every rule
was born from a measured failure:

- **one domain, one voice**: a hundred copies weigh no more than one source, and if
  the same site has passages on both sides (a fact-check narrates the myth before
  debunking it), it votes only with its strongest signal,
- **reliability priors**: fact-checkers 8x, encyclopedias/academia 2.5x, official
  bodies 2x — a professional debunk outweighs an unknown domain's assertion,
- **echo is not evidence**: repeating the claim almost word for word is not supporting
  it; refuting requires content of its own,
- **the attribution trap**: a passage that "supports" while carrying debunk markers
  ("purportedly", "hoax", "fact check"…) is almost always an article *describing* the
  myth, not asserting it — its support is discounted,
- staleness penalty on volatile topics, not on stable facts (pending),
- *cherry-picking* detection: technically true claims that mislead by omission
  (verdict class taken from AVeriTeC),
- output in 4 classes: **supported / refuted / conflicting evidence / not enough
  evidence**, always with the citations that justify the verdict.

## Module 5 — Frontier mode ("the human factor")

When the aggregator returns *not enough evidence*, AIDAM does what a scientist does:
it doesn't opine — it designs how to find out.

**Strategy hierarchy (from automatable to propositional):**
1. **Computation/simulation:** if the fact is computable (math, simple physics,
   statistics over public data), generate and run code — the output IS the evidence.
2. **Deduction from verified facts:** chain already-supported facts through explicit
   logical rules ("A implies B, A is supported ⇒ B has deductive support").
3. **Experiment design:** if not computable, produce a protocol: what data would be
   needed, what to measure, what result would confirm/refute. Honest output: "not
   verifiable today; this is how it would be verified".

**Design honesty:** level 3 does not compete with human scientists. It is a structured
template + a reasoning LLM used as a tool. The value is that the system *never* crosses
from "there is no evidence" to "I'll make it up".

## The verified-generation loop (Modules 6–7)

Verification is not just the product: it is the **engine that makes generation cheap**.
The principle (validated by the test-time compute literature, ICLR 2025): verifying is
easier than generating, so a strong verifier + a small generator + N attempts performs
like a giant generator — at a fraction of the cost. At matched compute budgets, this
strategy beats models 14x larger.

```
              ┌────────────────────────────────────────────┐
   Task  ────▶│  6. SPECIALIZED GENERATORS (SLMs)          │
              │  code:  Qwen3-Coder (Q4, consumer GPU)     │
              │  text:  small open SLM                     │──┐
              │  image: FLUX.2 Klein 4B / Z-Image Turbo    │  │ N candidates
              └────────────────────────────────────────────┘  │
                                                              ▼
              ┌────────────────────────────────────────────┐
              │  7. GENERATION VERIFIER                     │
              │  code:  run it. tests, benchmark,           │
              │         profiling → OBJECTIVE score         │
              │  text:  Module 3 (factually supported?)     │
              │         + docs verification                 │
              │  image: prompt adherence (automatic         │
              │         score) — the weakest                │
              └──────────────────┬─────────────────────────┘
                                 │
                    only the candidate that passes survives;
                    if none passes → retry with the failure
                    feedback, or escalate and say so
```

**Verifiability hierarchy** (decides how much the system can promise per domain):

1. **Code — perfect verification.** It compiles or it doesn't; tests pass or they
   don't; the benchmark yields milliseconds and the profiler yields memory. "Optimized
   code" is a measurement, not an opinion. Here AIDAM can beat large assistants on
   quality-per-dollar — and it is exactly how Qwen3-Coder-Next was trained: ~800k
   tasks where ground truth is *a test passing inside a Docker container*.
2. **Facts/text — strong verification.** Module 3 scores every generated claim against
   sources. Writing stays "anchored": the system cannot assert what its own verifier
   does not support.
3. **Images — weak verification.** Prompt adherence and artifacts can be measured;
   "beauty" cannot. Here AIDAM *orchestrates* existing distilled open models
   (FLUX.2 Klein 4B fits in ~8 GB of VRAM; Z-Image Turbo 6B generates in seconds on a
   16 GB card) — we do not train image models: different budget, different science.

**Design rule (NVIDIA paper, 2025):** small specialized models for every repetitive
agent task; a large model only when a planning step truly demands it — with the goal
of distilling it later. SLMs are 10–30x cheaper to serve and more reliable at
structured outputs, which is exactly what a compound system needs.

**Why this is cheaper:** the cost of large assistants is generating *everything* with
the most expensive model. AIDAM inverts the equation: cheap generators that err more,
plus a cheap strong verifier that filters — total cost per *correct* result drops even
with retries, because verifying costs cents compared to frontier-model generation.

## Model selection (cross-cutting)

Always the best, most current open model for each role, with no brand loyalty: open
weights, permissive license (MIT/Apache), no censorship. **The system answers every
claim** — political, violent or uncomfortable — with a verdict and evidence: those are
precisely the claims that carry the most misinformation and need verification the most.
Information is delivered in its purest state; the system's only filter is evidence.
An assistant model that refuses topics gets replaced (`AIDAM_MODELO_PREGUNTAS` accepts
any GGUF), and the verdict path (NLI verifier + explicit aggregation) does not know how
to refuse.

## Efficiency (cross-cutting)

**Training:**
- Liger Kernel (fused Triton kernels: RMSNorm, RoPE, SwiGLU, FusedLinearCrossEntropy)
  → ~60% less memory, ~20% more throughput. Directly applicable on a consumer GPU.
- FlashAttention (whichever version your GPU supports; FA-3 requires Hopper).
- `torch.compile` + bf16 + gradient checkpointing as the baseline.
- LoRA/QLoRA to iterate cheaply; full fine-tuning only for the final version.

**Inference:**
- First line: ONNX Runtime for the verifier on CPU (identical accuracy, 1.4x faster
  than PyTorch CPU, ~50 MB runtime instead of ~3 GB).
- Measured warning: dynamic INT8 **breaks** DeBERTa-v3 (88% → 51%; its activation
  outliers don't tolerate activation quantization). The recipe that works is
  **weight-only**: block-wise int4 MatMuls + int8 embeddings, activations in fp32 —
  the mini model is 319 MB at 86.1% accuracy, 2x faster on CPU.
- BitNet experiment: fine-tuning `microsoft/bitnet-b1.58-2B-4T` for the verification
  task, deployed with `bitnet.cpp` on pure CPU. See [ROADMAP.md](ROADMAP.md) for the
  real limits of 1-bit.

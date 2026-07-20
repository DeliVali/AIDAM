# Multi-SLM architecture: expert cartridges, surgical memory, the flywheel

**Status: target architecture — declared before implementation.** House rule:
gates are pre-registered before any numbers exist (§9), and no component is
promoted by design — each ships behind its gate or not at all. This document
translates the owner's Multi-SLM specification (2026-07, v2) into AIDAM's
terms: what already exists, what changes, and what must be measured first.

Companion docs: [ARCHITECTURE.md](ARCHITECTURE.md) (the verification core this
builds on), [AGENT.md](AGENT.md) (task mode, fine-tuning program, resource
program), [ROADMAP.md](ROADMAP.md) (measured history, including rejections).

---

## 1. Design laws (inherited from the current system, non-negotiable)

1. **State lives in the orchestrator, never in a model.** The ReAct scratchpad
   (thoughts, actions, observations) is Python-side data (`razonador.py`);
   every step re-renders the full prompt. Models are stateless per call and
   therefore disposable. Consequence: *expert swap, interruption, resume and
   escalation are the same primitive* — kill a worker, spawn a worker, hand it
   the scratchpad.
2. **A cartridge is a process, not a pointer.** Killing a process returns 100%
   of its memory to the OS, guaranteed by the kernel; in-process
   `del + gc.collect() + malloc_trim` is best-effort and glibc-dependent. The
   isolated `llm_worker.py` process (born from a *measured* llama.cpp/PyTorch
   heap corruption) is already the cartridge mechanism — generalized here to
   N model files. `mmap` (the default) means the kernel page cache survives
   the kill: reloading a recently-used GGUF is nearly free on NVMe.
3. **Code decides; models propose.** Routing, swap triggers, budgets,
   termination, and promotion are deterministic code. An expert never chooses
   its own replacement (a model that can delegate learns to give up).
4. **Separation of powers.** No model evaluates its own work. Verdicts come
   only from the NLI verifier + auditable aggregation (measured:
   LLM-as-sole-judge 24% vs 58%); code quality comes from execution in the
   sandbox, never from opinion.
5. **Anything solvable with code does not spend parameters.** A model enters
   the pipeline only where deterministic engineering measurably cannot do the
   job.

---

## 2. High-level diagram (the whole flow)

```text
                              ┌───────────────────────────────────────┐
            boot, once        │  0. HAL — HARDWARE AUDIT              │
            ─────────────────►│  GPU/VRAM · RAM · AVX level · cores   │
                              │  · SSD?  →  picks a MEASURED profile  │
                              └────────────────┬──────────────────────┘
                                               │ env knobs: quant level, n_ctx,
                                               │ threads, gpu_layers, kv-cache,
                                               │ flash-attn  (llm_worker vars)
                                               ▼
     user task ──────►┌───────────────────────────────────────┐
                      │  1. WORK QUEUE  (SQLite, resumable)   │  new work waits here;
                      └────────────────┬──────────────────────┘  tasks never interrupt
                                       ▼                          each other mid-step
                      ┌───────────────────────────────────────┐
                      │  2. ORCHESTRATOR  (pure code)         │  owns ALL state:
                      │     scratchpad · budgets · audit log  │  scratchpad, budgets,
                      └────────────────┬──────────────────────┘  audit. Models are
                                       ▼                          stateless, disposable.
                      ┌───────────────────────────────────────┐
                      │  3. CONTEXT — REPO MAP (AST) + RAG    │  tree-sitter skeleton
                      └────────────────┬──────────────────────┘  of the workspace,
                                       ▼                          < 500 tokens, cached
                      ┌───────────────────────────────────────┐
                      │  4. ROUTER — keywords → resident NLI  │  picks the specialty;
                      └────────────────┬──────────────────────┘  zero extra RAM
                                       ▼
                      ┌───────────────────────────────────────┐
                      │  5. EXPERT CARTRIDGE (worker process) │  ONE expert in memory
                      │     science/math · facts · code       │  at a time; runs ReAct
                      │     · generalist 8B (escalation)      │  steps; killed after
                      └────────────────┬──────────────────────┘  the task (RAM → base)
                                       │ draft answer / line-based patch
                                       ▼
                      ┌───────────────────────────────────────┐
                      │  6. VERIFICATION LAYER                │  separation of powers:
                      │   a) fact-checker 280M + aggregation  │  no model judges its
                      │      → «Recopilación de Hechos»       │  own work; verdicts
                      │   b) QA adversary: edge values, chaos │  never come from the
                      │      SymPy/NumPy probes, consistency  │  author expert
                      │   c) sandbox: run · measure · Ruff    │
                      │      lint · unified diff vs disk      │
                      └───────┬──────────────────────┬────────┘
                        fail  │                      │ pass
                              ▼                      ▼
                  ┌────────────────────┐   ┌────────────────────────┐
                  │  7. REPAIR LOOP    │   │  8. DELIVER            │
                  │  reload ONLY the   │   │  apply patch / answer  │
                  │  expert the error  │   │  with citations; the   │
                  │  class calls for   │   │  grounding gate marks  │
                  │  (swap rules §5)   │   │  «sin verificar»       │
                  └─────────┬──────────┘   └───────────┬────────────┘
                            └──► back to 5             ▼
                      ┌───────────────────────────────────────┐
                      │  9. DATA FLYWHEEL  (opt-in telemetry) │  TEXT_COPIED ·
                      └────────────────┬──────────────────────┘  PATCH_ACCEPTED ·
                                       ▼                          SESSION_PERSISTED
                          [ local JSONL trace store ]             → JSONL trace
                                       ▼
                      ┌───────────────────────────────────────┐
                      │ 10. ASYNC RETRAINER  (≤ 5 h projected,│  QLoRA in a nice-15
                      │     background process, gated swap)   │  child process; the
                      └───────────────────────────────────────┘  new adapter replaces
                                                                  the old ONLY if it
                                                                  passes GATE FT
```

---

## 3. Low-level diagram (cartridge lifecycle and memory)

A **cartridge** is one `llm_worker` process: one GGUF file, JSON lines over
stdin/stdout, HAL knobs injected as environment variables. The orchestrator
never links llama.cpp into its own process.

```text
                         router picks expert E
                                  │
                  ┌───────────────▼───────────────────┐
                  │ SPAWN worker(E)                   │  subprocess:
                  │  · env = model path + HAL knobs   │  python -m aidam.llm_worker
                  │  · mmap GGUF (page cache warm ⇒   │
                  │    a recent reload is ≈ free)     │
                  └───────────────┬───────────────────┘
                                  ▼
                ┌─────────────────────────────────────┐
        ┌──────►│ STEP (ReAct)                        │   the worker holds NO
        │       │  render full scratchpad → prompt    │   task state: killing it
        │       │  → completion → ONE action → run    │   at any step boundary
        │       │  tool → observation appended        │   loses nothing
        │       │  (orchestrator side)                │
        │       └───────────────┬─────────────────────┘
        │                       │
        │        swap rule fires?  (§5: error class ≠ specialty
        │        AND hysteresis satisfied AND swaps < max
        │        AND global step budget not exhausted)
        │                       │
        │          no           │ yes
        └───────────────────────┤
                                ▼
                  ┌───────────────────────────────────┐
                  │ KILL worker(E)                    │  process death: RAM back
                  │                                   │  to the OS, guaranteed —
                  └───────────────┬───────────────────┘  no gc, no malloc_trim
                                  ▼
                  SPAWN worker(E') and hand it the SAME scratchpad
                  (swap ≡ interrupt ≡ resume ≡ escalate: one primitive;
                   cost = model load < 1 s on NVMe + re-prefill of the
                   scratchpad — the dominant cost on CPU profiles)

   task ends (responder emitted, or budget exhausted) ──►
                  ┌───────────────────────────────────┐
                  │ peek queue: is the next pending   │
                  │ task the SAME specialty?          │
                  │  · yes → KEEP-WARM (short TTL,    │
                  │    then kill on idle)             │
                  │  · no  → KILL now, spawn E'' for  │
                  │    the next task                  │
                  │  (profile C: strictly serial —    │
                  │   never two experts in RAM;       │
                  │   profiles A/B may overlap load)  │
                  └───────────────────────────────────┘
```

RAM over time (profile C illustration: CPU-only 8 GB; expert 1.5B Q4 ≈ 1.1 GB;
base = app + resident NLI-mini ≈ 0.45 GB):

```text
 GB
 1.6 ┤           ┌───────────────────┐          ┌────────────────────┐
     │           │   expert: coder   │          │  expert: debugger  │
     │           │   (ReAct steps)   │          │   (repair loop)    │
 0.45┤═══════════╛                   ╘══════════╛                    ╘══════════
     │  route      generate + verify   swap gap    repair + verify     idle
     └────────────────────────────────────────────────────────────────────► t
       (router + resident NLI: no extra load)         (keep-warm TTL expiry)
```

The base line is not 0 MB: the 280M NLI verifier stays **resident** because it
is the consultant the whole pipeline calls many times per task (router
zero-shot, grounding gate per sentence, fact-checking). At 319 MB (onnx-mini)
residency is cheaper than reload-per-consultation; on profile C a
spawn-per-use variant may be measured if the RSS budget demands it.

---

## 4. Component map: spec → what exists today → what to build

| # | Spec component | Exists today | Delta to build |
|---|---|---|---|
| 0 | HAL, hardware audit at boot | Resource program: 3 **measured** profiles (`dev 12GB GPU`, `GPU 4GB` hybrid, `CPU 8GB RAM`) with exact env vars (`evaluation/perfil_recursos.py`, AGENT.md §resource program); selection is manual | Auto-detection at startup (VRAM, RAM, AVX level, physical cores, SSD) that selects among the measured profiles — pure code over existing infrastructure |
| 1 | Micro-router (0.5B GGUF) | `router.py`: deterministic keywords + zero-shot with the resident NLI verifier — zero extra RAM, testable | Extend categories to the expert pool (science/math, facts, code). A dedicated 0.5B GGUF router is an **experiment behind GATE ROUTE**, not a default: it must beat the code+NLI router to justify +300 MB and a load cycle |
| 2 | Expert pool (1.5B/3B fine-tuned SLMs) | ONE generalist reasoner (8B GGUF Q4) in an isolated worker; fine-tuning pipeline (`training/finetune_razonador.py`, GATE FT) exists; R3 already plans distilling to Qwen3-4B/1.7B students | Distill **per-domain** students instead of (or besides) one generalist student; each expert behind GATE EXPERT. Cautionary measured precedent: the R1 adapter was **rejected** (+15.3 parse validity, but T1 and consultation fell) |
| 3 | Fact-checker 300M + «Recopilación de Hechos» | **The core of the project**: 280M mDeBERTa NLI + auditable aggregation + grounding gate (`revisar_respuesta`) marking «sin verificar» | Wiring only: the "fact compilation" structure = the existing (fact, evidence, verdict, citation) rows, passed to the repair loop as an observation |
| 4 | QA expert / stress adversary | Sandbox racing for code (`agente/codigo.py`): bubblewrap, correctness fingerprints, timed survivors, CPU pinning | Add: edge-value/chaos injection (negative, zero, inf, empty), Ruff lint stage, SymPy/NumPy numeric probes for math claims, cross-consistency checks for factual answers. Adversary prompts/models must differ from the author expert (law 4) |
| 5 | ReAct repair loop | `razonador.py`: budgets, loop-breaker, retry, audit, compaction | Error-class routing (observation classifier → which expert repairs), swap governance (§5) |
| 6 | Data flywheel (implicit RLHF) | Audit log with content hashes (`agente/auditoria.py`); nothing captures user acceptance | New, **opt-in**: TEXT_COPIED / PATCH_ACCEPTED / SESSION_PERSISTED events; successful validated flows assembled as JSONL traces — exactly the "own curated traces" that round **R2** of the fine-tuning program already calls for. Local only; never leaves the machine |
| 7 | Async retrainer (≤ 5 h, background) | Training scripts exist (manual, GPU); adapter loading at inference exists (`AIDAM_MIMO_LORA` in `llm_worker.py`) | New: synthetic forward/backward micro-benchmark → projected duration for 100 samples × 3 epochs; ≤ 5 h → run QLoRA in a `nice 15` / `IDLE_PRIORITY_CLASS` child process; > 5 h → disable, revert the flag, offer cloud export. Finished adapters are **not** hot-swapped blindly: §5-D |
| — | Repo map / AST context (< 500 tokens) | Nothing equivalent (tools read files on demand) | New module: tree-sitter skeleton of the workspace (files, signatures, imports), cached on disk, invalidated by mtime; prepended to task prompts |

---

## 5. Governance rules (all enforced by code, declared before implementation)

**A. Swap triggers.** Re-routing mid-task is decided by deterministic rules on
the *observation*, mirroring router level 1: a stack trace / compile error /
test failure routes the next iteration to the debugger-class expert; a factual
contradiction routes to the facts expert; nothing routes on model request.

**B. Hysteresis against ping-pong.** Minimum N consecutive steps with the same
expert before another swap is allowed, and a maximum of M swaps per task
(constants declared off-test before any measurement, house rule). Precedent:
the step-level loop-breaker in `razonador.py`, born from a measured
temperature-0 five-times re-read.

**C. One global budget.** `MAX_PASOS` counts steps of the **task**, never per
expert — otherwise swapping becomes a budget bypass. When the pool is
exhausted, the escalation ladder ends at the generalist 8B; if that also
fails, the task terminates *visibly* with the deterministic summary
(`terminado_por="presupuesto"`), never with a fabricated answer.

**D. Retraining promotion is gated, never automatic.** The background worker's
finished adapter is evaluated on the GATE FT metrics (first-parse validity,
T1 pass rate, no regression on `questions.py` roles) **before** the pointer
swap; a miss is a documented rejection like any other. "Hot-swap on finish"
from the spec becomes "hot-swap on pass".

**E. Memory discipline per profile.** Profile C: strictly serial swaps (kill
before spawn — never two experts in RAM). Profiles A/B: the next cartridge may
be loaded while the current one emits its final step. Unload boundary is
**between tasks and at swap points, never between ReAct steps** — the same
model is called many times consecutively, and re-prefill of a ~14k-char
scratchpad is the dominant swap cost on CPU.

**F. Interruption = the same primitive.** An urgent task does not abort a
process mid-step: at the next step boundary the current task's scratchpad is
persisted into the queue row (`carga` is arbitrary JSON in `cola.py`), the
task is re-queued, the worker killed. Resuming later is literally the swap
mechanism: spawn a worker, hand it the saved scratchpad.

---

## 6. HAL — hardware abstraction layer

At boot, once: audit VRAM (CUDA/ROCm probe), total RAM, CPU flags (AVX2 /
AVX512), physical core count, and disk type; then select a profile and export
the corresponding `llm_worker` knobs. The profiles are **the three already
measured** by the resource program — the HAL adds detection, not new numbers:

| | Profile A | Profile B | Profile C |
|---|---|---|---|
| Detected | dedicated GPU ≥ 12 GB | iGPU/APU or small GPU + ≥ 16 GB RAM | CPU-only / ≤ 8 GB RAM |
| Maps to measured profile | `dev 12GB GPU` | `GPU 4GB` (hybrid offload) | `CPU 8GB RAM` |
| Expert quantization | FP16 / AWQ candidates | GGUF Q4_K_M | GGUF Q4_0 / Q3_K |
| Cartridge destination | VRAM (`n_gpu_layers=-1`) | RAM + partial offload | RAM (`n_gpu_layers=0`) |
| Context / threads / kv-cache | per measured sweep | per measured sweep | per measured sweep |

Context sizes, thread counts and kv-cache quantization come from
`perfil_recursos.py` sweeps under the pre-set sweet-spot criterion (GATE
PERF), not from a static table: any number in the spec's matrix is a starting
hypothesis for the sweep, not a shipped constant.

---

## 7. Verification layer — separation of powers

Three independent judges, none of them the author:

1. **Fact-checker (semantic).** The resident 280M NLI verifier + explicit
   aggregation contrasts names, dates, method signatures and constants against
   retrieved evidence and the RAG; output is the fact compilation the repair
   loop consumes. Verdicts are final — the author expert quotes them, never
   overrides them.
2. **QA adversary (behavioral).** Domain-dependent stress: edge values into
   generated formulas via isolated SymPy/NumPy scripts; logical
   cross-consistency and anachronism checks for factual/history answers;
   linters (Ruff) and test execution for code — all inside the bubblewrap
   sandbox (no network, read-only FS, `.git` remounted read-only, wall-clock
   timeout).
3. **Physical comparator (mechanical).** Unified diff against disk shown on
   the permission card before any write; candidate implementations race in the
   sandbox and are disqualified by result fingerprint before speed counts.

A failure from any judge becomes an `Observación:` injected into the repair
loop — literal tool output between delimiters, data, never instructions
(measured prompt-injection surface, 2026-07-17).

---

## 8. Data flywheel and async retraining

**Capture (opt-in, local, discreet).** A validated flow that then triggers
TEXT_COPIED, PATCH_ACCEPTED or SESSION_PERSISTED is assembled as one JSONL
trace: task, scratchpad, final answer, verification results. This is the
collection mechanism for round R2's "own curated traces" (AGENT.md). Nothing
is uploaded anywhere; the store lives under the per-user data directory
(`plataforma.py`).

**Feasibility check (the 5-hour rule).** Before any local training run: a
synthetic matrix micro-benchmark (forward/backward tensors emulating a 1.5B/3B
QLoRA pass) projects the duration of 100 samples × 3 epochs. ≤ 5 h: proceed.
\> 5 h: block local training, revert `ENABLE_DYNAMIC_TRAINING` to false,
notify, and offer exporting the JSONL for free cloud training (Colab-class).

**Isolation.** Training runs in a detached child process at `nice 15`
(`IDLE_PRIORITY_CLASS` on Windows), never sharing the event loop or UI
thread; progress goes to a silent log. The kernel scheduler yields instantly
to interactive work.

**Promotion.** On completion the adapter is benchmarked (GATE FT metrics);
only a pass moves the `AIDAM_MIMO_LORA` pointer for the next cartridge spawn.
The swap itself is trivial because cartridges reload per task anyway.

---

## 9. Pre-registered gates (declared now, all unmeasured)

House rule: a failed gate blocks promotion regardless of the work invested.

- **GATE HAL.** The auto-selected profile must match the best manually-chosen
  profile on the measurement harness for that hardware class; misdetection
  fails closed to profile C (never OOM by optimism).
- **GATE SWAP (cartridge lifecycle).** Promotion requires: T1 pass rate not
  below the resident-worker baseline; idle RSS at the profile's base target;
  added latency per swap within the profile budget (< 1 s load on NVMe;
  re-prefill measured and reported per profile). Measured on the same 20-task
  suite as GATE T1.
- **GATE EXPERT (one per specialist).** A domain expert replaces the
  generalist for its category only if it beats the 8B on that category's task
  slice AND causes no regression on the global suite. The R1 adapter
  rejection is the template for how a miss is documented.
- **GATE ROUTE.** A dedicated router model ships only if routing accuracy
  over a labeled task set beats keywords+NLI by a pre-set margin at
  acceptable RAM/latency cost.
- **GATE QA.** The adversary stage must catch a pre-built set of known-bad
  patches/answers (seeded faults) with a false-positive rate that does not
  block more than a pre-set fraction of known-good ones.
- **GATE FLY.** Flywheel-collected data must train an adapter that passes the
  full promotion battery of §12.1 (domain skill ≥ incumbent, frozen regression
  set within ε, anti-hallucination non-regression, calibration, canary); until
  then the flywheel only collects (capture can ship before training does).
- **GATE EXPERT (per knowledge domain).** A knowledge domain (legal, medical,
  biology, physics/chem, history, current-events) gets its own fine-tuned
  cartridge instead of the shared grounded-reasoner only if it wins on that
  domain's benchmark suite (§11.2) with no cross-domain regression — otherwise
  it stays on the shared cartridge (0 extra models). See §11.3.

---

## 10. Deliberate deviations from the spec, and why

1. **Process kill instead of `del + gc + malloc_trim`.** The spec's context
   manager frees memory inside one process; AIDAM already learned (measured
   heap corruption, `llm_worker.py` docstring) that llama.cpp belongs in its
   own process. Process death is the only reclamation the OS guarantees, and
   it also gives crash isolation for free. The spec's `CartuchoModeloLlame`
   maps to "spawn worker / kill worker".
2. **Unload between tasks and at swaps — not after every micro-step.** The
   spec unloads after each stage; but within a ReAct loop the same expert is
   called many times, and each reload pays scratchpad re-prefill (the real
   cost on CPU, more than the NVMe read). The spec's "RAM → 0" invariant is
   preserved at task boundaries and idle (keep-warm TTL expiry).
3. **The verifier stays resident.** The 280M consultant is called many times
   per task (router, grounding gate, fact-checking); at 319 MB, residency
   beats reload-per-call. Profile C may measure a spawn-per-use variant.
4. **The router is code first.** Keywords + resident-NLI zero-shot cost zero
   extra RAM and are testable without a model. A 0.5B router model is an
   experiment (GATE ROUTE), not the default.
5. **"Hot-swap on finish" becomes "hot-swap on pass".** A freshly trained
   adapter is never promoted without passing GATE FT — the R1 rejection shows
   why: better parse validity and worse task completion can coexist.
6. **The HAL matrix numbers are hypotheses, not constants.** Context sizes and
   thread counts ship from measured sweeps (GATE PERF), seeded by the spec's
   table.

---

## 11. The expert pool: how many, which base models, which benchmarks

We compete against much larger models, sometimes by *building on* smaller open
ones. The winning move is not to match their parameter count — it is to make
size irrelevant on the axis that matters: **a small model that reasons and
retrieves, gated by the fact-checker core, beats a large model that memorizes
and hallucinates.** Two consequences shape the whole pool:

- **Experts are picked/trained for SKILL, not for KNOWLEDGE.** Cramming domain
  facts into a 1.5–3B model is exactly what produces confident hallucination.
  Knowledge lives in retrieval (the 22 source families) and every factual
  sentence is gated by the resident 280M verifier. So a "legal expert" is not a
  model that has memorized case law — it is a model that reasons well over
  *retrieved* statutes and lets the verifier veto unsupported citations.
- **This collapses the model count.** Only skills that must live in weights
  (code generation, symbolic math, tool-calling) need a dedicated fine-tune.
  Knowledge domains (legal, medical, biology, physics/chem, history, current
  events) can share ONE grounded-reasoner cartridge, differentiated by the
  router's domain (which retrieval sources, which QA adversary), until a gate
  proves a domain earns its own model.

### 11.1 Why "saturated" benchmarks still discriminate for us

Several 2026 leaderboards are saturated **at the frontier** — MATH-500
(97–99%), AIME-2025 (98%+), MMLU, and GPQA-Diamond is near its asymptote
([Epoch AI](https://epoch.ai/benchmarks/gpqa-diamond)). That does **not** make
them useless here: a 1.5–4B model sits far below the ceiling, so the same
benchmark that no longer separates two frontier models cleanly separates two of
*our* candidates. Rule: pick per-domain benchmarks where our size class still
has headroom; cite frontier-hard sets (FrontierMath, GPQA-Diamond, HLE) as
*ceilings we report*, never as promotion gates we must pass. Pinning discipline
from [BENCHMARKS.md](../evaluation/BENCHMARKS.md) applies to every number below:
pin the version and date, and a leaderboard figure is a *reference frame*, not
our score until we reproduce it locally.

### 11.2 The roster (design target)

Small open base models, current July 2026. Numbers are the base model's
published scores (size class in parentheses), the frame we start from before
any AIDAM fine-tune — not AIDAM results.

| Role | Router domain | Small base candidate (July 2026) | Public benchmark suite (pinned per run) | AIDAM-side referee | Kind |
|---|---|---|---|---|---|
| **Code / Dev** | `programacion` | Qwen2.5-Coder-3B-Instruct (1.5B on profile C) — HumanEval 84.1 / MBPP 80.5 / BigCodeBench 73.6 / LiveCodeBench 62.4 ([tech report](https://arxiv.org/html/2409.12186v3)) | HumanEval, MBPP, BigCodeBench, LiveCodeBench (contamination-resistant), SWE-bench (agentic) | **sandbox execution** (`codigo.py`) — perfect verification | Skill expert |
| **Math / Logic** | `matematicas` | Qwen2.5-Math-1.5B — beats DeepSeekMath-7B-Base on GSM8K/MATH/CMATH/GaoKao ([tech report](https://arxiv.org/pdf/2409.12122)) | GSM8K, MATH-500 (floor), AIME-2025, MMLU-STEM; FrontierMath as ceiling ([MindStudio](https://www.mindstudio.ai/blog/frontier-math-benchmark-open-research-problems-ai-reasoning)) | **SymPy/NumPy** probes (frontier mode + QA adversary) | Skill expert |
| **Reasoner / Agent** (ReAct driver, search-question generator) | cross-cutting | DeepSeek-R1-Qwen3-8B (current) → distilled Qwen3-4B / 1.7B (R3). Cf. xLAM-2-3b-fc-r BFCL 65.74 (v3, 04/2025) ([HF](https://huggingface.co/Salesforce/xLAM-2-3b-fc-r)) | **BFCL V4** (anchors: 8B ceiling ~46.7, frontier ~77.5), τ²-bench (pass^k), AVeriTeC-500, citation-support | verifier + per-step audit | Skill expert (exists) |
| **Legal** | `legal` (new) | grounded-reasoner cartridge + legal retrieval; dedicated fine-tune only on a gated win (Saul-class / Qwen3-4B) | LegalBench (162 tasks, 6 reasoning types), LexGLUE, CaseHOLD, LawBench, LexGenius, ContractNLI ([leaderboard](https://awesomeagents.ai/leaderboards/legal-llm-leaderboard/)) | official statutes/case-law retrieval + NLI veto on citations | Knowledge domain |
| **Medicine / Clinical** | `medicina` | grounded-reasoner + medical retrieval (openFDA, ClinicalTrials, Europe PMC) | MedQA (USMLE; July-2026 top 95.2%, avg 77.3 — [leaderboard](https://awesomeagents.ai/leaderboards/medical-llm-leaderboard/)), MedMCQA, PubMedQA, MMLU-Medical (6 tasks, 1089 q), HealthBench | retrieval + NLI (hallucination = harm here) | Knowledge domain |
| **Biology / Life sci** | `biologia` (new) | grounded-reasoner + Europe PMC / Semantic Scholar | GPQA-Diamond (biology subset), MMLU-Med (college biology, genetics), PubMedQA, MMLU-Pro biology | retrieval + NLI | Knowledge domain |
| **Physics / Chemistry** | `ciencia` | grounded-reasoner + computation | GPQA-Diamond (physics/chem; O1 phys 92.8 / chem 77.3 — chem still hard), MMLU-Pro sciences, SciFact (already run: 63.7%) | computation/simulation + NLI | Knowledge domain |
| **History / Humanities** | `historia` (new) | grounded-reasoner + Wikipedia family / Wikisource | MMLU-Pro humanities (history, philosophy, law), MMLU history subjects, EduArt (art history) | retrieval + NLI + **anachronism/consistency** QA check | Knowledge domain |
| **Current events / General** | `actualidad`, `general` | grounded-reasoner + GDELT / Wikinews | AVeriTeC-500 (real viral claims), citation-support, MMLU-Pro general | retrieval + NLI | Knowledge domain |
| **Router** (optional model) | — | 0.5B GGUF classifier | routing accuracy on a labeled task set vs keywords+NLI | — | Experiment (GATE ROUTE) |
| **Verifier CORE** (resident, never swapped) | all | mDeBERTa-v3 280M (319 MB onnx-mini) — exists | **LLM-AggreFact** (target MiniCheck-FT5 ~74–75), FEVER 77.7, SciFact 63.7, AVeriTeC 62.6 | *is* the referee | The core |

### 11.3 The estimate, stated honestly

- **Models that must exist in weights (skill):** 3 — Code, Math, Reasoner/Agent.
- **Resident core:** 1 — the 280M verifier (not swapped, not a topic expert).
- **Optional router model:** +1, only if GATE ROUTE beats keywords+NLI.
- **Knowledge domains (legal, medical, biology, physics/chem, history,
  current-events):** start as **0 new models** — one shared grounded-reasoner
  cartridge serves them, differentiated by router domain + retrieval sources +
  QA adversary. Each becomes its own fine-tuned expert **only** when GATE EXPERT
  shows the shared cartridge loses on that domain's benchmark suite above.

So: **~5 models to start (3 skill + 1 core + 1 router), a design ceiling near
8–10** if every knowledge domain earns a dedicated expert through its gate. The
per-domain benchmark suites are defined *now* regardless — they do double duty
as the router's ground truth and as GATE EXPERT's promotion bar. This keeps the
pool small (efficiency), keeps knowledge in retrieval (anti-hallucination), and
spends a fine-tune only where a measured gap justifies it (the R1-rejection
discipline).

---

## 12. Auto-training: benchmarks and failure prevention

The flywheel (§8) can retrain an expert on captured traces. Retraining a small
model on a narrow, self-generated, user-biased stream is a minefield; the
defense is that **no adapter is ever promoted without clearing a fixed
benchmark battery, and the core anti-hallucination metric can never regress.**

### 12.1 The promotion battery (every flywheel adapter runs all of it)

Reuses GATE FT + the external-benchmark program — no new harness invented:

1. **Domain-skill suite** — the expert's own public benchmarks from §11.2 (e.g.
   Code → HumanEval + MBPP + LiveCodeBench + sandbox pass rate). Must be **≥ the
   current adapter**, not merely ≥ base.
2. **Frozen cross-domain regression set (the forgetting probe)** — a pinned mix
   run before and after: T1 task suite + BFCL-subset + AVeriTeC-100 +
   LLM-AggreFact-subset. **No slice may drop beyond ε** (declared off-test).
   This is the catastrophic-forgetting tripwire.
3. **Anti-hallucination gate (non-negotiable, the core)** — the grounding-gate
   «sin verificar» rate, AVeriTeC verdict accuracy, and citation-support
   recall/precision must **not regress**. The fact-checker core is the product;
   an adapter that codes better but grounds worse is rejected.
4. **Calibration** — post-hoc ECE no worse than the incumbent (a flywheel that
   makes the model overconfident is a net loss even at equal accuracy).
5. **Canary before pointer swap** — the passing adapter runs on a shadow eval
   for the next N real tasks with output compared to the incumbent; the
   `AIDAM_MIMO_LORA` pointer moves only after the canary holds. The previous
   adapter is retained for **instant rollback**.

A miss is a documented rejection with numbers, exactly like the R1 adapter.

### 12.2 Failure-prevention matrix

| # | Failure mode | Why it bites a local flywheel | Prevention (declared, code-enforced) | Detection |
|---|---|---|---|---|
| 1 | **Catastrophic forgetting** | LoRA limits weight change but not functional drift; a narrow retrain erases unrelated skills ([OPLoRA](https://arxiv.org/pdf/2510.13003)) | Orthogonal-subspace LoRA (CLoRA/OPLoRA) + **replay buffer**: every retrain mixes a fixed fraction of held-out gold traces; small LR; early stop on val. EWC-style penalty on high-Fisher weights ([survey](https://brics-econ.org/preventing-catastrophic-forgetting-during-llm-fine-tuning-techniques-that-work)) | Battery step 2 (frozen regression set) |
| 2 | **Reward hacking of implicit signals** | TEXT_COPIED / PATCH_ACCEPTED are noisy proxies — a user copies a *wrong* answer; the model learns to be copyable, not correct | Capture **only flows that ALSO passed the verification layer** (fact-checker + sandbox): the label is "validated AND accepted", never "accepted". Cap per-session contribution; require example diversity | Skill suite + anti-halluc gate divergence |
| 3 | **Model-autophagy / feedback collapse** | Training on self-generated traces → mode collapse, distribution narrowing ("MAD") | **Never train purely on self-data**: cap the self-generated ratio per round; always mix external gold (public datasets, curated traces) | Diversity metrics on the trace store; regression set |
| 4 | **Data poisoning / prompt injection via traces** | Tool output in a trace carries adversarial text (a file that reads like instructions — the measured 2026-07-17 surface) | Traces store tool output as **data between delimiters**; a sanitize+filter gate strips/flags injected content; never train on flagged traces; content-hash dedup | Audit-log hashes; injected-pattern filter |
| 5 | **Overfitting to a recent narrow workload** | 100-sample bursts of one task type skew the model | 100×3-epoch cap + replay mixing + val early-stop; per-domain quota so one workload can't dominate a round | Battery step 1 vs step 2 gap |
| 6 | **Silent quality regression** | An adapter looks fine on aggregate but breaks a specific case | Gated promotion (never auto-swap) + canary shadow eval + retained rollback adapter | Canary divergence (battery step 5) |
| 7 | **Starving interactive work** | Background training steals CPU/RAM from the UI | `nice 15` / `IDLE_PRIORITY_CLASS` detached child; **≤ 5 h projected** or abort and offer cloud export; single job at a time; kill-switch | Feasibility micro-benchmark (§8) + scheduler |
| 8 | **Non-reproducibility** | A promoted adapter can't be re-derived or audited | Pin seed; log training-data content hash + row count; version the adapter alongside its full battery numbers in ROADMAP | ROADMAP entry required before promotion |

### 12.3 The two invariants that make it safe

- **The core cannot regress.** Battery step 3 gives the fact-checker a veto over
  its own training loop: any adapter that improves a skill at the cost of
  grounding fidelity is rejected. Anti-hallucination is the one axis with no
  trade-off budget.
- **Promotion is gated, never automatic.** The spec's "hot-swap on finish"
  becomes "hot-swap on pass, after canary, with rollback retained" — the
  cartridge model makes the swap itself trivial (next spawn picks up the new
  `AIDAM_MIMO_LORA`), so all the cost is in the gate, which is where it belongs.

---

## 13. CPU latency budget (the Profile-C survival problem)

The HAL (§6) picks a lighter model on weak hardware — necessary, but it only
touches **one** of the four factors of task latency. This is the mission's
number-one UX risk: for a user without resources, a correct answer that takes
minutes on a cold CPU loop is a failed product. On CPU, inference is
**memory-bandwidth-bound**, so the levers that win are the ones that move fewer
bytes per token and process fewer tokens overall — not raw compute.

```text
   task latency  =  (per-token cost) × (tokens per step) × (steps per task)
                     └── HAL picks the model; §13.1 ──┘   └── §13.3 ──┘
                  +  (re-prefill per step)
                     └────────── §13.2: the CPU killer ──────────┘
```

### 13.1 Per-token cost — the HAL's lever, plus kernel knobs

Already swept by the resource program (GATE PERF): GGUF quant level (Q4_0 /
Q3_K on Profile C), threads = physical cores − 1, KV-cache quantization, AVX2
kernels. Fewer bytes per weight ⇒ faster on a bandwidth-bound CPU. The R3
distilled 1.7–3B reasoner is the biggest lever here and is on the critical path
for Profile C — the 8B is too heavy for this class regardless of tuning.

**Longer-term, CPU-specific:** BitNet ternary (`bitnet.cpp`, ROADMAP Phase 5) —
~1.58 bits/weight is genuinely faster on pure CPU, but it is a **training
commitment** (QAT / fine-tune the published 2B4T), not a config knob.

### 13.2 Re-prefill — the highest-leverage new work

Today every ReAct step re-renders the full scratchpad and the model re-prefills
all of it. On CPU that dominates. But the prefix is nearly stable step-to-step:
system + task + earlier turns are identical; only the newest observation is new.

**Prefix KV-cache reuse:** cache the KV of the stable prefix and prefill only
the new tokens — a ~14k-token re-prefill collapses to a few hundred. This is the
single most important CPU optimization for a ReAct loop.

**The design tension (non-obvious):** the scratchpad **compaction** in
`razonador.py` (folding old turns to fit the char budget) *rewrites the prefix
mid-conversation*, which **invalidates the cache**. On Profile C, prefer
**append-only** (no compaction; spend memory, keep n_ctx small) to preserve the
cached prefix — on a bandwidth-bound CPU that trade (memory for prefill) is the
right one. Measure both under GATE PERF: compaction saves context but may cost
more wall-clock than it saves.

### 13.3 Tokens per step and steps per task — do less with the LLM

**Grammar-constrained decoding (GBNF).** The measured failure — the model plans
the whole sequence, rambles past the token cap, executes an imagined step — is
pure wasted CPU. llama.cpp's native GBNF grammars can force the output to be
*only* a valid action JSON object: the model physically cannot spend 500 tokens
thinking aloud. Double win — fewer tokens per step **and** fewer bad steps
(malformed actions that today trigger the retry/loop-breaker paths). Attacks
latency and reliability at once, which is exactly Profile C's triple penalty.

**Route work out of the loop (house doctrine: code doesn't spend parameters).**
The fastest step is the one that never runs. File ops, category routing, and —
critically — claim verification go straight to their deterministic path or the
resident verifier, never through a ReAct step. Each thing removed from the loop
deletes N tokens × steps.

**Profile modulates agency, not just the model.** When the HAL detects Profile
C it should also prefer short flows and the verify-first path: a pure claim
needs *zero* ReAct steps — it runs on the 319 MB verifier alone. The humble user
gets something fast and truthful instead of a full agent that is slow and less
reliable. Agency is a HAL-selected dial, parallel to model weight.

**Prevent the bad step, don't just repair it.** The loop-breaker and corrective
retry already in `razonador.py` are damage control; a grammar-constrained
(or fine-tuned) model fails less up front, so fewer steps happen at all.

### 13.4 Already wired — keep it on for Profile C

- **Speculative decoding via prompt-lookup** (`AIDAM_MIMO_BORRADOR=lookup`):
  a natural fit because answers re-quote observations verbatim, so the draft
  hits for free. Confirm it defaults on for Profile C.
- Observation truncation (`_MAX_OBSERVACION`), think-block stripping from the
  scratchpad, resident (not spawn-per-step) worker, terse-thinking prompts.

### 13.5 Perceived latency — near-free, large for the mission

**Streaming.** Showing tokens as they generate, and the live
thought→action→observation trace (`progreso`/`avisar` already exists), turns
"30 s frozen" into "30 s watching it work". On a slow machine, perceived speed
is UX survival — the first thing to guarantee works on Profile C.

### 13.6 Priority order and the discipline

1. **Prefix KV-cache reuse** (§13.2) — the biggest hit; attacks re-prefill.
2. **Grammar-constrained JSON decoding** (§13.3) — kills rambling and bad steps.
3. **Profile-modulated agency + route-to-code** (§13.3) — fewer LLM steps.
4. **Confirm speculative decoding + streaming** on Profile C (§13.4–13.5).

The first three need no better model — they are engineering over what already
exists, which is exactly what the low-resource mission needs. House rule holds:
each is a **hypothesis until `evaluation/perfil_recursos.py` measures it under
GATE PERF**. Prefix-cache and GBNF *should* win big on CPU, but the
compaction-vs-cache trade in particular can surprise — measure before promoting.

- **GATE LAT (per profile) — declared now, unmeasured.** A latency lever is
  promoted to a profile's default only if it cuts median task wall-clock on that
  profile's hardware class by a pre-set margin with **no regression** on GATE T1
  (task success) or the anti-hallucination metrics. Because Profile C runs a
  different (weaker) model, GATE T1 and GATE PERF are measured **per profile** —
  a suite that passes on Profile A's model is not evidence for Profile C.

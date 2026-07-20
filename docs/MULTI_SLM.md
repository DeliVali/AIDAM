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
- **GATE FLY.** Flywheel-collected data must train an adapter that passes
  GATE FT; until then the flywheel only collects (capture can ship before
  training does).

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

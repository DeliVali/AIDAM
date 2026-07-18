# AIDAM agent subsystem

AIDAM grows from a verification pipeline into a full agent: an interactive loop that
investigates claims at measured depth, reads and writes files, runs commands, and —
optionally — listens, speaks and looks at images. The growth is **additive, not
mutative**: every architectural invariant of the pipeline survives intact, and the new
capabilities are arranged so they *cannot* violate them.

The invariants, restated as design law:

1. **Verdicts come only from the NLI core plus auditable aggregation.** No new module
   — orchestrator, synthesizer, voice, vision — introduces a second path to a verdict.
   Every verdict in the agent is the output of `aggregate.agregar_hecho` /
   `agregar_informe` over `(fact, evidence)` pairs judged by the verifier. Nothing else.
2. **LLMs are tools, never the judge.** Measured in this repo, not assumed: an 8B asked
   to judge directly scored 24% where the pipeline scored 58% on the same claims, and
   the scaffolded-teacher experiment (ROADMAP, 2026-07-13) confirmed it at scale — the
   0.3B specialist at 71.0 BAcc beats every 8B judge mode tried (best: 64.5). In the
   agent, LLMs decompose, reformulate queries, and narrate. They do not vote.
3. **Every assertion cites evidence.** The agent's tools return citations; the
   synthesizer sees only a deterministic evidence table; the audit log records every
   action with who approved it.
4. **Consumer hardware first.** The whole agent — cascade, workers, voice, vision —
   is budgeted for one 12 GB GPU. Anything heavier goes behind an optional extra.

Everything below is the design that follows from holding those four lines fixed.

## The investigation-weight cascade (tier-0 / tier-1 / tier-2)

Most claims are cheap. The AVeriTeC runs show the single-pass pipeline resolving the
bulk of claims in ~18–25 s; spending 5x that on every claim would be waste, and the
cascade literature quantifies it: adaptive escalation keeps ~95% of quality at 45–85%
of the cost, and calibrated-uncertainty cascades (UCCI, arXiv:2605.18796) cut cost 31%
at fixed F1 in production. So the agent runs a **cascade**: a cheap pass always, deeper
investigation only when the first pass *measurably* signals trouble.

**Escalation is measured, never guessed.** After the tier-0 pass (the existing
`pipeline.verificar`), the orchestrator computes four signals:

- **calibrated confidence** — the report's confidence below a threshold
  (`UMBRAL_CONFIANZA = 0.6`). The verifier's probabilities are temperature-calibrated
  (T=1.007, ECE 1.2%, ROADMAP Phase 1); the UCCI warning stands regardless — raw
  softmax entropy is miscalibrated and thresholds don't transfer between workloads,
  so these constants live off-test and are never tuned on benchmark test sets;
- **conflict** — some fact has strong evidence on *both* sides
  (≥ `UMBRAL_CONFLICTO = 0.75` for and against simultaneously);
- **insufficiency** — the verdict is INSUFICIENTE: retrieval found nothing probative;
- **inter-angle disagreement** — once angles exist, 1 minus the modal fraction of
  per-angle verdicts. Disagreement between angles is the SelfCheckGPT insight run
  through our own NLI: inconsistency *is* the difficulty detector, and it is free.

Any of the first three triggers escalation to tier-1; persistence of signal (and the
level cap) triggers tier-2. A forced `nivel=0` never escalates — batch runs stay
deterministic in cost.

**What escalation buys: angles, not repetitions.** The Condorcet jury theorem is the
whole theory of this section: a majority of N voters beats one voter *only if their
errors are independent*. Our verifier is deterministic — N identical passes over the
same (fact, evidence) pairs have correlation 1.0 and gain exactly zero. The ensemble
literature says the same about LLM panels: correlated members degrade the jury toward
a single voter (arXiv:2409.00094; deep-ensembles pathology, arXiv:2302.00704). So each
escalation step must vary the axis that decorrelates errors. In value order:

1. **The negation angle.** Verify the claim's negation with the same pipeline, then
   invert the resulting judgments (SUSTENTA↔REFUTA). "Contradiction to Consensus"
   (arXiv:2602.18693) measured why this works: affirmative search systematically
   under-retrieves refuting evidence, and our own AVeriTeC diagnosis found the same
   failure (viral lie → "supported" because the debunk never surfaced). The negation
   is heuristic and conservative — if no reliable rule applies, no negation angle is
   generated rather than inventing one.
2. **Query reformulations.** The local LLM generates alternative search questions
   (the AVeriTeC 2.0 winners' technique, already shipped behind `--preguntas`). This
   respects the flag: without it, angles are LLM-free (negation only).
3. **Extra source families.** New retrieval against families the tier-0 pass didn't
   reach — different sources, different failure modes. This is FacTool's and SAFE's
   shared lesson: SAFE (arXiv:2403.18802) reaches 72% human agreement — and wins 76%
   of the disagreements — precisely by issuing *multiple independent searches per
   atomic fact*, not by re-asking the same question.

Tier-1 caps at 3 angles, tier-2 at 6. The cap is not modesty, it is the literature:
self-consistency (arXiv:2203.11171) gets the bulk of its gain by N=5–10 and plateaus;
follow-up work on modern models finds the plateau earlier (k≈10–15) with possible
*degradation* beyond it, and PoLL (arXiv:2404.18796) finds the jury effect concentrates
in 3–5 heterogeneous members — a panel of 3 small judges beat GPT-4 at 1/7 the cost.
The useful range is **3–7 angles**; past that, spend nothing.

**Re-aggregation stays auditable.** Angle pairs accumulate with the tier-0 pairs
(evidence deduplicated by domain + text prefix), pass through the same
`comparators.ajustar_pares`, and the final verdict comes from the same
`aggregate.agregar_hecho` — one aggregation path, no new voting mechanism. Tier-1/2
deliberately omits the LLM post-processes (omission judge, NEI probe); they remain
tier-0-only under `--preguntas`, so escalation never adds an LLM opinion to the
verdict. The per-angle verdicts are kept only as the disagreement *signal* and as
report metadata: which angle contributed what is visible in the final
`InformeInvestigacion`.

This design is the local translation of Anthropic's multi-agent research system
(orchestrator scaling worker count by measured complexity, +90.2% over single-agent —
at ~15x token cost). Our workers are I/O-bound retrievers and a 280M batch judge, so
the pattern costs seconds, not dollars; but their hardest-won lesson — *codify the
effort-scaling rules explicitly, or watch 50 subagents chase a trivial query* — is
adopted verbatim: the tiers, thresholds and caps are module-level constants in code.

## Multi-agent doctrine for one 12 GB GPU

The MAST taxonomy (arXiv:2503.13657; 1,600+ traces, 14 failure modes) reduces
multi-agent failure to three families: bad specification, inter-agent misalignment
(agents operating on divergent views of shared state — ~37% of failures), and weak
task verification. AIDAM's doctrine is designed as the point-by-point antidote, under
the constraint that "multi-agent" on a 12 GB card means **multi-process over shared
state**, not N chatting LLMs:

- **Orchestration is code, not an LLM.** The graph decompose→retrieve→judge→aggregate
  is deterministic Python (`orquestador.investigar`). The LLM enters at exactly two
  bounded points — query reformulation and final narration — and decides neither
  routing nor termination. This is also where the field landed: OpenAI's own agents
  guidance recommends orchestrating by code for cost/latency predictability, and the
  visual-builder alternative (AgentKit) was deprecated within a year.
- **Delegation depth is 1.** Orchestrator → workers, never sub-sub-agents. The
  telephone game needs a chain to corrupt; a one-hop star has no chain.
- **Handbacks are structured and typed.** Workers return compact typed records
  (fact, passage, NLI label, probability, citation) — dataclasses, not prose. A worker
  never returns its transcript.
- **Facts travel verbatim.** The atomic fact text is immutable across every hop —
  queued, retrieved against, judged, and reported *literally*. Nothing paraphrases it
  between agents; the telephone cannot mutate what is never rewritten.
- **Shared state lives in a SQLite work queue** (`cola.py`): tasks with
  pending/in-progress/done/failed states, atomic claim under a lock, WAL on disk, and
  orphan recovery (`reanudar_huerfanas`) extending the house `--reanudar` pattern —
  the orchestrator's single-point-of-failure is mitigated by resumability, not by
  distributed consensus. One source of truth; no inter-agent messages to diverge.
- **GPU residency: one 280M NLI server, one swapped 8B.** The verifier (~1 GB) is
  permanently resident; the "N parallel verifiers" are N batched jobs against that
  single server — a 280M encoder judges hundreds of pairs per second while an 8B
  generates tokens one at a time, which is why NLI-as-judge is the only real judgment
  parallelism a consumer card affords. The 8B (decomposition, reformulation,
  synthesis) lives in an isolated worker process, loaded on demand and swapped —
  llama-server's router mode handles model exchange in seconds from NVMe. Retrievers
  are I/O-bound threads: free parallelism, zero VRAM.

MAST's third family, weak verification, is where AIDAM starts with an unfair
advantage: the component most multi-agent systems lack — an external verifier with an
auditable aggregation rule — *is our core product*.

## Permission system and sandbox

The 2025–2026 agent CLIs converged on a common design (deny-first rules, session vs
persistent grants, OS-level sandbox as the enforcement floor); AIDAM adopts the
convergent core rather than inventing one.

**Modes** (`permisos.ModoPermisos`):

| Mode | Read | Write | Execute |
|---|---|---|---|
| `plan` | free | denied | denied |
| `preguntar` (default) | free | ask | ask |
| `aceptar_ediciones` | free | auto-approve inside workspace | ask |
| `lote` (non-interactive) | free | denied unless ruled | denied unless ruled |

**Rules are deny-first**: evaluation order deny → ask → allow, first match wins,
specificity never overrides order. Command patterns are prefix globs
(`Ejecutar(git diff *)`); compound commands are split on `&&`, `||`, `;`, `|`, `&`
and **every** subcommand must match an allow rule while **one** deny match denies the
whole line (`git status && rm -rf /` is denied). Path patterns are anchored globs
resolved through symlinks — a symlink is judged by its target. A short list of
built-in denials (`rm -rf /`, `rm -rf ~`, …) precedes all configuration and cannot be
configured away.

**Grant asymmetry, deliberate**: "always allow" for *commands* may persist across
sessions per project; "always allow" for *edits* lasts only until the session ends
(persisting a write grant raises `ValueError`). Commands are repeatable and reviewable;
a standing write grant is an open door. This mirrors Claude Code's measured asymmetry
exactly.

**The sandbox is the floor, not the policy.** Agent-level rules constrain what the
agent *tries*; they cannot contain what a subprocess *does* (a Python script opens any
file it likes). The enforcement floor is **bubblewrap** — the mechanism both Claude
Code (sandbox-runtime) and Codex CLI independently converged on for Linux in 2026:
read-only root (`--ro-bind / /`), the investigation workspace as the only writable
bind, `--unshare-user/pid/ipc/uts` and `--unshare-net` by default (network is opt-in
per command), `.git` remounted read-only to protect history, tmpfs `/tmp`, milliseconds
of startup and ~zero RAM — which is what makes sandboxed fan-out viable where a
container's ~500 ms cold-start is not. No bwrap installed → the tool degrades to an
explicit error, never to unsandboxed execution.

**Everything is audited.** Every tool call appends one JSON line — timestamp, tool,
argument, decision, mode, who approved, success, content hash — to
`auditoria.jsonl`, flushed immediately, thread-safe. The same discipline that makes
the aggregator auditable makes the agent auditable: the log is the agent's citation
trail.

## Voice and vision: conveniences that never touch the verdict path

Voice and vision are **interfaces**, not evidence. A transcribed question is a
*question* (exactly as if typed); OCR text from a screenshot is a *claim to verify*
(exactly as if pasted). Both feed the pipeline's input; neither ever enters the
evidence pool, weighs in aggregation, or alters a verdict. This line is structural:
`voz.py` and `vision.py` have no import path into `aggregate.py` or `verify.py`
judgment — they only produce text that becomes `pipeline.verificar` input.

**Chosen stacks** (all optional extras, all lazy-imported, all degrading gracefully):

| Role | Choice | License | Notes |
|---|---|---|---|
| STT | faster-whisper, Whisper **large-v3-turbo INT8** | MIT (code and weights) | ~1.5 GB VRAM; strong Spanish+English in one checkpoint, automatic language detection |
| Capture/VAD | RealtimeSTT + Silero VAD | MIT | CPU; push-to-talk first, wake word later |
| TTS | **Kokoro-82M** (ONNX) | Apache 2.0 | CPU — zero VRAM; Spanish voices (`ef_dora` default); missing TTS is a silent no-op |
| OCR tier-1 | **RapidOCR** (ONNX; the repo's existing `imagen` extra) | Apache 2.0 | light, ONNX like the CPU verifier; PaddleOCR is the supported alternative |
| VLM (future) | **Qwen3-VL-8B** GGUF | Apache 2.0 | swapped with the 8B reasoner via llama-server router mode — never co-resident |
| Provenance | **c2patool** (C2PA) | open source (CAI) | fully local cryptographic manifest verification |

Rejected on license alone, whatever their quality: XTTS v2 and F5-TTS (non-commercial),
Moonshine's non-English models (non-commercial community license), Moondream 3 (BUSL) —
a free-information project ships nothing it cannot redistribute freely.

**VRAM budget on the 12 GB card:**

| Component | VRAM | Residency |
|---|---|---|
| NLI verifier (280M) | ~1 GB | always resident |
| 8B reasoner (Q4 + KV) | ~5.5–6.5 GB | on demand, isolated worker |
| faster-whisper turbo INT8 | ~1.5 GB | voice sessions only |
| Kokoro-82M TTS | 0 (CPU) | — |
| RapidOCR (ONNX) | ~0–1 GB (CPU-capable) | on demand |
| Qwen3-VL-8B (Q4 + mmproj + image KV) | ~7.5–8.5 GB peak | swapped with the 8B reasoner |
| Headroom (KV growth, batches) | ~2–3 GB | — |

The one hard constraint: the VLM and the reasoner never coexist — the pipeline is
naturally sequential (VLM extracts the claim → unloads → verification runs → reasoner
narrates), and NVMe swap costs seconds.

**Honest limits, stated up front:**

- **No local reverse-image search against the open web.** That requires a planetary
  index; only paid remote APIs (TinEye, Lens proxies) offer it. If ever added, it will
  be an explicitly remote, off-by-default source family — local-first means saying
  this plainly, not pretending.
- **Absence of C2PA proves nothing.** A valid manifest is provenance evidence; a
  missing manifest is *inconclusive* — most genuine images carry none. `procedencia()`
  returns `None` for absence and the docs forbid reading it as "fake".
- **OCR and STT output is input, not truth.** Transcription errors become claim-text
  errors; the verifier then judges the claim as stated. The interface never
  launders a mistranscription into a verdict.

## The conversational layer: dialogue acts and context blocks (2026-07-16)

The agent's product failures were measured one screenshot at a time —
questions «refuted» at 84%, «no, no es esa» verified against Russian
grammar, «qué día es hoy» answered with Wikiquote's tautology — and each
one became a routed dialogue act. Input now flows through a deterministic
router (regex + measured signals, zero models on the floor tier; every
interpretation is SHOWN, never silently guessed):

| Act | Detector | Response |
|---|---|---|
| social («hola», «gracias») | closed rule set (`contexto.respuesta_social`) | conversational reply, nothing verified, nothing spent |
| computable («qué día es hoy», «15% de 80») | clock/arithmetic patterns (`computables.py`), whitelisted-ast math | instant local answer, provenance stated |
| file order («mueve X a Y») | strict imperatives (`archivos.py`) | permission card with the EXACT action; HOME-only; trash-only deletion |
| question | `sintesis.es_pregunta` (tuned against AVeriTeC false-positives: WHO-acronym, Why-rants) | answer mode: best SENTENCE from meaning-ranked passages, cited; code questions get a copy-ready block extracted verbatim from evidence |
| ambiguous question («qué es lora») | distinctive-term clustering splits the evidence into senses (`aclaracion_necesaria`) | the agent ASKS, listing the senses actually found; the reply joins the pending context block and the refined question re-runs |
| rejection («no, no es esa») | `contexto.es_rechazo` | re-answer with rejected domains excluded |
| request («tienes un ejemplo de código», «show me…») | second-person openers (`contexto._P_PETICION`) — a request is a question by dialogue act, whatever its punctuation (measured 2026-07-17: it was verified as a claim, SUSTENTADO 100% against an OOP tutorial) | answer mode; if it names no topic of its own, it is a follow-up and inherits the previous turn's topic |
| follow-up («y en ese contexto…») | connectors/deictics + antecedent search; elliptical requests join this act | rewritten self-contained against the best prior turn, closing as a question so routing stays in answer mode |
| claim (everything else) | default | the full verify pipeline; verdicts always carry a one-breath grounded explanation (`respuesta_concisa`) |

**Conversational context is three tiers, RAM-only** (dies with the session;
never disk, never the repo): a 20-turn verbatim window; a compacted tier
where evicted turns fold into topic terms + their embedding (bytes, not
text — anchored-summary consensus, arXiv:2308.15022); and `GrafoPalabras`,
Jeffrey's keyword architecture — words interned once as integer ids,
turns as id-tuples, an inverted index as edges, rarity-weighted lookup.
Antecedent priority: exact rare-word hit > embedding similarity > recency.

**Two measured laws shaped this layer.** (1) The small embedder CANNOT
split same-word senses — lora-IoT vs LoRA-ML sit at cosine 0.90+ because
the shared surface term dominates; distinctive-term clustering separates
them with zero overlap. Keyword structures beat embeddings exactly where
the surface form collides. (2) Generic modifiers bridge unrelated topics
(«bajo consumo»/«bajo rango» merged the senses) — they live in the
stopword set now.

**Input spelling cleanup** (`ortografia.py`) is conservative by measured
necessity: a naive corrector turns «Pogba» into «bomba». Questions only,
capitalized words untouchable, edit-distance-1 fixes with an
anti-mojibake guard, and Spanish diacritics from a curated in-repo map —
pyspellchecker's es dictionary is corrupted («según» missing, «segün»
present). Every applied change is shown.

**Ecosystem surfaces.** `POST /v1/chat/completions` makes AIDAM a
provider for assistant infrastructure (OpenClaw gateways: point them at
`http://localhost:8236/v1`, model `aidam-verificador`) and any
OpenAI-style client — verification from WhatsApp/Telegram without
building messenger bridges ourselves.

**The answer follows the user's language.** The deterministic answer
templates exist in the six UI languages (es/en/fr/de/pt/it, phrase table
in `sintesis.py`; measured failure 2026-07-17: German claim, Spanish
answer). The websocket client sends the UI's `lang`; the OpenAI endpoint
has no language field, so `idioma.py` detects it from the typed message —
rarity-weighted function-word profiles, zero models, falling back to the
default when the input is too short or ambiguous to call.

## Pre-registered gates

House rule: gates are declared **before any numbers exist**, and a failed gate blocks
promotion regardless of how much work went in (see the scaffolded-teacher and v21
entries in ROADMAP for the discipline in action).

- **GATE (cascade promotion) — declared now, unmeasured.** The tier-1/2 cascade is
  **NOT promoted to default**. `investigar` ships behind explicit invocation
  (`/investigar`, `--nivel`); `verificar` remains tier-0. Promotion to default
  requires, on FEVER dev **and** the general set (AggreFact + FEVER + SciFact +
  AVeriTeC-500): (a) at fixed coverage, the cascade's selective-prediction risk is
  lower than tier-0's; (b) ECE no worse than tier-0's; and (c) **inter-angle agreement
  predicts correctness** — accuracy on high-agreement claims must significantly exceed
  accuracy on low-agreement claims. Criterion (c) is the Condorcet audit: if agreement
  does not predict correctness, the angles are not independent, and the remedy is
  redesigning the diversity — never raising N. Escalation thresholds stay off-test:
  tuning them on benchmark test sets voids the gate.
- **GATE (voice/vision as evidence) — standing.** Voice and vision ship as UI
  conveniences only. Whisper-as-evidence remains gated by the existing roadmap rule:
  video/podcast evidence is captions-only in v1, with **no local Whisper
  transcription until a measured miss-rate justifies the GPU cost**. Nothing in this
  subsystem re-opens that gate implicitly.

## Module map: `aidam/agente/*`

| Module | Role |
|---|---|
| `permisos.py` | deny-first permission engine; four modes; grant asymmetry |
| `auditoria.py` | JSONL audit log, immediate flush, content hashing |
| `sandbox.py` | bubblewrap-confined execution; pure command builder + runner |
| `cola.py` | resumable SQLite work queue (atomic claim, orphan recovery) |
| `angulos.py` | investigation angles: heuristic negation, LLM reformulations, judgment inversion |
| `orquestador.py` | the cascade: `investigar`, escalation signals, auditable re-aggregation |
| `sintesis.py` | deterministic evidence table + LLM narration with an anti-contradiction safeguard (a synthesis contradicting the verdict is dropped, never shown) |
| `herramientas.py` | typed tools: read/write/execute/verify/investigate, permission- and audit-wired |
| `bucle.py` | the agent REPL: one `while`, flat history, slash commands, rich rendering |
| `voz.py` | optional STT/TTS (extra `voz`); lazy imports, graceful degradation |
| `vision.py` | optional OCR + C2PA provenance (extra `vision`) |
| `rastreo.py` | optional tier-2 crawler (extra `rastreo`, Crawl4AI, robots.txt respected) |
| `contexto.py` | dialogue acts (social/rejection/follow-up), three-tier RAM context, `GrafoPalabras` keyword memory |
| `computables.py` | clock/arithmetic questions answered by code (whitelisted ast), never by retrieval |
| `archivos.py` | native file control from conversation: HOME-only, trash-only, strict parsing, permission-gated |
| `codigo.py` | measured code comparison: sandboxed timing (core-pinned), correctness fingerprints, LLM/web candidates |
| `ortografia.py` | guarded question spelling cleanup; curated Spanish accent map (broken upstream dictionary, measured) |
| `idioma.py` | deterministic input-language detection (function-word profiles) for callers that send no `lang` |

All modules import without torch, network or GPU; heavy dependencies load lazily
behind pyproject extras. The binding interface contracts live in the implementation
spec; this document is the *why*.

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
- [x] **In-domain fine-tuning attempt (verifier v4/v5, 2026-07-07/08) — two real
      bugs found, verifier not promoted.** AVeriTeC's train split (3,068 claims,
      never touching dev) was converted to NLI pairs (`generate_averitec_pairs.py`)
      and mixed into training, on the thesis that VitaminC/MNLI (Wikipedia-style)
      never taught the model real-world viral-claim *style*.
      - **v4** (raw label distribution: 62% Refuted/30% Supported/10% NEI,
        repeated 3x) scored 41% on AVeriTeC-100, *below* v3's 45%. Root cause,
        verified on the actual predictions: a trivially true, well-evidenced
        claim (3 voices, confidence 1.00) was predicted Refuted — the
        imbalanced injection taught a REFUTES shortcut for real-world-claim
        style. Fixed: `generate_averitec_pairs.py --balancear` caps every
        label at the minority-class count (280/class).
      - **v5** (balanced pairs) scored 87.34% VitaminC test / 65.0% AggreFact —
        both *marginally below* v3 (87.76% / 66.2%). The AVeriTeC-live
        comparison (two attempts, 38% and 39%) could not settle it either way:
        both runs were confounded by a **retrieval throttling problem**
        (below), not the verifier. On the network-independent benchmarks,
        which are the fair comparison, v5 does not beat v3.
      - **Decision: v3 (`models/verificador-v0`) stays the production default.**
        8,400 in-domain pairs out of a ~222k mix was evidently too small a
        fraction to shift a checkpoint already saturated on general NLI skill;
        a real domain-adaptation attempt would need either a much larger
        in-domain corpus or a staged fine-tune (specialize on VitaminC+MNLI
        first, then a short in-domain pass) rather than one blended mix.
      - **Second, independent bug found and fixed along the way**: the search
        cooldown (below) initially matched failures by ddgs exception *type*
        (`RatelimitException`/`TimeoutException`), reasoning that a generic
        exception could just mean "no results for this query." Measured wrong:
        live probe showed duckduckgo raises a generic `DDGSException("No
        results found")` on *every* query and bing a raw `ConnectError` —
        neither matches the typed exceptions, so both backends never cooled
        down, wasting a timeout + pacing slot on two dead engines before every
        single search. Fixed: any exception counts as an engine failure again;
        rotation reordered `yahoo → bing → duckduckgo` (yahoo measured healthy).
      - **Residual, unresolved**: even after that fix, both v5 AVeriTeC-100 runs
        showed the same shape — evidence-per-claim (voces) dropping roughly by
        half from the first to the second half of a single run (2.6→1.5, then
        2.6→1.6), and an isolated 30-query diagnostic reproduced the same decay
        curve independent of pacing (tested 1.0s and 3.0s — no difference).
        This looks like session-cumulative IP reputation decay with these free
        engines across hours of sustained querying, not a client-side
        rate/backend-selection bug — no further code change fixed it within
        the session. Next step: either an authenticated/paid search API for
        eval runs, or spacing full AVeriTeC-100 runs hours apart to let
        reputation reset, before trusting a live AVeriTeC number again.
- [x] **Verifier v6 promoted (2026-07-08): +2 epochs closes real headroom, now
      `models/verificador-v0`.** v0-v5 all trained a single epoch; that was
      under-converged. v6 = v3's exact recipe (VitaminC + MNLI + hard neutrals
      + synthetic, no AVeriTeC pairs) for 2 epochs instead of 1. Result on the
      three network-independent benchmarks (the fair comparison, since AVeriTeC-
      live was contaminated by the retrieval exhaustion below): **VitaminC test
      88.52% (v3: 87.76%, +0.76), LLM-AggreFact 66.2% (v3: 66.2%, tied), XNLI-es
      99.5% (v3: 99.7%, tied within noise — both readings contaminated, the
      base checkpoint saw XNLI in pretraining)**. A real, if modest, all-around
      improvement with no regression on any clean metric — promoted; old v0
      archived at `models/verificador-v0-1epoch-archivado`.
- [x] **Search-substrate exhaustion is cumulative across a SESSION, and gets
      WORSE the more you test it (2026-07-08) — critical operational finding.**
      Five consecutive live AVeriTeC-100 attempts within one extended session,
      in order: 45% (v9, healthy network) → 41% (v4) → 38% (v5) → 39% (v5,
      retry after a cooldown-logic fix) → **22% (v6, worst yet)**. Evidence per
      claim (voces) fell in lockstep: ~2.1 → ~2.0 → ~1.9 → **0.95, with 66/100
      claims at literally zero evidence** on the last run. This is NOT primarily
      about verifier quality — v6 is the best verifier of the five by every
      clean benchmark, yet scored the worst live number, because each
      successive eval run further exhausts the same shared, cumulative
      resource (the free search engines' tolerance for this IP) rather than
      testing under comparable conditions. **Operational rule going forward:
      do not run more than one full AVeriTeC-100 live eval per session; space
      repeated live evals hours-to-days apart; treat a live AVeriTeC number as
      informative only if it's the FIRST live-search-heavy activity of the
      session.** A same-session live-AVeriTeC "A/B" between two verifiers is
      not a valid comparison — the second run is always structurally
      disadvantaged regardless of which model is better.
      **Update, same day**: waiting doesn't rescue this either. A fresh
      health probe after an hour-plus of unrelated work showed full recovery
      (15/15 distinct fresh queries succeeded, real network latency, not
      cache); a full AVeriTeC-100 launched immediately after still landed at
      **22.0%, matching the already-exhausted v6 run almost exactly**, with
      voces degrading from the healthy start down to 1.1-1.2 well before the
      run finished. **The exhaustion threshold is reached WITHIN a single
      ~100-claim run, not just across runs** — so "start from a healthy
      network" doesn't help if the eval itself is long enough to re-exhaust
      it. The only real fix is removing the live-search dependency for
      evaluation, which is what the knowledge-store integration below does.
- [x] **New keyless sources (2026-07-08): Wikidata, openFDA,
      ClinicalTrials.gov.** Wikidata renders structured facts (dates,
      positions held, populations) precision-aware (a year-only fact
      doesn't get a fabricated day) — independent infrastructure from
      Wikipedia's own text search, so it survives ddgs exhaustion. openFDA
      (drug labels) and ClinicalTrials.gov (registered trials) weigh
      `docs-oficiales` (8.0), the same tier as a professional fact-checker —
      official registries, not secondary summaries. All three verified live
      end-to-end through `recuperar()`, not just raw API calls.
- [x] **Tested and rejected: dropping ddgs entirely (`AIDAM_SIN_DDG=1`) to
      dodge the exhaustion above (2026-07-08).** Built as a kill switch that
      falls back to every source with its own separate rate limit (Wikipedia
      family, academic APIs, StackExchange, GDELT). Result on the same
      AVeriTeC-100: **14.0% — worse than every exhausted-ddgs run this
      session**, with voces collapsing to 0.44 (78/100 claims zero evidence,
      the worst evidence coverage measured all session). Honest conclusion:
      for AVeriTeC's real-world viral/political claim style, the ddgs-
      mediated sources (`web`, `desmentidos`) carry nearly all the useful
      signal — Wikipedia/Wikidata/academic sources have almost no coverage
      of ephemeral 2020 political rumors, so removing ddgs even while
      throttled is strictly worse than keeping it. The kill switch itself is
      kept (`aidam/retrieve.py::_ddg_deshabilitado`, tests included) since
      it's a legitimate tool for other claim styles or a fully-dead network,
      but it is NOT the fix for this specific exhaustion problem. (Later the
      same day: waiting for reputation to reset turned out not to be the fix
      either — see the update above. The knowledge-store integration below is.)
- [x] **Tested and rejected: public SearXNG instances (2026-07-08).** SearXNG
      is open source and instances are keyless, so it looked like a natural
      way to diversify away from the specific ddgs backends we'd exhausted.
      Six public instances tested live: every one either rate-limited
      immediately (429, likely from other users' global traffic) or has its
      JSON API disabled for anonymous/external callers — a deliberate admin
      choice specifically to prevent the kind of automated querying we do.
      Not viable as a search-diversity lever.
- [x] **The official AVeriTeC "score" is a different, stricter metric than
      what this project measures — correcting a conflation (2026-07-08).**
      `evaluation/eval_averitec.py` computes plain label accuracy (does the
      predicted class match gold). The shared task's own "AVeriTeC score"
      only counts a claim correct if the label ALSO comes with evidence
      scoring ≥0.44 Ev2R recall against gold evidence (graded by an LLM) —
      much stricter. Concretely, from the HerO paper: **label accuracy
      0.752, AVeriTeC score 0.578** — same system, same run, very different
      numbers depending which one you read off a leaderboard. Confirms the
      90% ceiling either way: 75.2% is the best published *label accuracy*
      we found (HerO); the stricter score runs lower still (winning team:
      33.17% in the 2025 shared task). Sources: HerO paper
      (arxiv.org/html/2410.12377v2), 2nd AVeriTeC Shared Task overview
      (aclanthology.org/2025.fever-1.15/).
- [x] **Open-source reference systems worth reading for technique ideas**:
      [HerO](https://github.com/ssu-humane/HerO) (runner-up 2025, open-LLM
      pipeline, closest in spirit to AIDAM's design) and
      [CTU AIC](https://github.com/aic-factcheck/aic_averitec) (winner 2025,
      "fact-checking as simple RAG"). Not yet read in depth this session —
      next-cycle task.
- [x] **Offline evaluation via the organizers' knowledge store (2026-07-08).**
      The shared task publishes a pre-scraped document collection per claim
      (`huggingface.co/chenxwh/AVeriTeC`, gated behind a free HF account —
      Jeffrey's existing token already has access) specifically so systems
      don't need live search. `evaluation/knowledge_store.py` +
      `aidam/pipeline.py`'s new `recuperador` seam wire it into
      `eval_averitec.py --knowledge-store DIR`. This is the real fix for
      every exhaustion finding above — no amount of pacing, backend
      rotation, or waiting helps when the eval itself is the thing
      exhausting the resource; removing the live-search dependency for
      evaluation does.
      **First offline run (2026-07-08): 47.0% accuracy, F1 macro 0.326 — the
      best AVeriTeC-100 number of the entire session, beating even the
      original healthy-network baseline (45%), at 2.9 s/claim with zero
      network variance.** Every class scored non-zero F1 for the first time
      all session, including Conflicting Evidence/Cherrypicking (0.143 —
      every single live run tonight scored exactly 0.000 there): that class
      needs multiple credible, independent sources to genuinely conflict,
      which starved live search essentially never supplied, but the rich
      pre-scraped store does (per-claim documents from up to 1000 URLs).
      Refuted F1 0.649 and Supported F1 0.318 are both this session's best.
      Fixed a parser bug on the way: the "JSON-lines" files aren't really
      line-delimited (scraped text embeds literal unescaped newlines inside
      string values, corrupting naive `.splitlines()`); `_cargar_documentos`
      now walks JSON object boundaries directly via
      `json.JSONDecoder.raw_decode` in a loop, immune to embedded newlines.
      **This is now the recommended way to run AVeriTeC-100/500**:
      `eval_averitec.py --limite N --knowledge-store data/local/knowledge_store/dev`
      (dev split only prepared so far; `--extraer` pulls more claims from
      the already-downloaded zip on demand). Live retrieval (`recuperar()`,
      the default) stays the only option for real deployed verification of
      claims outside the dataset — the knowledge store is eval-only.
- [x] **Denial statements are an implicit-negation gap in the verifier, not
      an aggregation problem (2026-07-08) — traced, not fixed.** With a fast,
      noise-free offline eval finally available, inspected the largest error
      bucket (14 Refuted claims predicted Supported). Traced claim #30 (Paul
      Pogba hoax) to the pair level: six domains carrying the actual denial
      ("Pogba said he will be 'taking legal action' after reports claimed he
      had retired") are ALL classified **NO_CONCLUYE by the verifier**, not
      REFUTA — "X denies Y and threatens to sue over reports of Y" doesn't
      map to textbook NLI contradiction, it requires recognizing an implicit
      meta-level negation. Only one domain phrases the claim directly enough
      to read as SUSTENTA, and it wins by default. Added "alleged"/"denied"
      to `_MARCADORES_DESMENTIDO` (English was missing even though its
      Spanish twin "alegada" was already covered) on the reasonable
      hypothesis this was an attribution-trap gap — measured **zero change**
      on the full offline eval (47.0%, identical confusion matrix), because
      the discount only ever applies to evidence already labeled SUSTENTA,
      and the denial passages never reach that label in the first place. Kept
      the marker anyway (harmless, no regression, correct for cases where it
      DOES apply) but this is not the real fix. **Real fix would be training
      data**: minimal-edit pairs teaching "subject denies X" / "X was ruled
      false" style sentences as REFUTES, not NEUTRAL — a `generate_synthetic_llm.py`-shaped
      task, not an aggregation-weight tweak. Next-cycle item.
- [x] **`max_pasajes` swept on the offline eval (2026-07-08): 12→25 nearly
      doubles the improvement over the original number, real headroom found
      because the fast offline eval finally makes sweeping cheap (~2 min/run,
      vs. a live sweep that would each independently re-exhaust the search
      substrate).** Traced from a genuine retrieval-recall failure: claim #2
      ("...cancelled the visas...") had a 1.18-million-sentence candidate
      pool per claim, and the original cap of 12 was dominated by six
      near-duplicate paraphrases of the claim's easy half ("Khan criticized
      Macron"), crowding out the decisive, rarer detail. Swept 12/20/25/40:
      **47.0% → 51.0% → 56.0% → 54.0%** (F1 macro 0.326 → 0.331 → 0.345 →
      0.359 — 25 wins accuracy, 40 wins macro-F1 by favoring Conflicting
      Evidence recall over Supported precision). Kept **25** as the default:
      accuracy has been this project's headline metric throughout, and 25 is
      cheap enough that a real deployment could reasonably go higher still.
      **56.0% remains the session's best number.**
- [x] **Tested and reverted: MMR-style diversity reranking (2026-07-08).**
      The natural next idea after the sweep above — instead of a flat top-K
      by relevance, greedily diversify the selection (Jaccard similarity over
      content words, standard Maximal Marginal Relevance) so near-duplicate
      paraphrases can't crowd out a rarer decisive detail. Implemented,
      verified it DID work as intended (claim #2 went from a handful of
      near-duplicate domains to 20 distinct ones, and surfaced a
      visa-cancellation passage the flat cap missed) — then measured **worse
      overall: 52.0% vs. the flat cap's 56.0%, F1 macro 0.266 vs. 0.345**
      (Conflicting Evidence F1 collapsed to 0.000). Best-guess reason:
      independent domains repeating the SAME correct fact is real
      corroborating signal for this project's reliability-weighted
      aggregator — `aidam/aggregate.py`'s one-voice-per-domain rule already
      prevents them from over-counting, so diversifying past that traded
      away genuine multi-source confirmation for topical spread that turned
      out to include more off-target noise than decisive detail. Reverted;
      the mechanism (`_seleccionar_diverso` in
      `evaluation/knowledge_store.py`) is documented in the function's own
      history, not left as unused code. A more targeted version — diversify
      only among near-identical candidates, not the whole shortlist, or
      split compound claims into sub-facts and retrieve each independently —
      might still work; this specific implementation didn't.
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

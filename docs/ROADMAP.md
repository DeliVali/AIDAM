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
- [x] **Question-generator A/B (MiMo-7B-RL vs DeepSeek-R1-0528-Qwen3-8B) —
      resolved (2026-07-08): DeepSeek promoted to default.** First attempt
      (2026-07-07) was invalid — DeepSeek scored 16% with 75/100 claims at
      zero evidence voices because the live-search substrate was exhausted
      mid-run, confounding the comparison entirely. The offline knowledge-
      store eval fixes this at the root (no network variance to confound
      anything): re-ran the same A/B on the current best configuration
      (question-driven search + NEI resolver, both bugfixed) — **DeepSeek
      60.0% accuracy / F1 macro 0.373 vs. MiMo 59.0% / 0.385**. DeepSeek wins
      accuracy and Supported/Refuted F1; MiMo wins Conflicting Evidence F1
      (0.250 vs 0.154) — a real tradeoff, not a clean sweep. Promoted anyway
      since accuracy has been the project's headline metric throughout.
      `aidam/questions.py::_RUTA_DEFECTO` now points at
      `models/deepseek-r1-qwen3-8b/`; MiMo remains selectable via
      `AIDAM_MODELO_PREGUNTAS`. Also independently relevant: MiMo showed a
      specific, measured weakness earlier this session (circles rather than
      converging on ambiguous compound claims, see the dissent-resolver entry
      below) that motivated testing whether a different reasoning
      architecture would share it — inconclusive either way from one 100-claim
      run, but DeepSeek didn't show the same runaway-length failure mode in
      this comparison.
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
- [x] **Offline question-driven search: 58.0%, new best (2026-07-08).** MMR
      diversified WITHIN one query's results and lost to genuine
      corroboration; this instead changes the QUERY — the split-compound-
      claims idea flagged above, using the machinery already built for
      `--preguntas` rather than new code. `aidam/pipeline.py::verificar()`
      gained a `buscador_preguntas` seam (mirrors `recuperador`, same
      non-invasive pattern) so the LLM's follow-up sub-questions can search
      anywhere, not just live `buscar_web`. `eval_averitec.py --knowledge-store
      --preguntas` now points them at the SAME per-claim offline store,
      wrapping each sub-question as its own query — no live search at all,
      still fully reproducible. Claim #2 ("Khan criticized Macron" +
      "France cancelled visas") is the motivating case: the LLM generates a
      sub-question aimed at the specific visa detail, searched independently
      of the dominant "Khan criticized Macron" term frequency that was
      crowding it out. Result: **58.0% accuracy, F1 macro 0.368** (vs. the
      flat-cap-only 56.0%/0.345) — Conflicting Evidence F1 0.250 (up from
      0.133), Not Enough Evidence F1 0.235 (up from 0.182), at 9.1s/claim
      (LLM generation cost, still no network wait). Supported F1 dipped
      slightly (0.242 vs 0.308) — worth watching, not yet enough of a signal
      to act on with a 100-claim sample. This is now the recommended way to
      run the offline eval when the local LLM is available.
- [x] **Tested: LLM as the SOLE verdict judge, replacing the NLI+aggregator
      entirely (2026-07-08). Much worse — 24.0% vs. 58.0%.** Motivated by a
      real, traced NLI limitation (implicit-negation denials the pairwise
      classifier can't resolve, a reasoning model can). Built `--llm-juez`:
      retrieve the same evidence, hand it to the LLM with reasoning allowed,
      parse SUPPORTED/REFUTED/NOT ENOUGH EVIDENCE/CONFLICTING from the end of
      its answer. Root cause of the collapse: the LLM defaulted to "Not
      Enough Evidence" on **63/100** claims (gold: 7) — 40 of the 63 were
      actually Refuted. Reading evidence directly, without the aggregator's
      explicit reliability-weighted voting, the model is far too cautious to
      convert convergent circumstantial signal (many independent sources
      converging on the same conclusion, none stating it in one flat
      declarative sentence) into a confident verdict — exactly the job the
      aggregator's math already does well. Not promoted; kept only as an
      opt-in eval mode for comparison.
- [x] **Built instead: LLM as a targeted NEI resolver, not a replacement
      (2026-07-08). Flat on this 100-claim sample (58.0%→58.0%), architecture
      kept.** The standalone judge's own NEI-bias, reframed: consult it ONLY
      on facts the aggregator itself couldn't decide (`Veredicto.INSUFICIENTE`)
      — if it still returns something confident despite that bias, that
      disagreement is real signal, not noise. `verificar()` now does this
      automatically whenever `preguntas=True` (the LLM's already loaded for
      question generation; no extra cost when it doesn't fire). Measured
      effect: nearly identical confusion matrix to question-driven search
      alone (only one claim flipped, Supported NEI→correct) — the aggregator
      + question-driven search combination already resolves almost every
      claim with SOME confident signal, leaving very few genuine INSUFICIENTE
      cases for the resolver to act on in a 100-claim sample. Kept (harmless,
      architecturally sound, doesn't regress) rather than reverted like MMR;
      may matter more on the full 500-claim dev set or a different claim mix
      with more genuine evidence gaps.
- [x] **Tried extending the resolver to also cover SUSTENTADO-with-dissent —
      found two real bugs, reverted the extension anyway, kept the bugfixes:
      59.0%, new best (2026-07-08).** The Pogba case that motivated the whole
      resolver family was traced to SUSTENTADO at confidence 1.00, never
      INSUFICIENTE (the NLI classifier judged all six denial passages NEUTRAL
      individually, so they never got to outvote the one passage stating the
      rumor directly) — meaning the INSUFICIENTE-only trigger could
      *structurally never reach the case it was named after*. Built a broader
      "dissent resolver" (also consult on SUSTENTADO + substantial dissenting
      REFUTA evidence) to close that gap, and found two genuine bugs on the
      way: (1) `juzgar_veredicto` was reading `evidencias[:8]` in raw
      retrieval order — with question-driven search routinely pulling 30+
      passages, the actual triggering REFUTA evidence could fall past the
      cutoff entirely (measured: this silently starved the very case being
      debugged); (2) even after fixing that, 500/1200/2000-token budgets all
      cut the reasoning off mid-thought — this model doesn't self-terminate
      on ambiguous compound claims, it circles (measured: 8,861 characters
      of reasoning, still undecided). Fixed both — sort evidence into the
      prompt by (NLI signal, probability) instead of retrieval order; cap
      reasoning explicitly in the prompt ("2-3 sentences, then answer")
      instead of just raising the token ceiling. Even fixed, the *specific*
      Pogba case still didn't resolve (genuinely ambiguous compound claim —
      initial reports vs. a later denial vs. what the claim precisely
      asserts), and the *broader trigger* measured worse overall on the full
      100-claim eval (58.0%→57.0%). Reverted the trigger. **But the same two
      bugfixes also apply to the existing INSUFICIENTE-only resolver above
      (it was making the same evidencias[:8]-ordering and reasoning-budget
      mistakes) — re-measured with just those fixes and the trigger reverted:
      59.0% accuracy, F1 macro 0.385, both new session bests** (NEI F1 0.250,
      Supported F1 0.294, both up from the prior 58.0% run). The real lesson:
      chasing one specific hard case led nowhere, but the debugging surfaced
      genuine defects in shared machinery that helped everywhere else.
- [x] **Traced a Supported→Refuted error (Amy Coney Barrett confirmation
      date, 2026-07-08) — genuine source ambiguity, not a bug.** Unlike the
      Pogba investigation, this one didn't lead anywhere fixable, and that's
      itself the informative result. The claim ("confirmed...October 26,
      2020") is true and gold-labeled Supported; the top-ranked evidence
      (fedsoc.org, REFUTA at 0.99) says "confirmed on October 27" — and
      that's not a bad source: **supremecourt.gov itself** states the
      Judicial Oath was administered October 27, distinct from the Senate
      confirmation vote on the 26th. Multiple authoritative sources use
      "confirmed"/"joined the Court"/"sworn in" interchangeably for two
      technically different events a day apart — 8 of the 10 highest-
      confidence NLI judgments landed REFUTA, correctly reading a literal
      date mismatch against sources describing the adjacent-but-distinct
      event. No code fix addresses this without risking other genuinely
      date-sensitive judgments; it would need narrow domain knowledge (the
      confirmation-vote/oath-administration distinction specifically) that
      isn't worth hand-coding for one historical fact pattern. Recorded as a
      concrete illustration of the task's real difficulty ceiling: some
      errors are bugs, some are the genuine hardness of real-world source
      disagreement, and distinguishing the two matters more than forcing a
      fix onto the second kind.
- [x] **Verifier v7 (date-mismatch hard neutrals) — 62.0% AVeriTeC accuracy,
      first time past the 61% majority baseline, but NOT promoted
      (2026-07-08).** Against the advice of the entry above, tried the
      trainable version of the date-precision fix anyway:
      `training/generate_date_neutrals.py` mechanically mines VitaminC for
      same-topic pairs whose only conflict is a nearby-but-different date
      and labels them NOT ENOUGH INFO (5,000 pairs), teaching "a close date
      mismatch on a related event is ambiguity, not flat contradiction."
      v7 = v6's exact recipe + those pairs, 2 epochs. Results, honestly
      read: **the intended mechanism did not fire** — the Barrett case that
      motivated the data is still wrong, and per-claim diff vs. the 60.0%
      run shows 6 of the 7 newly-correct claims are flips TO Refuted (the
      dataset is 63% Refuted; a stronger refute tendency buys accuracy on
      this skew without being smarter). Meanwhile every clean,
      skew-independent metric regressed: VitaminC test 88.52→87.96,
      AggreFact 66.2→65.8, AVeriTeC macro-F1 0.373→0.305 (NEI predictions
      collapsed to 1/100). **v6 stays production.** The 62.0% is real and
      reproducible (`AIDAM_MODELO_VERIFICADOR=models/verificador-v7`,
      results archived at `averitec_results_v7_62pct.jsonl`) and crossing
      the majority baseline was one of the project's three original success
      criteria — but crossing it via class-skew alignment while regressing
      everywhere else is not the version of that milestone worth keeping,
      and for real-world use (where claims aren't 63% false) v7's shifted
      prior is a liability, not a feature. The milestone that counts is
      still ahead: past 61% with macro-F1 holding.
- [x] **Full 500-claim offline run — the real number: 55.0% accuracy, F1
      macro 0.309, 11.1 s/claim (2026-07-08).** Best configuration (v6 +
      DeepSeek question-driven search + NEI resolver) on the complete dev
      set with the organizers' knowledge store. Honest readings:
      1. **The 100-claim numbers ran ~5 points hot** (60% sample → 55%
         full set): the dev set's first 100 claims are evidently easier
         than its average. Every future comparison should quote the
         500-claim figure.
      2. **Against the last full-500 measurement (44.0%, live retrieval,
         2026-07-06): +11 points** — the sum of tonight's verifier,
         retrieval, and methodology work, measured on identical claims.
      3. Refuted F1 0.705 (was 0.604); Supported F1 0.354 (was 0.390);
         Conflicting remains near-floor (0.074) — the hardest class, still
         the biggest open problem, consistent with every run tonight.
      4. Still below the 61% majority baseline on accuracy — the honest
         gap to close next; the class-skew route to beat it (v7) was
         measured and rejected on principle.
- [x] **Verifier v8 (denial-pattern pairs) PROMOTED: 62.0% on the full 500,
      majority baseline crossed with macro-F1 RISING (2026-07-09).** The
      denial set (12k three-way shortcut-proofed pairs, see
      `generate_denial_pairs.py`) did what v7's date neutrals didn't:
      the mechanism verified causally at every level — the traced Pogba
      probe flipped (16 REFUTA pair judgments where before there were ~0),
      a Pogba-claim variant in the eval itself flipped to correct, and the
      100-claim flip-diff showed denial-genre corrections plus recovered
      Supported/Conflicting claims, not skew. Full-500 vs v6:
      **62.0% vs 55.0% accuracy (+7.0), F1 macro 0.360 vs 0.309, and every
      single class improved** (Refuted 0.767, Supported 0.388, Conflicting
      0.140, NEI 0.143) — the exact opposite of the v7 signature, and the
      legitimate version of the criterion-(b) milestone as defined when v7
      was rejected: past 61% with macro-F1 holding (here: rising). Clean
      benchmarks drifted marginally (VitaminC 88.17 vs 88.52, AggreFact
      65.3 vs 66.2) — accepted against a +7.0/+0.051 gain with verified
      causal mechanism. v6 archived at `models/verificador-v0-v6-archivado`.
      Series on the full 500: **44.0% → 55.0% → 62.0%**.
- [x] **Verifier v9 (temporal-qualification pairs) — REJECTED at full scale
      despite the mechanism firing (2026-07-09).** Applied v8's proven recipe
      (fully synthetic three-way shortcut-proofed contrast,
      `generate_temporal_pairs.py`, 12k pairs) to the biggest remaining error
      signature: quantities not bound to their time qualifiers ("at
      independence, 45M" refuted by today's 200M). The pair-level probe
      verified the mechanism completely — #207's wrong-time passages flipped
      from confident-REFUTA to neutral (22 no_concluye / 3 refuta), Pogba
      held, VitaminC even rose (88.35 vs v8's 88.17). **But the full 500
      measured worse: 60.6%/0.343 vs v8's 62.0%/0.360.** The two-sided
      trade, quantified: the targeted bucket barely moved (Supported→Refuted
      73→70 — #207 itself STILL ends Refuted, because neutralizing wrong-time
      evidence leaves NO supporting evidence rather than producing support;
      the correct-time figure simply isn't in the store), while genuine
      refutations weakened everywhere else (Refuted correct 263→258,
      Refuted→Supported errors 23→29 — many false claims are numeric
      exaggerations where the mismatch IS the refutation, and softening it
      loses them). **New methodological lesson, complementing v7's**: v7
      taught that aggregate gains without a verified mechanism are suspect;
      v9 teaches that a verified mechanism without aggregate gains is still
      a rejection — pair-level success only converts to claim-level wins if
      the corrective evidence actually exists to take over, and here the
      bottleneck was evidence coverage, not judgment. v8 stays production.
- [x] **Aggregation constants swept and CONFIRMED (2026-07-09).** Built
      `evaluation/sweep_aggregation.py` (caches retrieval+QG+NLI pairs once,
      re-aggregates in milliseconds — parameter sweeps went from 1.5 h to
      instant per point) and ran the 36-point grid over DOMINANCIA ×
      UMBRAL_SENAL × PESO_DESMENTIDO on a tuning slice (claims 100-299)
      disjoint from anything previously optimized against. Result: the
      production constants are already at the accuracy/F1 balance point —
      the best alternative (+1.5 accuracy at DOMINANCIA 1.5) pays with
      macro-F1 0.387→0.345, the same skew-shaped trade rejected with v7,
      and within noise at n=200. PESO_DESMENTIDO barely decides anything
      across 0.15–0.40. **Every optimization axis has now been swept or
      tried with measured results: verifier training (v3–v9), retrieval
      (max_pasajes, MMR, question-driven), LLM assistance (sole judge, NEI
      resolver, dissent resolver), backend choice (MiMo/DeepSeek), and
      aggregation parameters. The architecture's measured ceiling on
      AVeriTeC-500 is ~62%** — remaining error mass is characterized as
      negation-scope/entity-precision nuance beyond pairwise-NLI capacity
      (documented above), plus evidence-coverage gaps the store itself
      bounds. Next frontier per the phased plan: other benchmarks, and
      Phase 3's reasoning-class machinery.
- [ ] Temporal handling: volatile vs. stable facts
- [ ] Active search for contrary evidence (anti-confirmation bias)
- [ ] **Triage of Jeffrey's source brainstorm (2026-07-08)** — judged
      per-category, honest verdicts:
      - **Laws by country — WORTH IT**: BOE Spain (keyless open-data API,
        priority for the Spanish mission), EUR-Lex EU, GovInfo/Congress.gov
        US (free keys). "The law says X" is a real viral genre and the
        gazette is the primary source.
      - **Public testimony/trials — WORTH IT**: UK Hansard (keyless API) for
        "politician said X in parliament"; US CourtListener already shipped;
        GovInfo hearing transcripts (free key) later.
      - **Cybersecurity — SHIPPED same day**: NIST NVD (keyless) as `nvd`
        source, docs-oficiales tier — CVE records are the certified source
        for vulnerability/breach claims. Follow-up: CISA KEV catalog (free
        JSON, actively-exploited list).
      - **Nutrition (the verifiable core of "food") — WORTH IT**: USDA
        FoodData Central (free key) for "X has more protein than Y" claims.
        Recipes themselves are procedures, not factual claims — no verdict
        to check, out of scope.
      - **How-to/build guides — DEFERRED**: wikiHow is NC-licensed with no
        API; procedures mostly aren't claims. The verifiable slice (technical
        how-tos) is already covered by docs-oficiales.
      - **Podcasts — FOLDED into the video-transcripts workstream**: no
        transcript APIs exist generally; same Whisper-cost gate applies.
      - **Tweets of scientists — NOT VIABLE as X/Twitter**: the API has been
        paid-only since 2023, no keyless tier, scraping violates ToS.
        Honest alternative: **Bluesky (keyless AT Protocol API) and Mastodon
        (keyless public APIs)** where scientific communities increasingly
        post; plus expert statements already reach us via news/GDELT/
        Wikiquote. Open question flagged: expert identity ≠ authority on
        truth — expertise weighting needs the same care as source priors.
- [ ] **National statistics offices — the certifying authorities themselves
      (Jeffrey, 2026-07-08).** For "country X's inflation/unemployment/
      population is Y" claims, the national office isn't A source, it's THE
      source. Keyless/free shortlist: INE Spain (keyless JSON — priority for
      the Spanish-language mission, with INEGI+Banxico Mexico, free token);
      US BLS/Census/CDC; UK ONS; Eurostat. **Scaling insight: connect
      platforms, not countries** — most governments run CKAN, Socrata or
      OData standard portals, so three connectors cover hundreds of portals
      (datos.gob.mx, data.gov, datos.gob.es, data.gov.uk…). Caveats: the
      query-translation problem applies double (per-office indicator
      taxonomies → LLM translator design carries over), and official
      statistics LAG — a claim about last month may predate the certified
      number, which is an honest NEI, not a failure. The .gov/.gob 2x domain
      prior already up-weights these pages when web search finds them; a
      dedicated connector would raise them to docs-oficiales tier (8x).
- [ ] **Public statistical databases as certified sources (Jeffrey's idea,
      2026-07-08)** — the docs-oficiales equivalent for number claims, where
      web search returns blogspam arguing about the number and the database
      IS the number. Keyless shortlist by claim genre: WHO Global Health
      Observatory (health statistics — the biggest misinformation genre);
      World Bank/Eurostat/UN SDG (economic claims; World Bank measured
      flaky, silent-fail handles it); USGS earthquakes + NOAA/NASA climate
      (disaster and record claims against the instrument record); Interpol
      public notices ("X is wanted" viral defamation); GLEIF LEI (company
      existence). **The real engineering problem is query translation, not
      API access**: a claim says "unemployment doubled", the API wants
      indicator SL.UEM.TOTL.ZS + country + years. Design: router flags
      statistical claims, the existing LLM question-generator translates
      free text → structured lookup (same pattern as sub-question
      generation), result enters as docs-oficiales-tier evidence.
- [ ] **Time-dimension and unconventional sources (2026-07-08).** Everything
      in the current registry answers "what do sources say NOW"; these add
      axes nothing else covers. In value order:
      1. **Wayback Machine (Internet Archive)** — evidence with a time
         dimension, keyless API. Three distinct capabilities: deleted
         content ("X said Y then deleted it" — the archive is often the
         only surviving evidence, and deletion is itself signal); temporal
         claims ("the site said X in March 2020" — unverifiable against
         today's version); and dead-link resurrection (recover 404'd
         evidence URLs from snapshots instead of silently dropping them —
         a recall improvement to the whole existing pipeline).
      2. **SEC EDGAR** — keyless full-text search of company filings;
         primary source for "company X reported/did Y" claims.
      3. **Retraction Watch (now free via Crossref)** — flags claims citing
         since-retracted studies ("zombie science"), a misinformation genre
         nothing else in the registry detects.
      4. **Our World in Data** — curated keyless statistics for "country X
         has the highest Y" claims, where web search returns mostly
         blogspam.
- [ ] **Community sources — Reddit as index, not testimony (Jeffrey's idea,
      2026-07-08).** Moderated communities (r/AskHistorians, r/science,
      r/OutOfTheLoop) are often the fastest aggregators of PRIMARY sources
      for emerging viral claims — tracing a manipulated image or fabricated
      quote hours before fact-checkers publish. Design: search threads about
      the claim, extract URLs cited in top comments, fetch THOSE as evidence
      under their own domains' priors (Reddit-as-index); any direct Reddit
      text enters at a deliberately sub-1.0 prior (~0.3–0.5x, new tier below
      PESO_BASE). Existing safeguards already bound the risk: one-domain-one-
      voice caps all of reddit.com at a single vote, and tie-breaking
      requires a reliable voice, so weak sources add signal but can never
      overturn a fact-checker. Explicitly REJECTED in the same analysis:
      article/YouTube comments — unmoderated, trivially manipulable
      (bots/brigading), and viral lies are seeded there, so ingesting them
      imports the disinformation being judged (the echo problem again).
      Reddit's moderation/threading/vote structure is different in kind.
      Live-pipeline enrichment only — does not move offline benchmark numbers.
- [ ] **Video subtitles/transcripts as an evidence family (Jeffrey's idea,
      2026-07-08).** A large share of viral claims are about what someone
      said on camera; transcripts are the PRIMARY source for that genre,
      strictly better than secondary reporting, and they're just text —
      zero new models, flows straight into the existing passage→NLI→
      aggregator pipeline as one more FUENTES family. YouTube transcripts
      are fetchable keyless. Design notes: prefer manually-uploaded
      subtitles over noisy auto-captions; add an aggregator rule
      distinguishing attribution claims ("X said Y" — transcript is
      near-decisive) from content claims (the truth of Y — transcript is
      one more voice); captions-only in v1, NO local Whisper transcription
      until a measured miss-rate justifies the GPU cost.
- [ ] **Extraction purity workstream (requested by Jeffrey, 2026-07-08):
      close the measured quality gap between live-scraped evidence and the
      knowledge store's.** The live pipeline already uses trafilatura (best
      open-source main-content extraction) but the store's evidence is still
      cleaner, and part of tonight's 47→56% gain came from its sentence-level
      segmentation vs. our ~600-char chunks (which can glue a decisive
      sentence to irrelevant neighbors, diluting the NLI signal). Concrete
      pieces, in value order:
      1. **Extraction benchmark first**: the knowledge store doubles as a
         gold standard for extraction itself — it has the URLs AND the
         professionally-extracted sentences for thousands of real pages.
         Fetch the same URLs, run our extractor, score against the store's
         output. Makes every extraction change below measurable instead of
         a matter of taste (the project's philosophy applied to its own
         plumbing).
      2. Sentence-level segmentation of extracted pages (replace flat
         600-char chunking for ranking/selection; keep surrounding context
         when handing passages to the verifier).
      3. PDF support (government/scientific sources publish decisive
         documents as PDFs; currently invisible to us).
      4. Headless-browser fallback for JavaScript-rendered pages (real
         complexity/latency cost — measure how often it's actually needed
         via the benchmark in 1 before paying it).

**Success criterion:** measurable improvement on AVeriTeC's "conflicting evidence"
class, the hardest in the benchmark.

### Cross-benchmark generalization (does AVeriTeC tuning overfit?)

- [x] **SciFact (2026-07-09): 55.0% accuracy, F1 macro 0.528, oracle
      retrieval.** A second certified benchmark — scientific claims vs.
      peer-reviewed abstracts — as an honest overfitting check on a verifier
      (v8) never trained on scientific language. `evaluation/eval_scifact.py`
      hands it the gold cited abstract and scores the predicted label
      (SUPPORT/CONTRADICT/NEI), isolating judgment from retrieval. Read
      honestly: NEI is the strongest class (F1 0.613) but **63 SUPPORT and
      33 CONTRADICT claims are called NEI** — scientific abstracts hedge
      ("may suggest", "is associated with"), so no single sentence clears
      the entailment threshold, and the model has never seen this register.
      This is a genuine domain gap, deliberately NOT tuned away by lowering
      the threshold to fit this test set (the overfitting sin avoided all
      campaign). It says the AVeriTeC gains didn't come from overfitting
      (the core transfers — 55% cold on a new domain), and points the next
      training-data lever at scientific-register SUPPORT/CONTRADICT pairs.
      FEVER and a fresh LLM-AggreFact-on-v8 are the remaining cross-checks.
- [x] **Verifier v10 (scientific-register pairs) PROMOTED — the first
      verifier to improve two benchmarks at once (2026-07-09).**
      `generate_scifact_pairs.py` converts SciFact TRAIN's human-annotated
      rationales into verifier pairs (+ balanced mechanical NEI), v8's
      shortcut-proofing recipe applied; the rejected v9 temporal pairs were
      dropped from the mix. Measured everywhere: **SciFact dev 55.0→63.7
      (+8.7, F1 0.528→0.611)** — the target; **AVeriTeC-500 62.0→62.6,
      new accuracy best**, with both major classes up (Supported 0.388→0.406,
      Refuted 0.767→0.769); AggreFact 65.1 (flat); VitaminC 88.14 (flat).
      Honest cost, documented: the two smallest AVeriTeC classes eroded
      (NEI 0.143→0.087, Conflicting 0.140→0.100 — macro-F1 0.360→0.341),
      accepted because the mission is explicitly multi-domain and v10
      gained an entire scientific register at zero cost to general
      grounding. v8 archived at `models/verificador-v0-v8-archivado`.
      Full-500 series: 44.0 → 55.0 → 62.0 → 62.6.

- [x] **FEVER (2026-07-09): 77.7% accuracy, F1 macro 0.773 — the strongest
      benchmark number yet, and the three-leg generalization map is
      complete.** Balanced 999-claim sample of FEVER dev, oracle retrieval
      via copenlu/fever_gold_evidence (inlined gold sentences — no 3 GB wiki
      dump), production v10. Per-class: SUPPORTS F1 0.864, REFUTES 0.780,
      NEI 0.676 (weakest — its "gold" evidence comes from a retrieval
      system, so related-but-non-probative text sometimes reads REFUTA).
      **The map, honestly read**: FEVER 77.7% (Wikipedia register — the
      verifier's home domain, VitaminC is built from Wikipedia edits) >
      SciFact 63.7% (scientific register, learned this campaign) ≈
      AVeriTeC-500 62.6% (viral/political 4-class, the hard one). The
      ~15-point FEVER-to-AVeriTeC gap quantifies what AVeriTeC's difficulty
      actually is: not the verifier's comparative skill (strong at home),
      but real-world claim noise, 4-class ambiguity, and evidence quality.
      `evaluation/eval_fever.py`.

- [x] **Verifier v11 (FEVER-register pairs) — FEVER 86.0% (+8.3), but NOT
      promoted for production: AVeriTeC regressed below the pre-set bar
      (2026-07-10).** The third straight register-transfer win on its target:
      FEVER 77.7→86.0 (F1 macro 0.861), with SciFact (64.3), AggreFact
      (65.7) and VitaminC (88.69, campaign best) all nudging up. But the
      decisive AVeriTeC-500 landed at **60.2% vs v10's 62.6** — below the
      promotion rule fixed before the number existed (≥62.0, holding the
      majority-baseline crossing) — so **v10 stays production** and v11 is
      archived as the FEVER specialist (`models/verificador-v11`,
      selectable via `AIDAM_MODELO_VERIFICADOR`). Honest reading —
      **register interference is now a measured phenomenon**: 30k
      Wikipedia-register pairs (3.5× the AVeriTeC in-domain set) pulled the
      model toward encyclopedic style at the viral-claim register's
      expense; macro-F1 actually rose (0.341→0.352, Supported F1 0.436 =
      campaign best) while accuracy fell — the mix rebalanced toward
      minority classes as Refuted recall dropped. Next-session experiment:
      a smaller FEVER dose (~10k) to find the interference-free ratio, and
      the mmBERT long-context backbone as the deeper fix for register
      crowding in a 279M-capacity model.

- [x] **Verifier v12 (40k DocNLI long-document pairs @ 512 tokens) —
      REJECTED: a label-poisoning mechanism found the hard way (2026-07-10).**
      The long-document thesis was directionally right: AggreFact 65.1→66.0
      (project best), AggreFact-CNN 50.1→54.1 (+4, no longer coin-flip),
      SciFact/AVeriTeC-100 held, and the 512-token training fixed a silent
      train/eval length mismatch. **But FEVER collapsed 77.7→48.1**, and the
      mechanism is precise: DocNLI is itself built partly FROM FEVER/ANLI,
      with contradiction pairs relabeled `not_entailment` — our
      "conservative" not_entailment→NEI mapping therefore taught the model
      that FEVER-style refutations are NEUTRAL. Anti-refutation training,
      injected by provenance we didn't audit. MiniCheck-FT5 (74.7) remains
      unbeaten. **v13 design, from the lesson**: (a) audit mined datasets'
      provenance before mapping labels — DocNLI rows deriving from
      contradiction sources must be dropped, not relabeled; (b) the honest
      long-document negatives are purpose-built D2C synthetic data (local
      LLM generates multi-sentence-composition claims from real documents,
      the actual MiniCheck recipe) — hours of generation, now clearly
      required rather than optional. AggreFact-CNN's +4 from even
      contaminated long-doc data says the register lever is real.

- [x] **Verifier v13 (clean long-doc: 20k DocNLI-entailment + 4.5k D2C @512)
      — the poisoning fix VERIFIED, biggest AggreFact jump yet, but AVeriTeC
      again below the bar: NOT promoted (2026-07-11).** Scorecard:
      **AggreFact 65.1→68.7 (+3.6, largest single gain on this benchmark;
      AggreFact-CNN 50.1→60.4 cumulative)**, FEVER 78.4 (fully recovered
      from v12's poisoned 48.1 AND above v10's 77.7 — provenance filtering
      + purpose-built D2C negatives preserve the refute boundary exactly as
      designed), VitaminC 88.22, SciFact 62.7 (−1, sample noise),
      AVeriTeC-100 screen 68.0 (best ever) — **but the full 500: 61.0/0.355
      vs v10's 62.6/0.341**, below the standing ≥62.0 bar. v10 stays
      production for AVeriTeC; v13 archived as the grounding/long-document
      champion. Two structural notes: (1) the 100-screen ran hot for the
      fourth time — it is hereby demoted to a smoke test only, never an
      argument for promotion; (2) production selection is now genuinely
      multi-objective — the AVeriTeC-optimal and grounding-optimal models
      have diverged, which the cascade design (route by claim register)
      could eventually reconcile. Also this cycle: trainer gained
      --reanudar (v13's first run died at 80% to a GPU watchdog kill;
      resume from checkpoint-13000 saved ~75 min; a hot driver update was
      the likely culprit — nvidia-smi showed version mismatch until reboot).
      **D2C dose-response established: 4.5k pairs → +2.7 AggreFact. v14
      scales the dose (3k more groups: XSum register + fresh CNN/DM).**

- [x] **Verifier v14 (triple D2C dose: 13.5k pairs, XSum + fresh CNN/DM) —
      new grounding champion, diminishing returns measured (2026-07-11).**
      AggreFact 68.7→**69.7** (series 65.1→66.0→68.7→69.7 — now 5.0 from
      MiniCheck-FT5), FEVER 78.7 (best), SciFact 63.7 (back to v10 level),
      VitaminC 88.28. Strictly dominates v13 everywhere. Dose-response,
      honestly: first 4.5k D2C pairs bought +2.7; the next 9k bought +1.0 —
      the flat-dose axis is saturating, and the remaining 5-point gap
      likely needs the architecture lever (mmBERT 8k-context: whole
      documents in one pass instead of chunk-and-max). Batch-efficiency
      decision: instead of a 1.5h AVeriTeC-500 per candidate, ONE decisive
      500 runs on the best of v15/v16 at the end of this batch.
- [x] **AVeriTeC-100 screen formally demoted to smoke test** (ran hot four
      consecutive times: 66→62.6, 61→60.2, 68→61.0, 63→— vs full-500).
      Promotion arguments must cite the 500 only.

- [x] **Verifier v15 (v14 mix + 10k FEVER small dose) — best generalist of
      the campaign; the register trade-off is now a LAW of this backbone
      (2026-07-11).** Three simultaneous project bests: **AggreFact 70.0**
      (4.7 from MiniCheck-FT5), **FEVER 81.7** unified (+3.0 from a third
      of v11's interfering dose — the 10k dose works), **SciFact 66.3**;
      VitaminC 88.40. But AVeriTeC-500: 60.6 — below the 62.0 bar, the
      third grounding-optimized model in a row to trade viral-claim
      accuracy for grounding gains (v13 61.0, v14 unmeasured-by-policy,
      v15 60.6 vs v10's 62.6). **Conclusion: within a 279M fixed-capacity
      backbone, AVeriTeC-optimal and grounding-optimal are different
      models. Production stays multi-objective: v10 for AVeriTeC, v15 as
      generalist. The cascade (route by claim register) reconciles them at
      the system level; the mmBERT experiment (v16) tests whether a
      bigger-context backbone dissolves the trade-off at the model level.**
- [x] Jeffrey's standing order (2026-07-11): do NOT shut down — the goal is
      now to BEAT the published marks, starting with MiniCheck-FT5 74.7 on
      AggreFact. v16-mmBERT (8k context, whole-document single-pass) is the
      designated assault.

- [x] **Verifier v16-mmBERT (backbone experiment, first iteration) — a
      promising ALMOST, hypothesis corrected by measurement (2026-07-11/12).**
      mmBERT-base (308M, 8k context) trained from a raw encoder (fresh NLI
      head, MNLI raised to 150k as partial compensation for the missing
      2.7M-pair NLI pretraining), 1024-token training. Results vs v15:
      AggreFact chunked 69.6 (vs 70.0), FEVER 81.3 (vs 81.7), SciFact 63.0
      (vs 66.3), VitaminC 87.55 (vs 88.40) — behind on everything, but by
      0.4-3 points while missing millions of NLI pretraining pairs: **per
      point of NLI base, the backbone outperforms**. The headline negative:
      **whole-document single-pass @4096 scored 67.1, LOSING to its own
      chunk-and-max @512 (69.6)** — the 8k-context advantage does not
      materialize for free. Diagnosis: training data is mostly short pairs
      and training ran @1024, so 4096-token evaluation is length
      extrapolation the model never saw; windowed max-pooling meanwhile
      acts as an evidence locator that single-pass dilutes. **The corrected
      recipe for iteration two: (1) massive NLI pre-phase first (full MNLI
      + XNLI + ANLI, ~1M+ pairs) to close the base gap, (2) genuinely long
      D2C training documents (3-4k chunks) so long-context inference is
      in-distribution.** v15 remains the generalist champion; MiniCheck-FT5
      74.7 still stands, gap 4.7.

- [x] **Verifier v17-mmBERT: PROMOTED to generalist champion — the NLI
      pre-phase validated end to end (2026-07-11).** Two-phase recipe from
      the v16 verdict: phase 1 = massive NLI foundation (full MNLI 393k +
      ANLI 163k + VitaminC 120k @256, new trainer flags --anli
      --sin-mezcla), phase 2 = the EXACT v16 mix (376,729 examples,
      @1024, 2 epochs) so every delta is attributable to the pre-phase.
      Results: **AggreFact 70.3 (new best**, v15 70.0, v16 69.6; gap to
      MiniCheck-FT5 now 4.4), **FEVER 83.2 (new unified best**, v15 81.7;
      specialist v11 86.0 still ahead), VitaminC 88.7 (v15 88.4). The
      phase-1 checkpoint alone hit 88.81 VitaminC — 556k fresh NLI pairs
      closed the entire base gap to the 2.7M-pair mDeBERTa lineage.
      Whole-document @4096 improved 67.1 → 69.6: the strong base recovered
      most of the single-pass deficit, but chunk-and-max (70.3) still wins
      — the remaining -0.7 is length extrapolation (trained @1024). Open
      question: **SciFact stuck at 63.0 in BOTH mmBERT versions** (v15:
      66.3) — the scientific register resists this backbone. Per-subset
      breakdown points the next lever: AggreFact-CNN 52.8 and ExpertQA
      57.6 (n=3,702) are the two craters; ExpertQA + SciFact share the
      expert/technical register that news D2C never covered. **Next: D2C
      over scientific abstracts (new register = the transfer playbook
      that won v8/v10/v11), targeting ExpertQA, SciFact and the CNN
      crater at once.**

### Backbone and pipeline ideas from the field (2026-07-09, via Jeffrey)

- [ ] **mmBERT/ModernBERT backbone experiment** — prompted by reviewing
      halugate-sentinel (a Stage-0 "does this prompt need fact-checking"
      router on ModernBERT; NOT a verifier — it would sit in front of a
      system like AIDAM, not replace it). The transferable insight is the
      backbone: mmBERT (multilingual ModernBERT) has **8,192-token native
      context** vs mDeBERTa's 512 — our entire long-document weakness
      (AggreFact-CNN 50.3%, the chunk-and-max hack) is an architectural
      limit that backbone dissolves: whole documents judged in one pass.
      Cost: no NLI-pretrained head exists, so the full recipe retrains from
      a raw encoder — a weekend-scale GPU experiment with real risk.
      Candidate after the current data-register campaign plateaus.
- [ ] **Trained Stage-0 verification gate** for the Phase 4 compound agent:
      most user requests (code/creative/opinion) shouldn't pay the
      verification tax. Current opinion filter is regex; halugate proves
      ~100M params and 50k prompts suffice for a 96%+ intent gate. Connects
      to the ask-don't-guess design principle.
- [ ] **HaluEval / FaithDial as additional grounding registers** for the
      AggreFact push — unmined public sources their card lists.

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
      — code is the one domain where verification needs no sources: execution
      is ground truth. Correctness = the task's tests pass (observation, not
      opinion); efficiency = measured time/peak memory at SEVERAL input sizes
      (observe the real scaling curve — catch the O(n²) behind code that
      "looks fine"). Benchmark corpus (Jeffrey asked re: LeetCode, 2026-07-08):
      not LeetCode itself (ToS/closed content) — the open equivalents:
      HumanEval + MBPP (open, tests included), LiveCodeBench (continuously
      refreshed → contamination-resistant), SWE-bench (real GitHub issues
      with real test suites). Separately: GitHub repos/changelogs/issues as
      primary sources for claims ABOUT code ("X deprecated Y in vZ", CVE
      claims) — the docs-oficiales of software history; free token when built.
- [ ] Code generator: small quantized Qwen3-Coder (Q4) on a consumer GPU
- [ ] Best-of-N loop: N candidates → execution-based score → the best survives;
      if none passes, retry with the failure feedback
- [ ] "Efficiency mode": the score includes measured time and memory, not just
      correctness
- [ ] Anchored writing: all generated text passes through Module 3 before delivery
- [ ] Images: orchestrate local FLUX.2 Klein / Z-Image Turbo + prompt-adherence score
- [ ] **Design principle (2026-07-08, not yet buildable — no generation module
      exists yet): ask, don't guess, when a request is genuinely unanswerable
      without missing context — brief and conversational, never a form.**
      Example: "give me code for iterating arrays" needs a language; a vague
      fact-check claim ("the president signed the bill") may need a country
      or date. The bar is *unanswerable without it*, not merely *improvable
      with it* — if a reasonable default exists, generate against the
      default rather than asking. This applies system-wide (fact-checking's
      interactive CLI mode included, not just generation) and should be
      designed in from day one of Phase 4 rather than retrofitted later.

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

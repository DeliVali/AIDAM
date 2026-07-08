# Annotated state of the art (July 2026)

References behind every AIDAM design decision. Each entry says *what it teaches us*
for this project.

## Incorporated into the system (July 2026)

- **MiMo-7B-RL (Xiaomi)** — [GitHub](https://github.com/XiaomiMiMo/MiMo) ·
  [quantized GGUF](https://huggingface.co/jedisct1/MiMo-7B-RL-GGUF)
  7B reasoning model at o1-mini level, open source, Q4-quantized at ~4.7 GB — runs
  on the project's consumer GPU via llama.cpp.
  → *Our first search-question generator (`aidam/questions.py`); candidates are
  swappable via `AIDAM_MODELO_PREGUNTAS` (DeepSeek-R1-0528-Qwen3-8B, MIT, is the
  current best in its class). Required trick: empty `<think></think>` prefill,
  because RL reasoning models spend hundreds of tokens thinking before answering.*

- **AVeriTeC 2.0 Shared Task (ACL 2025)** — [paper](https://aclanthology.org/2025.fever-1.15/)
  Winner CTU AIC with a 33.17% AVeriTeC score (strict metric with evidence quality;
  not comparable to plain accuracy). Technique shared by the top systems:
  **per-claim question generation** to guide retrieval — instead of searching the
  literal claim (which returns pages repeating it), ask what would confirm or refute
  it. → *Implemented behind the CLI's `--preguntas` flag.*

- **Synthetic hard negatives / Auto-GDA** — [Auto-GDA (Amazon)](https://arxiv.org/pdf/2410.03461) ·
  [claim matching with LLMs](https://arxiv.org/pdf/2402.05904)
  The published recipe for our measured failure (same-topic passages judged as
  contradiction): generate pairs "topically aligned, semantically irrelevant".
  → *`training/generate_neutrals.py` builds them mechanically from VitaminC's
  structure (same page, different fact) — 30k pairs without needing an LLM.*

- **2026 training tooling** — [overview](https://codersera.com/blog/fine-tuning-llms-complete-guide-2026/)
  Unsloth (QLoRA on a 6 GB GPU, Triton kernels), TRL v1.0 (unified SFT/DPO/GRPO),
  Axolotl with quantization-aware training. → *For when our own generative models
  arrive (neural decomposer, Phases 3-4); the 280M encoder verifier doesn't need them.*

## Small specialized verifiers (Module 3)

- **MiniCheck** — [arXiv:2404.10774](https://arxiv.org/abs/2404.10774) ·
  [GitHub](https://github.com/Liyan06/MiniCheck) (EMNLP 2024)
  770M params ≈ GPT-4 at fact-checking, 400x cheaper. The recipe: synthetic data
  generated with a strong LLM, with challenging factual errors that require composing
  information across sentences. Introduces the **LLM-AggreFact** benchmark.
  → *Our base recipe for Phase 1 and the baseline to beat.*

- **ClaimCheck** — [arXiv:2510.01226](https://arxiv.org/pdf/2510.01226)
  Real-time fact-checking with small models. Confirms the SLM-verifier direction is
  still active and competitive in 2025-2026.

- **Distilling Step-by-Step** — [Google Research](https://research.google/blog/distilling-step-by-step-outperforming-larger-language-models-with-less-training-data-and-smaller-model-sizes/)
  A 770M T5 beats PaLM-540B on specific tasks by distilling *rationales* (reasoning
  steps), not just labels. → *When generating synthetic data, keep the teacher LLM's
  reasoning, not just the verdict.*

## Decomposition and verification pipelines (Modules 1, 2)

- **VeriScore** — [arXiv:2406.19276](https://arxiv.org/pdf/2406.19276)
  Extracts only *verifiable* claims (not opinions) and verifies them with web search.
  → *Foundation of the Decomposer.*

- **VeriFastScore** — [arXiv:2505.16973](https://arxiv.org/html/2505.16973)
  Decomposition + verification in a single model pass. → *Phase 5 optimization.*

- **DnDScore** — [arXiv:2412.13175](https://arxiv.org/pdf/2412.13175)
  Decontextualization (resolving references before verifying) matters: atomic facts
  without context verify poorly. → *Decomposer requirement.*

- **SAFE (Search-Augmented Factuality Evaluator)** — DeepMind
  Decomposes into atomic facts and generates per-fact targeted search queries.
  → *Retriever pattern: one search per atomic fact, not per full claim.*

## Real-world claim verification (Module 4)

- **AVeriTeC / FEVER 2025 Shared Task** — [fever.ai/2025/task.html](https://fever.ai/2025/task.html) ·
  [description](https://arxiv.org/html/2410.23850v1)
  The serious benchmark: real claims, web evidence, and 4 verdicts —
  **supported / refuted / not enough evidence / conflicting evidence &
  cherry-picking**. 2025 edition: open LLMs only, reproducible, <1 min per claim.
  → *Our 4 verdict classes and our latency budget come from here.*

- **HerO 2 (Team HUMANE, AVeriTeC 2025)** — [arXiv:2507.11004](https://arxiv.org/html/2507.11004v1)
  Efficient top system built on open LLMs. → *A real winning-architecture reference
  for Phase 0.*

- **Ev2R** — [arXiv:2411.05375](https://arxiv.org/html/2411.05375v2)
  How to evaluate the quality of retrieved evidence. → *Retriever metric.*

## Extreme quantization (Phase 5)

- **BitNet b1.58 2B4T** — [technical report](https://arxiv.org/pdf/2504.12285) ·
  [HuggingFace](https://huggingface.co/microsoft/bitnet-b1.58-2B-4T) ·
  [analysis](https://www.emergentmind.com/topics/bitnet-b1-58)
  Ternary weights {-1,0,+1}, ~1.58 bits/weight, competitive with fp16 at 2B params /
  4T tokens. Requires **training from scratch** with QAT — it is not a post-hoc
  conversion. CPU inference with `bitnet.cpp`.
  → *Realistic path: fine-tune the published 2B4T, not pre-train our own.*

## Training efficiency (cross-cutting)

- **Liger Kernel** — [arXiv:2410.10989](https://arxiv.org/pdf/2410.10989)
  Fused Triton kernels (RMSNorm, RoPE, SwiGLU, FusedLinearCrossEntropy):
  ~60% less memory, ~20% more throughput, trivial install on PyTorch/HF.
  → *Applies from the first Phase 1 fine-tune.*

- **FlashAttention-3** — [technical notes](https://notes.suhaib.in/docs/tech/latest/breaking-the-bottleneck-how-flashattention-3-unlocks-the-full-power-of-nvidia-hopper-gpus/)
  2x over FA-2, but requires Hopper GPUs (H100). On consumer GPUs use FA-2 / PyTorch
  SDPA. Complementary to Liger (attention vs. the rest of the layers).

## Verified generation and test-time compute (Modules 6–7, Phase 4)

- **Scaling LLM Test-Time Compute Optimally** — [arXiv:2408.03314](https://arxiv.org/abs/2408.03314) (ICLR 2025)
  At matched FLOPs, a small model + search guided by a process verifier beats a model
  **14x larger**; the compute-optimal strategy improves efficiency >4x over naive
  best-of-N. → *The mathematical justification of the generate→verify→select loop.*

- **GenPRM** — [arXiv:2504.00891](https://arxiv.org/abs/2504.00891)
  A 1.5B generative verifier beats GPT-4o on ProcessBench by scaling its own inference
  compute. → *The verifier can also "think harder" when the decision is hard.*

- **Generative Verifiers** — [arXiv:2408.15240](https://arxiv.org/pdf/2408.15240)
  Modeling verification as next-token prediction lets the verifier reason before
  scoring. → *Candidate architecture for Module 7.*

- **T1: Tool-integrated Verification for SLMs** — [arXiv:2504.04718](https://arxiv.org/pdf/2504.04718)
  Tool-based verification (code execution) to scale test-time compute in small models.
  → *Exactly our code verifier.*

- **SLMs are the Future of Agentic AI (NVIDIA, 2025)** — [technical blog](https://developer.nvidia.com/blog/how-small-language-models-are-key-to-scalable-agentic-ai/)
  SLMs: 10–30x cheaper to serve, fine-tuned in hours, more reliable at structured
  outputs. Recipe: one specialized SLM per sub-task; a large LLM only for planning,
  distilled away when possible. → *The design rule of the whole compound system.*

- **Qwen3-Coder / Qwen3-Coder-Next** — [GitHub](https://github.com/QwenLM/Qwen3-Coder) ·
  [technical report](https://arxiv.org/pdf/2603.00729)
  80B MoE with only 3B active; fits on a consumer GPU at Q4. Trained on ~800k tasks
  where ground truth is *a test passing in Docker* — execution-feedback learning at
  scale. → *Phase 4 code generator, and validation that "execution is the referee"
  works even for training.*

- **Efficient open image models (2026)** — [comparison guide](https://www.bentoml.com/blog/a-guide-to-open-source-image-generation-models)
  FLUX.2 Klein 4B (distilled from the 32B, ~8 GB VRAM, Apache 2.0), Z-Image Turbo 6B
  (8 inference steps, seconds on a 16 GB card), SD 3.5 Large Turbo (4 steps).
  → *Orchestrated as tools; we do not train image models.*

## SLM landscape

- **Small Language Models survey** — [ACM TIST](https://dl.acm.org/doi/10.1145/3768165)
  Specialized models often beat general LLMs in their domain because their entire
  parameter budget concentrates on that task's patterns.
  → *The academic justification of the whole project.*

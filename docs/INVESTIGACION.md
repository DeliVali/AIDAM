# Estado del arte anotado (julio 2026)

## Incorporado al sistema (julio 2026)

- **MiMo-7B-RL (Xiaomi)** — [GitHub](https://github.com/XiaomiMiMo/MiMo) ·
  [GGUF cuantizado](https://huggingface.co/jedisct1/MiMo-7B-RL-GGUF)
  Modelo de razonamiento de 7B a nivel o1-mini, open source, cuantizado Q4 en
  ~4.7 GB — corre en la GPU de consumo del proyecto vía llama.cpp.
  → *Es nuestro generador de preguntas de búsqueda (`aidam/preguntas.py`).
  Truco necesario: prefill de `<think></think>` vacío, porque el modelo RL gasta
  cientos de tokens razonando antes de responder.*

- **AVeriTeC 2.0 Shared Task (ACL 2025)** — [paper](https://aclanthology.org/2025.fever-1.15/) ·
  ganador CTU AIC con 33.17% de AVeriTeC score (métrica estricta con calidad de
  evidencia; no comparable con exactitud simple). Técnica común a los sistemas
  punteros: **generación de preguntas por afirmación** para dirigir la
  recuperación — en vez de buscar la afirmación literal (que devuelve páginas
  que la repiten), preguntar lo que la confirmaría o refutaría.
  → *Implementado con MiMo en el flag `--preguntas` de la CLI.*

- **Hard negatives sintéticos / Auto-GDA** — [Auto-GDA (Amazon)](https://arxiv.org/pdf/2410.03461) ·
  [claim matching con LLMs](https://arxiv.org/pdf/2402.05904)
  La receta publicada para nuestro fallo medido (pasajes del mismo tema juzgados
  como contradicción): generar pares "alineados en tema, irrelevantes en
  semántica". → *`training/generar_neutrales.py` los fabrica mecánicamente desde
  la estructura de VitaminC (misma página, hecho distinto) — 30k pares sin
  necesitar LLM.*

- **Herramientas de entrenamiento 2026** — [panorama](https://codersera.com/blog/fine-tuning-llms-complete-guide-2026/)
  Unsloth (QLoRA en GPU de 6 GB, kernels Triton), TRL v1.0 (SFT/DPO/GRPO
  unificados), Axolotl con quantization-aware training. → *Para cuando toquen
  modelos generativos propios (descompositor neuronal, Fase 3-4); el verificador
  encoder de 280M no los necesita.*

Referencias que sostienen cada decisión de diseño de AIDAM. Cada entrada dice *qué nos
enseña* para este proyecto.

## Verificadores pequeños especializados (Módulo 3)

- **MiniCheck** — [arXiv:2404.10774](https://arxiv.org/abs/2404.10774) ·
  [GitHub](https://github.com/Liyan06/MiniCheck) (EMNLP 2024)
  770M params ≈ GPT-4 en fact-checking, 400x menos costo. La receta: datos sintéticos
  generados con un LLM fuerte, con errores factuales desafiantes que exigen componer
  información entre frases. Introduce el benchmark **LLM-AggreFact**.
  → *Es nuestra receta base para la Fase 1 y nuestro baseline a superar.*

- **ClaimCheck** — [arXiv:2510.01226](https://arxiv.org/pdf/2510.01226)
  Fact-checking en tiempo real con modelos pequeños. Confirma que la dirección
  SLM-verificador sigue activa y competitiva en 2025-2026.

- **Distilling Step-by-Step** — [Google Research](https://research.google/blog/distilling-step-by-step-outperforming-larger-language-models-with-less-training-data-and-smaller-model-sizes/)
  T5-770M supera a PaLM-540B en tareas específicas destilando *racionales* (pasos de
  razonamiento), no solo etiquetas. → *Al generar datos sintéticos, guardar el
  razonamiento del LLM maestro, no solo el veredicto.*

## Pipelines de descomposición y verificación (Módulos 1, 2)

- **VeriScore** — [arXiv:2406.19276](https://arxiv.org/pdf/2406.19276)
  Extrae solo afirmaciones *verificables* (no opiniones) y las verifica con búsqueda web.
  → *Base del Descompositor.*

- **VeriFastScore** — [arXiv:2505.16973](https://arxiv.org/html/2505.16973)
  Descomposición + verificación en una sola pasada de modelo. → *Optimización de Fase 5.*

- **DnDScore** — [arXiv:2412.13175](https://arxiv.org/pdf/2412.13175)
  La decontextualización (resolver referencias antes de verificar) importa: hechos
  atómicos sin contexto se verifican mal. → *Requisito del Descompositor.*

- **SAFE (Search-Augmented Factuality Evaluator)** — DeepMind
  Descompone en hechos atómicos y genera consultas de búsqueda dirigidas por hecho.
  → *Patrón del Recuperador: una búsqueda por hecho atómico, no por afirmación completa.*

## Verificación de afirmaciones del mundo real (Módulo 4)

- **AVeriTeC / FEVER 2025 Shared Task** — [fever.ai/2025/task.html](https://fever.ai/2025/task.html) ·
  [descripción](https://arxiv.org/html/2410.23850v1)
  El benchmark serio: afirmaciones reales, evidencia web, y 4 veredictos —
  **supported / refuted / not enough evidence / conflicting evidence & cherry-picking**.
  Edición 2025: solo LLMs abiertos, reproducible, <1 min por afirmación.
  → *Nuestras 4 clases de veredicto y nuestro presupuesto de latencia vienen de aquí.*

- **HerO 2 (Team HUMANE, AVeriTeC 2025)** — [arXiv:2507.11004](https://arxiv.org/html/2507.11004v1)
  Sistema eficiente ganador con LLMs abiertos. → *Referencia de arquitectura ganadora
  real para la Fase 0.*

- **Ev2R** — [arXiv:2411.05375](https://arxiv.org/html/2411.05375v2)
  Cómo evaluar la calidad de la evidencia recuperada. → *Métrica del Recuperador.*

## Cuantización extrema (Fase 5)

- **BitNet b1.58 2B4T** — [informe técnico](https://arxiv.org/pdf/2504.12285) ·
  [HuggingFace](https://huggingface.co/microsoft/bitnet-b1.58-2B-4T) ·
  [análisis](https://www.emergentmind.com/topics/bitnet-b1-58)
  Pesos ternarios {-1,0,+1}, ~1.58 bits/peso, competitivo con fp16 a 2B params / 4T
  tokens. Requiere **entrenamiento desde cero** con QAT — no es una conversión post-hoc.
  Inferencia en CPU con `bitnet.cpp`.
  → *Camino realista: fine-tunear el 2B4T publicado, no pre-entrenar uno propio.*

## Eficiencia de entrenamiento (transversal)

- **Liger Kernel** — [arXiv:2410.10989](https://arxiv.org/pdf/2410.10989)
  Kernels Triton fusionados (RMSNorm, RoPE, SwiGLU, FusedLinearCrossEntropy):
  ~60% menos memoria, ~20% más throughput, instalación trivial sobre PyTorch/HF.
  → *Se aplica desde el primer fine-tuning en Fase 1.*

- **FlashAttention-3** — [notas técnicas](https://notes.suhaib.in/docs/tech/latest/breaking-the-bottleneck-how-flashattention-3-unlocks-the-full-power-of-nvidia-hopper-gpus/)
  2x sobre FA-2, pero requiere GPU Hopper (H100). En GPU de consumo usar FA-2 / SDPA
  de PyTorch. Complementario a Liger (atención vs. resto de capas).

## Generación verificada y cómputo en tiempo de inferencia (Módulos 6–7, Fase 4)

- **Scaling LLM Test-Time Compute Optimally** — [arXiv:2408.03314](https://arxiv.org/abs/2408.03314) (ICLR 2025)
  Con FLOPs igualados, un modelo pequeño + búsqueda guiada por un verificador de proceso
  supera a un modelo **14x más grande**; la estrategia compute-óptima mejora la
  eficiencia >4x sobre best-of-N ingenuo.
  → *La justificación matemática del bucle generar→verificar→seleccionar.*

- **GenPRM** — [arXiv:2504.00891](https://arxiv.org/abs/2504.00891)
  Un verificador generativo de 1.5B supera a GPT-4o en ProcessBench escalando su propio
  cómputo de inferencia. → *El verificador también puede "pensar más" cuando la decisión
  es difícil.*

- **Generative Verifiers** — [arXiv:2408.15240](https://arxiv.org/pdf/2408.15240)
  Modelar la verificación como predicción de siguiente token permite que el verificador
  razone antes de puntuar. → *Candidata a arquitectura del Módulo 7.*

- **T1: Tool-integrated Verification for SLMs** — [arXiv:2504.04718](https://arxiv.org/pdf/2504.04718)
  Verificación con herramientas (ejecución de código) para escalar test-time compute en
  modelos pequeños. → *Exactamente nuestro verificador de código.*

- **SLMs are the Future of Agentic AI (NVIDIA, 2025)** — [blog técnico](https://developer.nvidia.com/blog/how-small-language-models-are-key-to-scalable-agentic-ai/)
  SLMs: 10–30x más baratos de servir, fine-tuning en horas, más fiables en salidas
  estructuradas. Receta: SLM especializado por sub-tarea; LLM grande solo para planificar,
  y destilarlo cuando se pueda. → *La regla de diseño de todo el sistema compuesto.*

- **Qwen3-Coder / Qwen3-Coder-Next** — [GitHub](https://github.com/QwenLM/Qwen3-Coder) ·
  [informe técnico](https://arxiv.org/pdf/2603.00729)
  MoE 80B con solo 3B activos; cabe en una GPU de consumo con Q4. Entrenado con ~800k
  tareas donde la verdad terreno es *un test que pasa en Docker* — aprendizaje por
  feedback de ejecución a escala. → *Generador de código de la Fase 4, y validación de
  que "la ejecución es el árbitro" funciona hasta para entrenar.*

- **Modelos de imagen abiertos eficientes (2026)** — [guía comparativa](https://www.bentoml.com/blog/a-guide-to-open-source-image-generation-models)
  FLUX.2 Klein 4B (destilado del 32B, ~8 GB VRAM, Apache 2.0), Z-Image Turbo 6B
  (8 pasos de inferencia, segundos en una tarjeta de 16 GB), SD 3.5 Large Turbo (4 pasos).
  → *Se orquestan como herramientas; no entrenamos modelos de imagen.*

## Panorama SLM

- **Survey de Small Language Models** — [ACM TIST](https://dl.acm.org/doi/10.1145/3768165)
  Los modelos especializados superan a menudo a LLMs generales en su dominio porque todo
  su presupuesto de parámetros se concentra en los patrones de esa tarea.
  → *La justificación académica de todo el proyecto.*

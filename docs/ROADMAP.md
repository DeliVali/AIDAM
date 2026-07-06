# Roadmap de AIDAM

Regla general: **cada fase produce algo que funciona y se mide contra un benchmark
público**. Nada de arquitecturas en el aire durante meses.

## Fase 0 — Pipeline funcional con piezas existentes (2–4 semanas)

Construir el sistema completo de punta a punta usando modelos ya publicados. Esto valida
la arquitectura antes de entrenar nada, y nos da la línea base a superar.

- [x] Descompositor v0 (heurístico; el neuronal estilo VeriScore queda para Fase 1)
- [x] Recuperador: Wikipedia + búsqueda web, una voz por dominio (independencia)
- [x] Verificador: NLI multilingüe mDeBERTa-v3 (~280M) — elegido sobre MiniCheck
      porque funciona en español desde el día uno
- [x] Agregador v0: mayoría ponderada auditable, 4 clases de veredicto, con tests
- [x] CLI: `aidam verificar "afirmación"` → veredicto + citas (7.9 s por afirmación real)
- [x] **Evaluación AVeriTeC (2026-07-05, primeras 100 del dev)**: exactitud 30–31%,
      F1 macro 0.21–0.25 (baseline mayoritario: 61%). El número es duro y es el punto:
      ahora cada cambio se mide. Script en `evaluacion/eval_averitec.py` (recuperación
      viva, no la pista oficial del shared task). Pendiente: LLM-AggreFact.
      **Diagnóstico medido**: el fallo dominante es mentira viral → "sustentado"
      (25/100); en la mayoría de esos casos el fact-checker ni aparece en la evidencia,
      y cuando aparece, su snippet truncado *repite* la afirmación y el verificador lo
      lee como apoyo. El cuello de botella es la calidad de la evidencia (snippets),
      no la agregación.

**Criterio de éxito:** el pipeline completo verifica una afirmación real en <1 minuto
(el estándar del shared task de AVeriTeC 2025) y publica su puntuación.

**Estado (2026-07-06) — dev set completo (500 afirmaciones):**
- **AIDAM: 44.0% exactitud, F1 macro 0.318, 17.9 s/afirmación** (Refuted F1 0.604,
  Supported 0.390). Serie sobre las primeras 100: 30→31→37→39→41; sobre las 500: 44.
- **Duelo contra un modelo actual (2026) sin recuperación** — mismas 100 afirmaciones,
  MiMo-7B-RL con razonamiento libre y solo memoria paramétrica: **25.0% / F1 0.186 /
  63.7 s**. AIDAM: **41.0% / 0.274 / 20 s** → **+16 puntos y 3x más rápido**: la
  evidencia viva le gana al recuerdo. (`evaluacion/eval_baseline_llm.py`)
- Pendiente estructural: clase "contradictoria" sobre-predicha a escala (109 vs 38 de
  oro — el juez de omisión dispara de más; afinar su umbral), NEI débil (F1 0.142),
  y el techo del 61% mayoritario sigue arriba.

## Fase 1 — Entrenar el verificador propio (1–2 meses)

Replicar y luego intentar superar la receta MiniCheck con datos propios.

- [x] **v0 entrenado (2026-07-05)**: fine-tuning contrastivo sobre VitaminC (120k pares)
      desde el checkpoint NLI multilingüe, en una RTX 5070 (11 min).
      **VitaminC test: 73.3% → 88.8% exactitud, F1 macro 0.664 → 0.845.**
      Script en `training/entrenar_verificador.py`.
      ⚠️ Con transformers v5 (5.13) el entrenamiento colapsa a una sola clase
      (regresión de DeBERTa-v3); por eso `pyproject.toml` fija `<5`.
- [x] **v1 con neutral restaurado (2026-07-05)**: entrenar solo con VitaminC
      (contrastivo) volvió al modelo propenso a "refutar" con pasajes relacionados
      pero no probatorios — detectado conduciendo la CLI, no en el benchmark.
      Arreglo: mezcla 120k VitaminC + 60k MNLI. VitaminC test se mantiene (88.75%)
      y la sobre-refutación baja. Residuo conocido: intros enciclopédicas aún votan
      "contra" en ~70-79% — el objetivo #1 de los datos sintéticos es generar pares
      neutrales-difíciles (intro genérica × afirmación específica).
- [x] **v2 con neutrales-difíciles (2026-07-05)**: 30k pares mecánicos desde la
      estructura de VitaminC (misma página, hecho distinto — receta Auto-GDA,
      `training/generar_neutrales.py`). La refutación espuria del par medido cayó
      de 86% a 53% (bajo el umbral de señal); VitaminC test 88.21%.
      «Python lists are mutable»: REFUTADO 74% → SUSTENTADO 100%.
- [ ] Generador de datos sintéticos con LLM: errores factuales sutiles, multi-frase,
      multi-salto (los neutrales mecánicos de v2 son el primer paso)
- [ ] Datos de entrenamiento en español (VitaminC es inglés; el modelo conserva el
      español del checkpoint base, pero hay que medirlo y reforzarlo)
- [ ] Calibración de probabilidades + evaluación de abstención
- [ ] Publicar en HuggingFace con pesos abiertos

**Criterio de éxito:** ≥ MiniCheck-FT5 en LLM-AggreFact; primer verificador pequeño
competitivo en español.

## Fase 2 — Lógica comparativa seria (1–2 meses)

- [x] **Ampliación de fuentes (2026-07-05)**: registro extensible con 8 familias en
      paralelo — Wikipedia (mono y multilingüe), Wikinews, web abierta, Semantic
      Scholar, OpenAlex, arXiv y Europe PMC. *Verificado: afirmación médica juzgada
      con FDA, papers académicos en ambos lados, Wikinews y Wikipedia francesa,
      en 7.3 s.* Añadir una fuente = una función registrada (ver CONTRIBUTING).
- [x] **Recuperación multilingüe (2026-07-05)**: enlaces interlingüísticos de Wikipedia
      → evidencia en en/fr/de/ru/zh/… sin modelo de traducción; el verificador juzga
      pares cruzados de idioma directamente. `--max-idiomas` en la CLI.
      *Verificado: afirmación en español sustentada por las Wikipedias en inglés (96%)
      y alemán (95%).* Pendiente: ranking de relevancia cruzado con embeddings
      multilingües (hoy los idiomas lejanos aportan solo su introducción).
- [ ] Modelo de independencia de fuentes (detección de contenido sindicado/copiado)
- [x] **Priores de fiabilidad v0 + regla anti-eco (2026-07-05)**: fact-checkers pesan
      8x, enciclopedias/academia 2.5x, .gov/.edu 2x; y un snippet que solo repite la
      afirmación casi no pesa como soporte ("el eco no es evidencia"). Con tests.
      **Resultado A/B en AVeriTeC-100**: refutadas correctas 13→20, exactitud 30→31%,
      F1 macro bajó 0.25→0.21 (algunas afirmaciones ciertas ahora se refutan por
      desmentidos parciales). Ayuda, pero el techo lo pone la evidencia: ver siguiente.
- [x] **Evidencia de página completa + búsqueda dirigida a desmentidos (2026-07-05)**:
      texto completo de los mejores resultados (trafilatura) y consulta reformulada
      («\<afirmación\> fact check»). Con el resto de arreglos: AVeriTeC-100 30%→37%,
      Refuted F1 0.529, y «la Gran Muralla se ve desde la Luna» → REFUTADO 93%.
- [x] **Router de categorías + gate probatorio + eco recalibrado (2026-07-05)**:
      el agente elige fuentes por tema (programación→Stack Overflow, medicina→Europe
      PMC; las académicas son universales: un misroute añade ruido, nunca quita señal);
      los pasajes que no comparten ≥2 palabras de contenido con el hecho no se juzgan
      (las intros genéricas se leían como contradicción); el anti-eco solo aplica a
      afirmaciones largas (en las cortas, cobertura ≠ eco). Todo salió de un `/verify`
      en runtime que falló — cada regla tiene su test de regresión.
- [x] **Generación de preguntas de búsqueda (2026-07-05)**: MiMo-7B-RL de Xiaomi
      cuantizado (Q4, llama.cpp) genera las preguntas cuya respuesta confirmaría o
      refutaría la afirmación — la técnica de los ganadores de AVeriTeC 2.0. Flag
      `--preguntas`. **Con verificador v2 + preguntas: AVeriTeC-100 37% → 39%,
      F1 macro 0.254 → 0.308, NEI F1 0.077 → 0.300** (serie: 30→31→37→39).
      24.5 s/afirmación, dentro del presupuesto de 1 min del shared task.
- [ ] Afinar los priores con datos (aprendidos de aciertos históricos, no a mano)
- [x] **Desempate por fiabilidad (2026-07-05)**: en zona de empate, conflicto real
      solo si AMBOS lados tienen una voz fiable; ruido web empatando con un
      desmentido creíble = refutación (medido: 13/16 "contradictorias" predichas
      eran refutadas). **AVeriTeC-100: 39% → 41%, Refuted F1 0.577** (serie
      completa: 30→31→37→39→41). Trade-off honesto: la clase "contradictoria"
      queda casi vacía (F1 0.074→0) — estaba rota de origen y ahora es explícito.
- [ ] Clase "evidencia contradictoria": necesita detección real de cherry-picking
      (¿la evidencia que sustenta omite contexto que la refutaría?) — candidato
      natural: MiMo como juez de omisión. Hoy es la clase peor (F1 0).
- [ ] Manejo temporal: hechos volátiles vs. estables
- [ ] Detección de cherry-picking (clase AVeriTeC "evidencia contradictoria")
- [ ] Búsqueda activa de evidencia contraria (anti-sesgo de confirmación)

**Criterio de éxito:** mejora medible en la clase "conflicting evidence" de AVeriTeC,
la más difícil del benchmark.

## Fase 3 — Modo frontera (2–3 meses, investigación)

- [ ] Router: ¿este hecho sin evidencia es computable, deducible, o solo proponible?
- [ ] Sandbox de ejecución de código para hechos computables
- [ ] Motor de deducción sobre hechos ya verificados (reglas explícitas, auditable)
- [ ] Generador de protocolos de verificación para lo no computable

**Criterio de éxito:** en un conjunto de preguntas sin respuesta directa en la web pero
computables (ej. "¿un cubo de agua de 3m cabe en X?"), el sistema las resuelve por
simulación en vez de responder "no sé".

## Fase 4 — Generación verificada (puede arrancar tras la Fase 1, en paralelo)

El bucle generar→verificar→seleccionar, empezando por el dominio donde la verificación
es objetiva: **código**.

- [ ] Sandbox de ejecución (contenedores) con tests, benchmark y perfilado automáticos
- [ ] Generador de código: Qwen3-Coder pequeño cuantizado (Q4) en GPU de consumo
- [ ] Bucle best-of-N: N candidatos → puntuación por ejecución → sobrevive el mejor;
      si ninguno pasa, reintento con el feedback del fallo
- [ ] "Modo eficiencia": la puntuación incluye tiempo y memoria medidos, no solo corrección
- [ ] Escritura anclada: todo texto generado pasa por el Módulo 3 antes de entregarse
- [ ] Imágenes: orquestar FLUX.2 Klein / Z-Image Turbo locales + score de adherencia al prompt

**Criterio de éxito:** en un conjunto de tareas de código con tests, AIDAM (generador
pequeño + verificador) iguala la tasa de éxito de un asistente de frontera a <10% del
costo por tarea resuelta.

## Fase 5 — Eficiencia extrema (continuo)

- [x] **Verificador en ONNX → cualquier CPU (2026-07-05)**: exactitud idéntica a
      PyTorch (88.3%), 1.4x más rápido en CPU, y el runtime pesa ~50 MB en vez de
      ~3 GB (`pip install aidam[verificador-cpu]`, backend auto si falta torch).
      Export: `training/cuantizar_verificador.py`.
      ⚠️ Hallazgo medido: el INT8 dinámico **rompe** DeBERTa-v3 (88.3% → 51.4%,
      por canal tampoco rescata) — su atención desenredada no tolera cuantización
      dinámica de activaciones. Camino: cuantización estática con calibración
      excluyendo la atención, o QAT (quantization-aware training).
- [ ] INT8 real del verificador vía QAT o estática con exclusión de atención
- [ ] Experimento BitNet: fine-tuning de bitnet-b1.58-2B-4T + despliegue con bitnet.cpp
- [ ] Distilar el descompositor a <500M
- [ ] Fusionar descomposición+verificación en una pasada (estilo VeriFastScore)

---
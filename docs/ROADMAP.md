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
- [ ] Generador de datos sintéticos: errores factuales sutiles, multi-frase, multi-salto
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
- [ ] Afinar los priores con datos (aprendidos de aciertos históricos, no a mano)
- [ ] Clase "evidencia contradictoria": F1 0.095 en AVeriTeC-100 — la más débil;
      necesita detección real de cherry-picking, no solo el empate de señales
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

- [ ] Verificador en int8/ONNX → CPU de consumo (ganancia probada, sin drama)
- [ ] Experimento BitNet: fine-tuning de bitnet-b1.58-2B-4T + despliegue con bitnet.cpp
- [ ] Distilar el descompositor a <500M
- [ ] Fusionar descomposición+verificación en una pasada (estilo VeriFastScore)

---
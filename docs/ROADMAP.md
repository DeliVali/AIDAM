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
- [ ] Evaluación en el dev set de **AVeriTeC** y en **LLM-AggreFact**

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
- [ ] Generador de datos sintéticos: errores factuales sutiles, multi-frase, multi-salto
- [ ] Datos de entrenamiento en español (VitaminC es inglés; el modelo conserva el
      español del checkpoint base, pero hay que medirlo y reforzarlo)
- [ ] Calibración de probabilidades + evaluación de abstención
- [ ] Publicar en HuggingFace con pesos abiertos

**Criterio de éxito:** ≥ MiniCheck-FT5 en LLM-AggreFact; primer verificador pequeño
competitivo en español.

## Fase 2 — Lógica comparativa seria (1–2 meses)

- [ ] Modelo de independencia de fuentes (detección de contenido sindicado/copiado)
- [ ] Priores de fiabilidad por fuente, aprendidos de aciertos históricos, transparentes.
      *Caso motivador (2026-07-05): «la Gran Muralla se ve desde la Luna» → tres sitios
      turísticos que repiten el mito empatan con Wikipedia y el veredicto queda en
      "contradictorio" cuando debería ser "refutado". Sin fiabilidad por fuente, la
      web ruidosa empata con la web fiable.*
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

## ⚠️ Verdades incómodas (leer antes de soñar)

Este proyecto es viable **porque** acota sus promesas. Estas son las tres correcciones
a la visión original, por escrito para no olvidarlas:

**1. "1-bit sin pérdida de eficacia" — parcialmente falso.**
BitNet b1.58 requiere entrenar desde cero con quantization-aware training (no se puede
convertir un modelo existente sin pérdida), y la paridad con fp16 se sostiene a escala
de ~2B+ con billones de tokens de entrenamiento — presupuesto de Microsoft, no de una
GPU de consumo. Nuestro camino: int8/4-bit post-entrenamiento (pérdida ~nula, probado)
primero, y BitNet como experimento de fine-tuning sobre el 2B-4T ya publicado.

**2. "Que toda tu información sea correcta" — imposible; hay algo mejor.**
Ningún sistema puede garantizar la verdad: solo puede medir el acuerdo de fuentes
independientes, y las fuentes pueden estar todas equivocadas (la historia de la ciencia
está llena de consensos rotos). Lo que sí podemos garantizar, y ningún LLM grande ofrece
hoy: **trazabilidad total** (cada veredicto cita su evidencia), **calibración honesta**
(cuando dice 90%, acierta el 90% de las veces) y **abstención** (dice "no sé" en vez de
alucinar). Eso ya sería un salto enorme sobre el estado actual.

**3. "Competir con los grandes modelos" — sí, pero en la tarea correcta.**
AIDAM no reemplazará a un LLM general en escribir código o poesía. No lo necesita: la
meta es superar a GPT/Claude/Gemini **en verificación factual por dólar y por vatio**,
que es exactamente lo que MiniCheck ya demostró posible. Un martillo no compite con una
navaja suiza; la clava mejor.

**4. "Generar más barato que los asistentes de frontera" — cierto donde la verificación
es objetiva; falso donde no lo es.**
El bucle generador-pequeño + verificador funciona cuando hay un árbitro objetivo: tests
que pasan, benchmarks que dan números, hechos que se contrastan con fuentes. En código
la promesa es real y medible (Fase 4). En prosa abierta, diseño creativo o juicio
estético no hay verificador barato, y ahí un generador pequeño sigue siendo un generador
pequeño: N intentos malos no suman uno bueno si nadie puede puntuar cuál es mejor. AIDAM
promete calidad-por-dólar superior **en dominios verificables**, no paridad universal.

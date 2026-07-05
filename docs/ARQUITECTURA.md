# Arquitectura de AIDAM

AIDAM no es un modelo: es un **sistema compuesto** donde un modelo pequeño especializado
es el núcleo y los demás módulos son ingeniería determinista o herramientas. Esto es
deliberado — cada cosa que puede resolverse con código no gasta parámetros.

```
                        ┌─────────────────────────────────────┐
 Afirmación / Pregunta  │  1. DESCOMPOSITOR                    │
 ──────────────────────▶│  afirmación → hechos atómicos        │
                        │  verificables (estilo VeriScore)     │
                        └──────────────┬──────────────────────┘
                                       │ hechos atómicos
                        ┌──────────────▼──────────────────────┐
                        │  2. RECUPERADOR MULTI-FUENTE         │
                        │  búsqueda web, Wikipedia, papers,    │
                        │  datos estructurados. Deduplica y    │
                        │  agrupa por fuente independiente     │
                        └──────────────┬──────────────────────┘
                                       │ pares (hecho, evidencia)
                        ┌──────────────▼──────────────────────┐
                        │  3. NÚCLEO VERIFICADOR  ★el modelo★  │
                        │  <1B params, estilo MiniCheck:       │
                        │  ¿la evidencia sustenta el hecho?    │
                        │  → sustenta / refuta / no concluye   │
                        └──────────────┬──────────────────────┘
                                       │ veredictos por par
                        ┌──────────────▼──────────────────────┐
                        │  4. AGREGADOR DE LÓGICA COMPARATIVA  │
                        │  pondera independencia de fuentes,   │
                        │  fiabilidad, fecha; detecta          │
                        │  contradicciones y cherry-picking    │
                        └──────────────┬──────────────────────┘
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 ▼                     ▼                     ▼
         SUSTENTADO / REFUTADO   CONTRADICTORIO      SIN EVIDENCIA
         (+ citas trazables)     (muestra ambos       │
                                  lados + pesos)      ▼
                        ┌─────────────────────────────────────┐
                        │  5. MODO FRONTERA                    │
                        │  genera plan de verificación:        │
                        │  simulación (código), cálculo        │
                        │  simbólico, o diseño de experimento. │
                        │  Nunca inventa una respuesta.        │
                        └─────────────────────────────────────┘
```

## Módulo 1 — Descompositor

**Qué hace:** convierte una afirmación compleja en hechos atómicos verificables, con
decontextualización (resolver pronombres, fechas relativas, elipsis) para que cada hecho
sea autocontenido.

**Cómo:** en Fase 0, un LLM abierto pequeño con prompt (estilo VeriScore/DnDScore).
En fases posteriores, se destila a un modelo propio de <500M. La literatura de 2025
(VeriFastScore) muestra que descomposición + verificación pueden fusionarse en una sola
pasada — optimización futura.

## Módulo 2 — Recuperador multi-fuente

**Qué hace:** para cada hecho atómico, busca evidencia en fuentes heterogéneas y la
prepara para el verificador.

**Diseño clave:** el valor de la evidencia depende de la **independencia** de las fuentes.
Cien sitios que copian el mismo comunicado de prensa cuentan como *una* fuente. El
recuperador:

- agrupa documentos por origen probable (clustering de similitud + análisis de dominio),
- registra metadatos: fecha, tipo de fuente (primaria/secundaria/terciaria), dominio, idioma,
- busca activamente evidencia **en contra**, no solo a favor (anti-sesgo de confirmación).

**La información es libre sin importar el idioma:** el recuperador no se limita al
idioma de la afirmación. Vía los enlaces interlingüísticos de Wikipedia trae el mismo
artículo en otros idiomas (inglés, chino, ruso, árabe…) **sin modelo de traducción**,
y el verificador multilingüe juzga los pares cruzados directamente (afirmación en
español, evidencia en alemán). Bono de independencia: cada edición de Wikipedia es una
comunidad editorial distinta — más voces para la lógica comparativa. Limitación actual:
los pasajes en idiomas que no comparten vocabulario con la consulta se toman de la
introducción del artículo (no hay ranking léxico cruzado); la mejora natural son
embeddings multilingües para rankear relevancia entre idiomas.

**Sin entrenamiento:** este módulo es ingeniería pura (APIs de búsqueda, embeddings para
clustering, reglas). Cero parámetros gastados.

## Módulo 3 — Núcleo verificador (el modelo especializado)

**El corazón del proyecto.** Un modelo pequeño que recibe `(hecho atómico, pasaje de
evidencia)` y emite: **sustenta / refuta / no concluye**, con probabilidad calibrada.

**Por qué puede ser pequeño:** no necesita saber si la afirmación es cierta — solo si
*este texto* la sustenta. Eso es inferencia textual (NLI), una habilidad cerrada que cabe
en cientos de millones de parámetros. MiniCheck lo demostró: 770M ≈ GPT-4 en esta tarea.

**Receta de entrenamiento (validada por MiniCheck):**
1. Generar datos sintéticos con un LLM fuerte: pares (hecho, evidencia) con errores
   factuales *desafiantes* — sutiles, que requieren componer información entre frases.
2. Fine-tuning de un modelo base pequeño (candidatos: Flan-T5-Large 770M,
   ModernBERT-Large 400M, Qwen3-0.6B) sobre esos datos + datasets públicos (ANLI, FEVER,
   LLM-AggreFact).
3. Calibración post-hoc (temperature scaling) para que las probabilidades signifiquen algo.

**Métrica de éxito:** igualar o superar MiniCheck-FT5 en el benchmark LLM-AggreFact.

## Módulo 4 — Agregador de lógica comparativa

**Qué hace:** combina los veredictos por par en un veredicto global por hecho, y de los
hechos al veredicto de la afirmación completa. Aquí vive la "lógica comparativa" que da
nombre al proyecto.

**Es matemática explícita, no una red neuronal** (transparente y auditable):
- ponderación bayesiana por fiabilidad histórica de la fuente y por independencia,
- penalización por antigüedad en topics volátiles; no en hechos estables,
- detección de patrón *cherry-picking*: afirmaciones técnicamente ciertas que engañan
  por omisión (clase de veredicto tomada de AVeriTeC),
- salida en 4 clases: **sustentado / refutado / evidencia contradictoria / evidencia
  insuficiente**, siempre con las citas que justifican el veredicto.

## Módulo 5 — Modo frontera ("el factor humano")

Cuando el agregador devuelve *evidencia insuficiente*, AIDAM hace lo que hace un
científico: no opina — diseña cómo averiguarlo.

**Jerarquía de estrategias (de lo automatizable a lo propositivo):**
1. **Cálculo/simulación:** si el hecho es computable (matemática, física simple,
   estadística sobre datos públicos), genera y ejecuta código, y la salida ES la evidencia.
2. **Deducción desde hechos verificados:** encadena hechos ya sustentados mediante
   reglas lógicas explícitas ("A implica B, A está sustentado ⇒ B tiene soporte deductivo").
3. **Diseño de experimento:** si no es computable, produce un protocolo: qué datos harían
   falta, qué mediría, qué resultado confirmaría/refutaría. Salida honesta: "no
   verificable hoy; así se verificaría".

**Honestidad de diseño:** el nivel 3 no compite con científicos humanos. Es una plantilla
estructurada + un LLM de razonamiento usado como herramienta. El valor está en que el
sistema *nunca* cruza de "no hay evidencia" a "me lo invento".

## El bucle de generación verificada (Módulos 6–7)

La verificación no es solo el producto: es el **motor que abarata la generación**. El
principio (validado por la literatura de test-time compute, ICLR 2025): verificar es más
fácil que generar, así que un verificador fuerte + un generador pequeño + N intentos
rinde como un generador gigante — a una fracción del costo. Con presupuesto de cómputo
igualado, esta estrategia supera a modelos 14x más grandes.

```
              ┌────────────────────────────────────────────┐
   Tarea ────▶│  6. GENERADORES ESPECIALIZADOS (SLMs)      │
              │  código: Qwen3-Coder (Q4, GPU de consumo)  │
              │  texto:  SLM abierto pequeño               │──┐
              │  imagen: FLUX.2 Klein 4B / Z-Image Turbo   │  │ N candidatos
              └────────────────────────────────────────────┘  │
                                                              ▼
              ┌────────────────────────────────────────────┐
              │  7. VERIFICADOR DE GENERACIÓN               │
              │  código:  ejecutar. tests, benchmark,       │
              │           perfilado → puntuación OBJETIVA   │
              │  texto:   Módulo 3 (¿factualmente           │
              │           sustentado?) + verificación docs  │
              │  imagen:  adherencia al prompt (score       │
              │           automático) — la más débil        │
              └──────────────────┬─────────────────────────┘
                                 │
                    solo sobrevive el candidato que pasa;
                    si ninguno pasa → reintenta con el
                    feedback del fallo, o escala y lo dice
```

**Jerarquía de verificabilidad** (decide cuánto puede prometer el sistema en cada dominio):

1. **Código — verificación perfecta.** Compila o no; los tests pasan o no; el benchmark
   da milisegundos y el perfilador da memoria. "Código optimizado" es una medición, no
   una opinión. Aquí AIDAM puede superar en calidad-por-dólar a los asistentes grandes,
   y es exactamente como se entrenó Qwen3-Coder-Next: ~800k tareas donde la verdad
   terreno es *un test que pasa en un contenedor Docker*.
2. **Hechos/texto — verificación fuerte.** El Módulo 3 puntúa cada afirmación generada
   contra fuentes. La escritura queda "anclada": el sistema no puede afirmar lo que su
   propio verificador no sustenta.
3. **Imágenes — verificación débil.** Se puede medir adherencia al prompt y artefactos,
   pero no "belleza". Aquí AIDAM *orquesta* modelos abiertos destilados existentes
   (FLUX.2 Klein 4B cabe en ~8 GB de VRAM; Z-Image Turbo 6B genera en segundos en una
   tarjeta de 16 GB) — no entrenamos modelos de imagen: es otro presupuesto y otra
   ciencia.

**Regla de diseño (paper de NVIDIA, 2025):** modelos pequeños especializados para cada
tarea repetitiva del agente; un modelo grande solo si un paso de planificación lo exige
de verdad — y con la meta de destilarlo después. Los SLMs son 10–30x más baratos de
servir y más fiables en salidas estructuradas, que es justo lo que un sistema compuesto
necesita.

**Por qué esto abarata:** el costo de los asistentes grandes está en generar *todo* con
el modelo más caro. AIDAM invierte la ecuación: generadores baratos que se equivocan
más, más un verificador barato y fuerte que filtra — el costo total por resultado
*correcto* baja aunque haya reintentos, porque verificar cuesta céntimos frente a generar
con un modelo de frontera.

## Eficiencia (transversal)

**Entrenamiento:**
- Liger Kernel (kernels Triton fusionados: RMSNorm, RoPE, SwiGLU, FusedLinearCrossEntropy)
  → ~60% menos memoria, ~20% más throughput. Directamente aplicable en una GPU de consumo.
- FlashAttention (la versión que soporte tu GPU; FA-3 requiere Hopper).
- `torch.compile` + bf16 + gradient checkpointing como base.
- LoRA/QLoRA para iterar barato; full fine-tuning solo para la versión final.

**Inferencia:**
- Primera línea: ONNX Runtime / int8 para el verificador (modelos encoder pequeños
  cuantizan a int8 casi sin pérdida — esto sí está probado).
- Experimento BitNet: fine-tuning de `microsoft/bitnet-b1.58-2B-4T` para la tarea de
  verificación, desplegado con `bitnet.cpp` en CPU pura. Ver advertencia en
  [ROADMAP.md](ROADMAP.md) sobre los límites reales del 1-bit.

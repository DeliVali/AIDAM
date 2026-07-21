# AIDAM — diagramas de arquitectura (base del proyecto)

La **arquitectura canónica es el §1** (la visión del owner). Todos los demás
diagramas son el *detalle de sus cajas* — marcados **✅ construido** o
**🎯 objetivo**. Nos regimos por el §1; lo que existía antes se reusa solo
donde sirve para implementar esta arquitectura, no al revés.

Diagramas en **Mermaid** (texto plano): se renderizan solos en GitHub; para
editarlos visualmente pega cualquier bloque en <https://mermaid.live> (sin
registro) o impórtalo en <https://app.diagrams.net>. Los nodos citan módulos y
funciones reales (`aidam/…`). Roster de expertos y benchmarks por dominio:
[MULTI_SLM.md §11](MULTI_SLM.md).

Índice:
1. **Arquitectura canónica (visión del owner)** — perfil → router → experto → fact-checker → comparador → flywheel
2. Enrutamiento de la entrada (superficie de chat) ✅
3. Núcleo fact-checker: pipeline de verificación ✅
4. Modo respuesta (pregunta → respuesta citada) ✅
5. Bucle ReAct de tareas (el razonador) ✅
6. Árbitros por dominio (separación de poderes) 🎯
7. Bajo nivel: cableado actual (procesos, IPC, módulos, almacenes) ✅

---

## 1. Arquitectura canónica (visión del owner)

**La referencia del proyecto.** Perfil de hardware → router → experto
especializado → fact-checker → lógica comparativa → respuesta, más el flywheel
opt-in. Cuatro matices medidos del proyecto marcados con ★: (1) los dominios de
conocimiento = recuperación + razonador compartido, no un modelo memorizado;
(2) el «comparador» es lógica determinista auditable, no un modelo; (3) el
router-modelo debe ganarle al router de código (GATE ROUTE); (4) el
reentrenamiento promociona **solo si pasa** la batería, no al terminar. Roster
completo con modelos base y benchmarks: [MULTI_SLM.md §11](MULTI_SLM.md).

```mermaid
flowchart TB
    ACT(["Usuario · prompt"]) --> ENTRY["Puntos de entrada<br/>Electron · CLI"]
    ENTRY --> HAL["HAL — al instalar/iniciar audita el hardware<br/>genera 3 perfiles (A alto · B medio · C bajo)<br/>el perfil elige modelo y MODULA la agencia<br/>(perfil bajo: funciones como reentrenar, bloqueadas)"]
    HAL --> ROUTER["Router — clasifica la intención<br/>★ hoy es CÓDIGO (keywords + NLI, 0 MB);<br/>modelo 0.5B solo si gana (GATE ROUTE)"]

    ROUTER --> POOL
    subgraph POOL["Pool de expertos (cuantizados + fine-tuning, benchmarks por-dominio)"]
        direction TB
        subgraph SKILL["Habilidad — se especializan en pesos"]
            direction LR
            CODE["Código · Qwen2.5-Coder-3B<br/>HumanEval/MBPP/LiveCodeBench/SWE-bench"]
            MATH["Matemáticas · Qwen2.5-Math-1.5B<br/>GSM8K/MATH-500/AIME/FrontierMath"]
            AGENT["Razonador/Agente · R1-Qwen3-8B→4B/1.7B<br/>BFCL V4 · τ²-bench · AVeriTeC-500"]
        end
        subgraph KNOW["★ Conocimiento — razonador compartido + recuperación (NO memorizado)"]
            direction LR
            LEGAL["Legal · LegalBench/LexGLUE/CaseHOLD"]
            MED["Medicina · MedQA/PubMedQA/MMLU-Med"]
            BIO["Biología · GPQA-bio/MMLU-Med"]
            PHYS["Física/Química · GPQA-Diamond/SciFact"]
            HIST["Historia · MMLU-Pro/EduArt + anacronismos"]
            NEWS["Actualidad · AVeriTeC/citation-support"]
        end
    end

    POOL --> SUG(["Respuesta sugerida"])
    SUG --> FC["Fact-checker CORE (residente)<br/>NLI 280M + búsqueda integrada (22 fuentes)<br/>árbitro por dominio: sandbox · SymPy · recuperación+NLI"]
    FC --> CMP["★ Lógica comparativa (DETERMINISTA, no un modelo)<br/>aggregate.py + grounding gate<br/>¿la respuesta del experto es congruente con la evidencia?<br/>lo no sustentado → «sin verificar»"]
    CMP --> ANS(["Respuesta al usuario<br/>SIEMPRE con citas"])

    ANS -. "flujo validado (opt-in)" .-> FLY
    subgraph FLY["Reentrenamiento dinámico (SOLO perfiles A/B)"]
        direction TB
        LIM["Se alcanzó el límite de datos guardados"]
        ASK{"¿Reentrenar con tu telemetría?<br/>(consentimiento del usuario)"}
        LIM --> ASK
        ASK -->|No| DEL["Se elimina la telemetría<br/>(se guarda hash/log para auditar)"]
        ASK -->|Sí| TRAIN["QLoRA en background (nice-15)<br/>+ datos-oro externos (anti-olvido)"]
        TRAIN --> BATT{"★ Batería de gates:<br/>habilidad ≥ actual · sin regresión<br/>ANTI-ALUCINACIÓN no empeora · canary"}
        BATT -->|falla| REJ["Rechazo documentado<br/>modelo actual se mantiene"]
        BATT -->|pasa| UPD["Hot-swap del experto (rollback retenido)"]
        UPD --> DEL
        REJ --> DEL
    end
```

---

## 2. Enrutamiento de la entrada del usuario ✅

Detalle del bloque **Router** del §1: qué es cada entrada decide el camino.
Todo es código determinista y testeable; un falso positivo que robe una
afirmación al camino de verificación es el peor error, así que la detección es
conservadora.

```mermaid
flowchart TD
    IN(["Texto del usuario"]) --> COMP{"¿computable?<br/>computables.responder_computable"}
    COMP -->|sí: mates/fechas| RC["Respuesta calculada<br/>(sin modelo)"]
    COMP -->|no| ORD{"¿orden de archivos?<br/>archivos.interpretar_orden"}
    ORD -->|«mueve…», «crea…»| FILE["Tarjeta de permiso<br/>acción exacta · solo HOME · papelera"]
    ORD -->|no| PREG{"¿es pregunta?<br/>sintesis.es_pregunta"}
    PREG -->|sí| AMBIG{"¿evidencia ambigua?<br/>aclaracion_necesaria"}
    AMBIG -->|sí| ASK["Devuelve una pregunta<br/>(divide sentidos)"]
    AMBIG -->|no| ANS["Modo respuesta<br/>(diagrama 4)"]
    PREG -->|no| TAREA{"¿tarea imperativa Y modo tarea ON?<br/>razonador.interpretar_tarea"}
    TAREA -->|sí| REACT["Bucle ReAct<br/>(diagrama 5)"]
    TAREA -->|no| VER["Afirmación → verificación<br/>(diagrama 3)"]
```

---

## 3. Núcleo fact-checker: pipeline de verificación ✅

Detalle del bloque **Fact-checker CORE** del §1, ya construido y medido. Los
veredictos SÓLO salen de aquí (NLI + agregación), nunca de un LLM (medido:
LLM-como-único-juez 24% vs 58%).

```mermaid
flowchart TD
    C(["Afirmación"]) --> DEC["1· Descomponer<br/>claim → hechos atómicos<br/>decompose.py (estilo VeriScore)"]
    DEC --> ROU["2· Router de categoría<br/>router.py: palabras clave → NLI zero-shot"]
    ROU --> RET["3· Recuperación multifuente EN PARALELO<br/>retrieve.py · 22 familias · sin claves"]

    subgraph FUENTES["Fuentes (por categoría)"]
        direction LR
        W["Wikipedia<br/>multilingüe"]
        DB["Debunks<br/>fact-checkers"]
        DOC["Docs oficiales<br/>código/infra"]
        ACA["Semantic Scholar<br/>OpenAlex · arXiv"]
        WEB["Web abierta<br/>páginas completas"]
    end
    RET --> FUENTES
    FUENTES --> IND["Independencia:<br/>un dominio = una voz<br/>(clustering + metadatos)"]

    IND --> JUD["4· Juez NLI por par<br/>verify.puntuar / juzgar<br/>sustenta / refuta / neutral + prob"]
    JUD --> AG["5· Agregador comparativo<br/>aggregate.py · priores de fiabilidad<br/>fact-checkers 8x · academia 2.5x"]

    AG --> V{"Veredicto (4 clases)"}
    V --> S["SUSTENTADA"]
    V --> RF["REFUTADA"]
    V --> CO["EVIDENCIA EN CONFLICTO"]
    V --> NE["SIN EVIDENCIA SUFICIENTE"]
    NE --> FRO["Modo frontera<br/>computar/simular · deducir · diseñar experimento<br/>NUNCA inventa"]
    S --> CIT(["+ citas trazables"])
    RF --> CIT
    CO --> CIT
```

---

## 4. Modo respuesta (pregunta → respuesta citada) ✅

Las preguntas se responden con la frase que responde, citada — nunca con un
veredicto. Fundamentado por construcción: cada palabra viene textual de una
fuente. La cita secundaria pasa por el NLI (corrección medida 2026-07-20).

```mermaid
flowchart TD
    Q(["Pregunta"]) --> RET["Recuperar evidencia<br/>(mismas fuentes que el diagrama 3)"]
    RET --> CAND["Partir pasajes en FRASES candidatas<br/>25–300 chars, sin código"]
    CAND --> RANK["Rankear por embedding<br/>vectores._codificador<br/>frase ↔ pregunta"]
    RANK --> BEST["Mejor frase = respuesta<br/>(textual de su fuente)"]
    BEST --> PRIM["Cita PRIMARIA<br/>«Source: dominio — url»<br/>precisión medida 94.6%"]
    PRIM --> SEC{"Citas secundarias<br/>«Also covered by»<br/>_dominios_corroborantes"}
    SEC -->|verificador disponible| GATE["Filtro NLI:<br/>¿el pasaje del dominio IMPLICA la frase?<br/>≥ UMBRAL_SUSTENTO (0.6)<br/>coste acotado: ≤15 cotejos"]
    SEC -->|sin verificador| TOP["Fallback: dominios por rango<br/>(comportamiento histórico)"]
    GATE -->|implica| SHOW["Mostrar dominio corroborante"]
    GATE -->|no implica| DROP["Descartar<br/>(evita citation theater)"]
    SHOW --> A(["Respuesta + citas honestas"])
    TOP --> A
    BEST --> A
```

---

## 5. Bucle ReAct de tareas (el razonador) ✅

Detalle del bloque **ReAct** del §1. El LLM elige la SIGUIENTE acción dentro de
límites impuestos por código (presupuesto, whitelist, permisos, sandbox,
auditoría por paso). La terminación la decide el código, no el modelo. Todo
pensamiento/acción/observación se MUESTRA. En la arquitectura objetivo, el
worker único se reemplaza por el experto que el router elige del pool (§1).

```mermaid
flowchart TD
    T(["Tarea"]) --> INIT["Estado en el orquestador:<br/>scratchpad · presupuesto · auditoría<br/>(el modelo es SIN-ESTADO)"]
    INIT --> STEP["Render del scratchpad → prompt<br/>razonador._renderizar (ChatML)"]
    STEP --> LLM["Experto del pool (§1)<br/>worker aislado · llm_worker.py"]
    LLM --> PARSE{"Extraer 1 acción JSON<br/>_extraer_accion"}
    PARSE -->|inválida| RETRY["Reintento correctivo<br/>(1 vez, sin pensar)"]
    RETRY -->|falla otra vez| FAILV["Termina VISIBLE<br/>error_llm (nunca inventa)"]
    PARSE -->|responder| GATEG["Grounding gate<br/>revisar_respuesta<br/>frases sin sustento → «sin verificar»"]
    PARSE -->|herramienta| REP{"¿acción repetida?"}
    REP -->|sí| BREAK["Rompe-bucles:<br/>observación correctiva, no re-ejecuta"]
    REP -->|no| TOOL["ejecutar_herramienta<br/>leer/escribir/sandbox/buscar/verificar"]
    TOOL --> OBS["Observación (dato, no instrucción)<br/>entre delimitadores · truncada"]
    OBS --> BUD{"¿presupuesto agotado?<br/>MAX_PASOS=8"}
    BREAK --> BUD
    BUD -->|no| STEP
    BUD -->|sí| SUMV["Resumen determinista<br/>de lo hecho (visible)"]
    GATEG --> DONE(["Respuesta final + auditoría"])
    SUMV --> DONE
    FAILV --> DONE
```

---

## 6. Árbitros por dominio (separación de poderes) 🎯

Detalle del **árbitro por dominio** del §1: ningún modelo evalúa su propio
trabajo. El árbitro cambia según el dominio (la columna «Árbitro AIDAM» del
roster) — sandbox para código, SymPy para matemáticas, recuperación+NLI para
conocimiento. Un fallo de cualquiera vuelve al bucle de reparación como
observación.

```mermaid
flowchart TD
    DRAFT(["Respuesta sugerida del experto"])
    subgraph JUECES["Árbitros independientes (ninguno es el autor · según dominio)"]
        J1["Fact-checker semántico<br/>NLI 280M + agregación<br/>→ congruencia con la evidencia"]
        J2["Adversario QA / cómputo<br/>valores límite · SymPy/NumPy<br/>consistencia/anacronismos · Ruff"]
        J3["Comparador físico (código)<br/>ejecutar en sandbox · diff vs disco<br/>huella de resultado"]
    end
    DRAFT --> J1
    DRAFT --> J2
    DRAFT --> J3
    J1 --> DEC{"¿congruente y correcto?"}
    J2 --> DEC
    J3 --> DEC
    DEC -->|no| FIX["Bucle de reparación:<br/>recarga SÓLO el experto que toca<br/>error como Observación (dato)"]
    FIX --> DRAFT
    DEC -->|sí| APPLY(["Entregar / aplicar<br/>+ grounding gate «sin verificar»"])
```

---

## 7. Bajo nivel: cableado actual ✅

Vista técnica de lo **construido hoy**: **fronteras de proceso** (recuadros
◆), **IPC/red** (flechas punteadas), **llamadas en-proceso** (sólidas),
**almacenes** (cilindros) y **APIs externas**. Refleja el código real
(`aidam/…`, `escritorio/…`). Tres procesos separados por diseño: Electron, el
servidor Python, y el worker LLM aislado (nació de una corrupción de heap
medida entre llama.cpp y PyTorch). **Estado vs §1:** hoy hay un worker
razonador único; la arquitectura objetivo lo sustituye por el pool de expertos
que el router selecciona por perfil.

```mermaid
flowchart TB
    subgraph ENTRY["Puntos de entrada"]
        direction LR
        CLI["CLI · aidam<br/>cli.py<br/>verificar · investigar · tarea<br/>codigo · imagen · interfaz"]
        BROWSER["Navegador<br/>interfaz/app.js"]
        ELECTRON["Escritorio · Electron<br/>escritorio/main.js"]
    end

    ELECTRON -. "spawn(): aidam interfaz --sin-navegador --puerto N" .-> SRV
    BROWSER -. "HTTP + WebSocket (streaming)" .-> SRV
    CLI -->|"import directo"| PIPE
    CLI --> ORQ

    subgraph PROC_SRV["◆ PROCESO SERVIDOR — Python (FastAPI + uvicorn)"]
        SRV["servidor.py<br/>POST /v1/chat/completions<br/>GET /api/* · WebSocket"]
        NLIRES["Verificador NLI RESIDENTE<br/>_verificador_cacheado() · 1x por proceso"]
        ROUTECHAT["Enrutado de superficie<br/>archivos · pregunta · tarea · afirmación"]
        SRV --> ROUTECHAT
        SRV --> NLIRES
    end
    ROUTECHAT --> PIPE
    ROUTECHAT --> ORQ

    subgraph LIB["Biblioteca núcleo (en-proceso)"]
        direction TB
        PIPE["pipeline.py · verificar()"]
        DEC["decompose.py"]
        ROU["router.py"]
        RET["retrieve.py<br/>FUENTES · 22 familias · paralelo"]
        VER["verify.py · crear_verificador()"]
        AGG["aggregate.py + comparators.py"]
        VEC["vectores.py · embedder"]
        SINT["sintesis.py<br/>responder_pregunta()"]
        PIPE --> DEC --> ROU --> RET --> VER --> AGG
        RET --> VEC
        PIPE --> SINT
        SINT -. "gate cita secundaria" .-> VER
    end

    subgraph AGENTE["Subsistema agente (aidam/agente/)"]
        direction TB
        ORQ["orquestador.py"]
        RAZ["razonador.py · bucle ReAct"]
        HER["herramientas.py"]
        SBX["sandbox.py"]
        COLA["cola.py · cola SQLite (reanudable)"]
        MEM["memoria.py<br/>memoria 3 niveles (SOLO RAM)"]
        PERM["permisos.py"]
        AUD["auditoria.py"]
        CODE["codigo.py · carrera de candidatos"]
        ORQ --> RAZ
        RAZ --> HER
        HER --> PERM
        HER --> SBX
        RAZ --> AUD
        ORQ --> COLA
        ORQ --> MEM
        HER --> CODE
        CODE --> SBX
    end
    ORQ --> PIPE
    RAZ -. "consultar_verificador" .-> VER

    VER --> BACKENDS
    subgraph BACKENDS["Backends del verificador (selección por AIDAM_BACKEND)"]
        direction LR
        TORCH["VerificadorNLI (PyTorch/GPU)<br/>mDeBERTa-v3 280M"]
        ONNX["VerificadorONNX (CPU)<br/>onnx · onnx-mini 319MB int4/int8"]
    end
    NLIRES --> BACKENDS

    subgraph PROC_LLM["◆ PROCESO WORKER LLM — AISLADO (→ pool de expertos, §1)"]
        WORKER["llm_worker.py<br/>llama.cpp · GGUF Q4<br/>create_completion()"]
    end
    RAZ -. "subprocess.Popen + JSON-lines (stdin/stdout)" .-> WORKER
    PIPE -. "questions.py: genera preguntas de búsqueda" .-> WORKER
    HALW["Config/HAL · env AIDAM_MIMO_*<br/>n_ctx · gpu_layers · kv-cache · flash-attn · lora"]
    HALW -. "env" .-> WORKER

    subgraph PROC_SBX["◆ SUBPROCESO SANDBOX"]
        BWRAP["bubblewrap (bwrap)<br/>sin red · FS solo-lectura<br/>.git remontado RO · timeout"]
    end
    SBX -. "spawn confinado" .-> BWRAP

    subgraph DISK["Almacenamiento en disco"]
        direction LR
        MODELS[("models/<br/>*.gguf · verificador-onnx*")]
        DL[("data/local/<br/>knowledge_store · search_cache.sqlite")]
        USER[("dir por-usuario (plataforma.py)<br/>general/ · historial · auditoria.jsonl")]
    end
    WORKER -. "mmap (page cache)" .-> MODELS
    BACKENDS --> MODELS
    RET --> DL
    COLA --> USER
    AUD --> USER

    subgraph EXT["APIs externas · HTTPS · sin claves"]
        direction LR
        E1["Wikipedia family<br/>DuckDuckGo · debunks"]
        E2["Stack Exchange · Semantic Scholar<br/>OpenAlex · arXiv · Europe PMC · Crossref"]
        E3["GDELT · openFDA<br/>ClinicalTrials · NIST NVD"]
    end
    RET -. "HTTPS en paralelo (registro FUENTES)" .-> EXT

    OUTN(["Respuesta / veredicto<br/>SIEMPRE con citas · vía WebSocket o stdout"])
    AGG --> OUTN
    SINT --> OUTN
    RAZ --> OUTN
```

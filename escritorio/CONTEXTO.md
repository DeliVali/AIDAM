# AIDAM — Contexto completo del proyecto para el diseño de la app de escritorio

> Documento de trabajo (2026-07-16). Todo lo que hay que saber del proyecto para diseñar
> la aplicación Electron sin tener que releer el repo. Las rutas son relativas a la raíz.

## 1. Qué es AIDAM

Agente abierto de verificación de información (fact-checking). En vez de confiar en lo
que un modelo "recuerda", recupera evidencia viva de ~22 familias de fuentes y deja que
un modelo pequeño especializado (NLI, 280M parámetros) compare cada hecho contra cada
pasaje. **Todo veredicto cita sus fuentes.** Todo corre local en hardware de consumo.

Principios innegociables (de CONTRIBUTING.md y docs/ARCHITECTURE.md):

1. **El veredicto sale SOLO del núcleo NLI + agregación auditable** (reglas explícitas en
   código, sin cajas negras). Los LLM son herramientas (reformulan, narran), **nunca el
   juez** — medido: un 8B como juez único saca 24% donde el pipeline saca 58%.
2. **Ninguna afirmación sin fuente trazable.** La memoria paramétrica está prohibida
   como evidencia.
3. **Hardware de consumo primero** (la máquina de referencia: RTX 5070 12GB, CachyOS).
4. **Sin censura**: la ruta del veredicto no sabe negarse a verificar.
5. Metodología de laboratorio: puertas pre-registradas antes de los números, experimentos
   rechazados documentados igual que los promovidos (docs/ROADMAP.md es la bitácora).

## 2. Estado medido (julio 2026)

- Verificador en producción: **v10** (mDeBERTa-v3 280M), desplegado como
  `models/verificador-v0`. AVeriTeC-500: **62.6** (por encima del baseline de mayoría 61).
- Linaje mmBERT (contexto 8k): v20 campeón de grounding (AggreFact **71.0–71.2**, récord
  del proyecto) pero no producción; v21 no promovido (puertas).
- FEVER (oráculo, 999 balanceado): ~86 especialista / 83.9 v21. SciFact: ~63.7.
- Media general de 4 benchmarks: **~71.5**. Meta declarada: **90 general**.
- Despliegues: PyTorch GPU, ONNX CPU (~50MB runtime) y mini int4 (319MB).
- LLM local opcional: DeepSeek-R1-Qwen3-8B GGUF Q4 vía llama.cpp en **proceso worker
  aislado** (llama.cpp + PyTorch en el mismo proceso corrompen memoria, medido).

## 3. Cómo funciona el pipeline (`aidam/`)

`pipeline.verificar(afirmacion, lang, max_idiomas, preguntas, verificador, progreso,
recuperador, buscador_preguntas) -> Informe`:

1. **Descomponer** (`decompose.py`): afirmación → hechos atómicos (heurístico).
2. **Router** (`router.py`): categoría del hecho (programación/matemáticas/medicina/
   ciencia/actualidad/general) → decide qué familias de fuentes consultar.
3. **Recuperar** (`retrieve.py`): registro `FUENTES` (~22 familias: Wikipedia multiidioma,
   Wikidata, web con búsqueda anti-bulos, GDELT, académicas, registros oficiales, docs
   técnicas, Stack Exchange…) consultadas EN PARALELO con aislamiento de fallos, caché
   sqlite, pacing y dedup. Una fuente caída solo reduce evidencia.
4. **Juzgar** (`verify.py`): el NLI puntúa cada par (hecho, pasaje) →
   sustenta / refuta / no_concluye con probabilidad calibrada.
5. **Agregar** (`aggregate.py`): reglas explícitas y auditables — un dominio = una voz,
   priors de fiabilidad (verificadores IFCN y docs oficiales 8x, enciclopedias/academia
   2.5x, .gov/.edu 2x), el eco no es evidencia, desmentidos mal leídos se descuentan.
   Veredicto global = el del hecho más débil.
6. Post-procesos LLM opcionales (solo con `--preguntas` y modelo presente): preguntas de
   búsqueda dirigidas, juez de omisión (cherry-picking), resolutor de casos insuficientes.

## 4. Regla de producto: preguntas vs afirmaciones (CLAVE para la UI)

Commit `d943c7d` (2026-07-16). El `Informe` ahora trae dos campos nuevos:

- `tipo`: `"afirmacion"` o `"pregunta"`.
- `respuesta`: **respuesta concisa siempre presente**, construida desde la evidencia.

Reglas que la UI DEBE respetar:

- **Una pregunta no se "refuta"**: si `tipo == "pregunta"`, NO mostrar etiqueta de
  veredicto ni confianza como si fuera un claim; mostrar la respuesta con sus citas.
  (Fallo de producto medido que motivó esto: «¿dónde está la Mona Lisa?» → "REFUTADO 75%".)
- **Respuesta entendible siempre**: el usuario recibe «No, X porque Y (fuente)» — nunca
  una etiqueta pelada ni un ensayo. `respuesta` viene lista; la síntesis LLM opcional
  puede pulirla pero obedece el mismo contrato de brevedad y nunca cambia el veredicto.

## 5. El subsistema agente (`aidam/agente/`) — el corazón del producto

Diseño completo en **docs/AGENT.md** (invariantes, cascada, doctrina multi-agente,
puertas pre-registradas). Módulos:

| Módulo | Qué hace |
|---|---|
| `orquestador.py` | **Cascada de investigación** (`aidam investigar`): pase barato nivel 0 siempre; escala a niveles 1-2 SOLO por señales medidas (confianza < 0.6, conflicto de evidencia fuerte, insuficiencia). El re-agregado pasa por las MISMAS reglas auditables. |
| `angulos.py` | Diversidad de ángulos (requisito de Condorcet): ángulo de **negación** (juzga la hipótesis negada y voltea etiquetas — recupera evidencia refutadora que la búsqueda afirmativa pierde) y reformulaciones LLM (solo diversifican retrieval; la hipótesis juzgada es siempre el hecho literal). |
| `permisos.py` | Motor deny-first estilo Claude Code: reglas `Herramienta(patron)` en `~/.config/aidam/permisos.json`, 4 modos (plan / preguntar / aceptar_ediciones / lote), split de comandos compuestos, anclas de ruta con symlinks resueltos, freno integrado `rm -rf /`. Asimetría deliberada: concesiones de comandos pueden persistir, las de edición son solo de sesión. |
| `sandbox.py` | Ejecución confinada con **bubblewrap**: `/` de solo lectura, escritura solo en el workspace, `.git` re-montado ro, sin red por defecto, timeout. Es el patrón en que convergieron Claude Code y Codex CLI en 2026. |
| `auditoria.py` | Cada llamada a herramienta → una línea JSONL con flush (decisión, modo, quién aprobó, hash). Reconstruible, como el agregador. |
| `cola.py` | Cola de trabajo SQLite thread-safe y reanudable (patrón `--reanudar` como primitiva) para orquestar trabajadores. |
| `sintesis.py` | El LLM SOLO ve la tabla de evidencia determinista y narra; salvaguarda que descarta salidas que contradigan el veredicto. Aquí viven también `es_pregunta()`, `responder_pregunta()` y `respuesta_concisa()` (modo respuesta, §4). |
| `herramientas.py` | Herramientas del agente (leer/escribir con diff previo, ejecutar en sandbox, verificar, investigar) con permisos + auditoría. |
| `bucle.py` | REPL `aidam agente`: un while, historial plano, comandos slash, texto libre = investigar. |
| `codigo.py` | (en curso) `aidam codigo`: comparar implementaciones **midiéndolas** en el sandbox; las mediciones se vuelven `Evidencia(fuente="medicion-local")` — el bucle generar→verificar→seleccionar aplicado a código. |
| `voz.py` / `vision.py` / `rastreo.py` | Extras opcionales que NUNCA tocan la ruta del veredicto (§7 capacidades). |

**Multi-instancia en 12GB (doctrina, docs/AGENT.md):** orquestación por código (no por
LLM), delegación de profundidad 1, "handbacks" tipados, hechos pasados literales (sin
teléfono descompuesto). Las "N instancias" del verificador son lotes contra UN proceso
NLI residente (~1GB); los retrievers son I/O puro; el 8B se carga bajo demanda. El VLM
futuro (Qwen3-VL-8B) se intercambiaría con el razonador vía llama-server, nunca ambos.

**Puerta pre-registrada:** la cascada NO es el camino por defecto hasta demostrar, a
cobertura fija, menos riesgo que nivel 0 en FEVER dev + set general, con calibración no
peor, y con el acuerdo entre ángulos prediciendo corrección.

## 6. Memoria del agente

- `memoria.py`: sesiones e historial de verificaciones en SQLite
  (`~/.aidam/memoria.db`, override `AIDAM_MEMORIA`). Un veredicto recordado es
  **contexto, nunca atajo**: se muestra («ya verificada el <fecha>: <veredicto>») y se
  re-verifica igual.
- `vectores.py`: memoria semántica de evidencia (embeddings calculados una vez);
  `aidam recordar "<consulta>"` busca por significado. La evidencia recordada participa
  en el nivel 0 de `investigar` (desactivable con `--sin-memoria`).

## 7. El backend HTTP (`aidam/servidor.py`) — el contrato que Electron consume

`aidam interfaz [--host 127.0.0.1] [--puerto 8236] [--sin-navegador]` sirve la UI
estática de `aidam/interfaz/` y expone:

**REST**
- `GET /api/capacidades` → `{"version", "voz": bool, "imagen": bool, "pdf": bool}`
  (la UI esconde/enseña botones según esto; Electron lo usa como health-check de arranque)
- `GET /api/fuentes` → registro de fuentes con categorías
- `GET /api/historial?limite=20` → memoria del agente
- `POST /api/imagen` (multipart) → `{"texto"}` OCR local RapidOCR; `501` si falta extra
- `POST /api/documento` (multipart) → `{"texto"}` PDF (pypdf) o texto plano
- `POST /api/voz?lang=es` (multipart audio) → `{"texto"}` faster-whisper local
  (modelo `AIDAM_MODELO_VOZ`, default `small`, int8 CPU — la GPU queda para el verificador)

**WebSocket `/ws`** (una conexión por ventana, una verificación a la vez):

```
cliente → servidor
  {"tipo": "verificar", "afirmacion": str, "lang": "es", "max_idiomas": 5,
   "preguntas": bool?, "memoria": true, "modo": "auto" | "permisos"}
  {"tipo": "permiso_respuesta", "id": int, "aprobado": bool, "todo": bool}
  {"tipo": "cancelar"}

servidor → cliente
  {"tipo": "progreso",  "mensaje": str}                        # streaming de avance
  {"tipo": "permiso",   "id": int, "accion": str, "detalle": str}   # modo permisos
  {"tipo": "memoria",   "previas": [{veredicto, confianza, fecha}]} # "ya verificada"
  {"tipo": "informe",   "informe": {…}}                        # forma informe_a_dict
  {"tipo": "cancelado"} | {"tipo": "error", "mensaje": str}
```

**Forma del informe** (`models.informe_a_dict`, idéntica a `aidam verificar --json`):

```json
{
  "afirmacion": "…",
  "veredicto": "sustentado|refutado|evidencia_contradictoria|evidencia_insuficiente",
  "confianza": 0.83,
  "tipo": "afirmacion|pregunta",
  "respuesta": "No — la evidencia lo refuta: es.wikipedia.org señala que «…» (confianza 83%; https://…)",
  "hechos": [{
    "hecho": {"texto": "…", "origen": "…"},
    "veredicto": "…", "confianza": 0.83,
    "a_favor":  [{"etiqueta": "sustenta", "prob": 0.95,
                  "evidencia": {"texto": "…", "url": "…", "titulo": "…",
                                 "dominio": "es.wikipedia.org", "fuente": "wikipedia",
                                 "idioma": "es"}}],
    "en_contra": [ … ]
  }]
}
```

Detalles de comportamiento: el verificador se carga UNA vez por proceso del servidor y
se comparte; el pipeline corre en hilo trabajador; una petición de permiso bloquea al
trabajador hasta respuesta/cancelación/desconexión; «Permitir todo» pasa el resto de la
corrida a automático. Servidor mono-usuario en 127.0.0.1, **sin autenticación a propósito**
— no exponer a la red.

## 8. La interfaz web actual (`aidam/interfaz/`: 3 archivos estáticos)

`index.html` + `app.js` (~600 líneas vanilla) + `estilo.css` (tema oscuro `#0f1115`).
Sin build, sin Node: FastAPI la sirve tal cual. Ya implementa: caja de claim, barra de
modo (⚡ automático / 🔒 pedir permiso), progreso en vivo, panel de permisos
(Permitir / Permitir todo / Denegar), aviso de memoria («ya verificada…»), panel de
historial, dictado (local o API del navegador como fallback), imagen→OCR al input,
documento→texto, render del informe con citas. `docs/INTERFAZ.md` la documenta.

## 9. La app de escritorio HOY (`escritorio/`)

Lo que ya existe (funcional en desarrollo):

- `main.js`: al abrir, busca puerto libre → lanza `aidam interfaz --sin-navegador
  --puerto N` → espera `GET /api/capacidades` (hasta ~15s) → abre `BrowserWindow`
  1100×780 (mín 720×520, `contextIsolation: true`, sin `nodeIntegration`) cargando
  `http://127.0.0.1:N`. Al cerrar, mata el backend; si el backend muere, cierra la app.
- Resolución del backend: `$AIDAM_BACKEND_BIN` → `resources/backend/aidam` (release
  empaquetado) → `../.venv/bin/aidam` (desarrollo).
- `package.json`: electron 43, electron-builder 26; `npm run empaquetar` → AppImage +
  .deb en `dist/`; `extraResources` empaqueta `escritorio/backend/`.
- **Pendiente para release autocontenido**: binario PyInstaller del backend (sobre el
  backend ONNX CPU, sin PyTorch/Python) en `escritorio/backend/`. Sin él, el paquete
  solo corre donde está el repo con su `.venv`.
- Gotcha conocido: desde la terminal de VSCode, `env -u ELECTRON_RUN_AS_NODE npm start`.

**El diseño de Electron = (a) el shell nativo + (b) rediseño de la UI web que embebe.**
Ambos viven en este repo; la UI es compartida con `aidam interfaz` en navegador.

## 10. CLI completo (paridad de funciones a considerar en la UI)

| Comando | Qué hace |
|---|---|
| `aidam verificar <texto> [--lang --max-idiomas --preguntas --json --sin-memoria]` | verificación estándar |
| `aidam investigar <texto> [--nivel 0-2 --preguntas --sintesis --json --sin-memoria]` | cascada por señales medidas |
| `aidam agente [--modo plan\|preguntar\|aceptar-ediciones\|lote --voz --preguntas]` | REPL con herramientas |
| `aidam imagen <ruta>` | OCR local → verificación |
| `aidam codigo <a.py b.py…> --llamada "f(x)"` | comparar implementaciones midiendo en sandbox |
| `aidam historial` / `aidam recordar <consulta>` | memoria del agente / búsqueda semántica |
| `aidam fuentes` / `aidam permisos` | registros |
| `aidam interfaz` | el servidor de la UI (lo que lanza Electron) |

## 11. Entorno y modelos

- Máquina de referencia: RTX 5070 **12GB**, CachyOS Linux, Python 3.12 (uv), ~1.3TB libres.
- Presupuesto VRAM (tabla completa en docs/AGENT.md): NLI 280M ~1GB residente; 8B Q4
  ~5.5-6.5GB bajo demanda (worker aislado); whisper turbo int8 ~1.5GB solo en sesiones
  de voz (la UI usa `small` en CPU); TTS Kokoro en CPU.
- Extras pip: `verificador` (torch), `verificador-cpu` (ONNX), `interfaz`
  (fastapi/uvicorn/pypdf), `voz` (faster-whisper, RealtimeSTT, kokoro-onnx, sounddevice),
  `imagen` (rapidocr-onnxruntime), `rastreo` (crawl4ai), `entrenamiento`, `dev`.
- Variables de entorno principales: `AIDAM_BACKEND(=onnx|onnx-mini|torch)`,
  `AIDAM_MODELO_VERIFICADOR`, `AIDAM_MODELO_PREGUNTAS`, `AIDAM_MEMORIA`,
  `AIDAM_PERMISOS`, `AIDAM_AUDITORIA`, `AIDAM_MODELO_VOZ`, `AIDAM_VOZ_TTS`,
  `AIDAM_OCR_LANG`, `AIDAM_SIN_DDG`, `AIDAM_CACHE_*`, `AIDAM_BACKEND_BIN` (Electron).
- Latencias reales a diseñar alrededor: carga del verificador unos segundos (una vez por
  proceso); verificación en vivo típicamente **10-60s** (red + NLI); primera carga del
  8B decenas de segundos; OCR/STT sub-segundo a pocos segundos. La UI vive del canal
  `progreso` — el silencio se percibe como cuelgue.

## 12. Consideraciones de diseño para la app (lo no negociable + lo abierto)

No negociable (viene de los principios):
- **La respuesta primero**: `respuesta` visible siempre, en una respiración; veredicto +
  confianza como refuerzo visual; **citas siempre a un clic** (url + dominio + pasaje).
- **Preguntas ≠ afirmaciones**: sin etiqueta de veredicto para `tipo == "pregunta"`.
- `evidencia_insuficiente` es un resultado honesto, no un error: mostrarlo como tal
  («N pasajes evaluados; conviene reformular»).
- El aviso de memoria («ya verificada el X → veredicto») es contexto: siempre re-verifica.
- Degradación elegante: capacidades ausentes (voz/imagen/pdf) se ocultan o explican con
  el comando de instalación — nunca rompen.
- Privacidad como feature visible: todo local, el audio nunca sale de la máquina.

Abierto para el diseño:
- Bandeja del sistema + atajo global («verificar el portapapeles»), notificaciones al
  terminar corridas largas, arrastrar imagen/PDF a la ventana (los endpoints ya existen).
- Exponer `investigar` (cascada) en la UI: mostrar nivel alcanzado, ángulos y señales —
  hoy es solo CLI; el toggle está listado como pendiente en docs/INTERFAZ.md.
- Veredictos hablados (TTS kokoro ya está en el extra `voz`; falta cablearlo a la UI).
- Multi-ventana: el protocolo ya soporta una verificación por conexión WS.
- Identidad visual: manzana mordida plana de `assets/aidamlogo.svg`; tema oscuro actual
  `#0f1115`; los 4 veredictos tienen semántica de color establecida (verde/rojo/amarillo/gris).

## 13. Separación repo público ↔ releases (estado tras la limpieza de hoy)

- **Nunca en git** (ya ignorado): `models/` (42GB), `data/local/` (cachés, sqlite),
  `escritorio/node_modules|dist|backend|data`, `/build` y `/dist` de la raíz, venvs,
  cachés de herramientas, `.env`.
- **En git (repo público)**: todo el código del agente (`aidam/` incluida `agente/`),
  tests, docs, la UI web (3 archivos estáticos, ~30KB — es la cara del producto y pesa
  nada) y el cascarón Electron (`escritorio/main.js`, `package.json`, READMEs).
- **En releases de GitHub (no en git)**: `escritorio/dist/*.AppImage|.deb` + el binario
  PyInstaller del backend. Los modelos se distribuyen por HuggingFace, no por git.
- Corregido hoy: `escritorio/data/local/search_cache.sqlite` estaba COMMITEADO
  (des-trackeado; era una caché local), y la regla `build/` de la raíz ignoraba
  `escritorio/build/icon.png` (el icono que electron-builder necesita — ahora `/build`
  está anclada a la raíz y el icono se puede versionar).
- Si algún día se quiere sacar la interfaz/escritorio del repo público: mover
  `escritorio/` (y opcionalmente `aidam/interfaz/` + `servidor.py`) a un repo aparte
  que dependa de `aidam` como paquete. Hoy no compensa: son ~35KB de código y la
  separación real (código vs artefactos vs modelos) ya está hecha con el ignore.

## 14. Pendientes conocidos

- Binario autocontenido del backend (PyInstaller + ONNX CPU) → releases instalables.
- `investigar` y TTS en la interfaz; icono `build/icon.png` regenerable desde el SVG.
- Revisión adversarial multi-agente del subsistema `agente/` (auto-revisión hecha;
  3 correcciones aplicadas: juicio del ángulo de negación, markup rich, dedup de ángulos).
- Windows/macOS: electron-builder no cruza plataformas con fiabilidad; hará falta CI o
  máquinas de esas plataformas.

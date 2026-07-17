# The graphical interface

`aidam interfaz` starts a local server and opens the browser. Same pipeline
as the CLI, same verdicts, same citations — a chat-style layout (Claude Code
shape): a left sidebar with **reopenable verification history** and a "new
verification" button, and the conversation area with live progress, the
execution permission system, the agent's memory and document input (image
OCR, PDF, plain text).

**"Glacial" design**: translucent glass panels over obsidian with glacial
blue, a subtle animated ice background (`fondo.js`, self-contained WebGL that
steps aside under `prefers-reduced-motion` or without WebGL), glowing verdict
dots, and typography bundled locally in `fuentes/` (Hanken Grotesk for text,
JetBrains Mono for metadata — no CDN, works offline). The brand couples the
palette to `assets/aidamlogo.svg`: the circular apple mark in a golden-ring
halo, the apple's red for *refuted/stop*, the leaf's green for *supported*,
the signature rule's gold for memory and permission accents. Dark-only by
design — the glass needs the night. No build step, no Node: static files
served by FastAPI.

Deliberate omissions in the UI: **no voice input** (product decision for the
desktop app; the CLI agent keeps its own voice path via `aidam[voz]`), and
**no "LLM questions" toggle** — LLM-guided search is an agent capability,
enabled automatically whenever the local question model is present.
Citations are collapsed into per-fact dropdowns by default. Questions (as
opposed to claims) render an evidence-grounded answer and never a verdict
label (`Informe.tipo == "pregunta"`).

```bash
uv pip install -e ".[verificador,interfaz]"
.venv/bin/aidam interfaz                    # http://127.0.0.1:8236
.venv/bin/aidam interfaz --puerto 9000 --sin-navegador
```

## Execution modes

Chosen per verification, from the bar under the input box:

- **⚡ Automático** — the whole pipeline runs unattended, like the CLI.
- **🔒 Pedir permiso** — every action that reaches the network pauses and asks
  first: each per-fact evidence retrieval, and each LLM-generated follow-up
  search. **Permitir** approves one action; **Permitir todo** approves the rest
  of the run; **Denegar** skips that one search (the fact simply ends up with
  less evidence — deny everything and it comes out `evidencia_insuficiente`).

The permission gate needed no pipeline changes: `pipeline.verificar()` already
accepts injectable `recuperador` / `buscador_preguntas` callables (the same
seam the offline AVeriTeC evaluation uses), and the server wraps them with an
ask-the-user gate over the WebSocket.

## Memory

Verifications are saved to the agent memory (`~/.aidam/memoria.db`, see
`aidam/memoria.py`) and listed in the sidebar. Clicking an entry **reopens the
stored conversation** — claim, date and the full report with its citations —
via `GET /api/verificacion/{id}` (`memoria.informe_por_id()`), without
re-running anything. If a claim was verified before, a new run still shows the
prior verdict as context — and re-verifies anyway: a remembered verdict is
never a substitute (facts change). Uncheck **memoria** to skip both the lookup
and the save for one run.

## Working folder (📁)

AIDAM is an agent, and agents work somewhere: the sidebar's **Carpeta de
trabajo** picks the workspace root. In the desktop app it opens the native
folder dialog (`escritorio/preload.js` → IPC → `dialog.showOpenDialog`); in a
browser there is no real-path dialog, so the UI falls back to typing the path
(the server runs on the same machine). The choice persists, travels with each
`verificar` message, is validated server-side (a typo fails loud, not
silently) and lives on the session as the anchor for the file-facing agent
tools (`aidam/agente/herramientas.py`).

## Documents (📎)

The attach button opens a list of document types; extraction is always local
and the text lands in the input box for review before verifying:

- **🖼 Image / screenshot** — RapidOCR (ONNX) via `/api/imagen`; requires
  `aidam[imagen]`.
- **📄 PDF** — pypdf via `/api/documento`; ships with `aidam[interfaz]`.
- **📃 Plain text** (.txt, .md, .csv) — `/api/documento`, no extra needed.

Paste and drag-and-drop route by file type automatically. Endpoints answer
`501` with the install command when a dependency is missing;
`/api/capacidades` tells the UI what is available. (`/api/voz` still exists
server-side for other consumers, but the UI does not use it.)

## WebSocket protocol

One connection per tab, one verification at a time. JSON messages:

```
client → server
  {"tipo": "verificar", "afirmacion": str, "lang": "es", "max_idiomas": 5,
   "memoria": true, "modo": "auto" | "permisos", "carpeta": str?}
  # "preguntas" (bool) accepted but optional: absent → the agent decides
  # (LLM-guided search runs whenever the local model is present)
  # "carpeta" (optional): the agent's working folder — validated server-side
  # (must exist) and kept on the session as the workspace root for
  # file-facing agent tools
  {"tipo": "permiso_respuesta", "id": int, "aprobado": bool, "todo": bool}
  {"tipo": "cancelar"}

server → client
  {"tipo": "progreso",  "mensaje": str}
  {"tipo": "permiso",   "id": int, "accion": str, "detalle": str}
  {"tipo": "memoria",   "previas": [{"veredicto", "confianza", "fecha"}, …]}
  {"tipo": "informe",   "informe": {…}}        # same shape as `verificar --json`
  {"tipo": "cancelado"}
  {"tipo": "error",     "mensaje": str}
```

The report shape is `models.informe_a_dict()` — shared with the CLI's
`--json`, so anything that consumes one consumes the other.

Concurrency, in one paragraph: the blocking pipeline runs in a worker thread;
progress events flow back through the event loop (ordering preserved); a
permission request parks the worker on a `threading.Event` until the user
answers, cancels, or the tab disconnects (disconnect releases every pending
wait, so nothing leaks). The verifier loads once per server process and is
shared across connections.

## Testing

`tests/test_servidor.py` exercises the protocol offline: a fake
`verificar_fn` honours the pipeline contract and injected `recuperar_fn`
replaces live retrieval *behind* the permission gate, so the gate itself is
tested without network. Runtime verification (real server, real claim, real
sources) is described in `.claude/skills/verify`.

## The desktop app (`escritorio/`)

The native-window app lives in `escritorio/` — an Electron shell (Node, not
Python) that spawns `aidam interfaz` on a free localhost port when opened and
kills it on close. Its icon is derived from `assets/aidamlogo.svg` (the flat
bitten apple + signature rule). Development: `cd escritorio && npm install &&
npm start`.

**GitHub releases are one command**: `git tag v* && git push --tags` — the
`release.yml` workflow builds installers on Linux (AppImage/deb), Windows
(NSIS) and macOS (dmg), each embedding the self-contained backend
(`packaging/empaquetar_backend.py`: PyInstaller over the ONNX CPU backend, no
Python/PyTorch needed on the target). The verifier model downloads from
HuggingFace on first use (`aidam/modelos.py`). Details and honest caveats in
`escritorio/README.md`.

## Deliberately not done yet

- **Spoken verdicts** (TTS): the `voz` extra already ships kokoro-onnx for
  the CLI agent; wiring it to the UI is pending.
- **`investigar` in the UI**: the cascade orchestrator (`aidam investigar`)
  will get a toggle once its CLI surface settles.
- **Authentication**: the server binds to 127.0.0.1 and is single-user by
  design. Do not expose it to a network as-is.

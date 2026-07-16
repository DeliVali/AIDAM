# The graphical interface

`aidam interfaz` starts a local server and opens the browser. Same pipeline
as the CLI, same verdicts, same citations — plus live progress, an execution
permission system, the agent's memory, and optional voice and image input.
No build step, no Node: the UI is three static files (`aidam/interfaz/`)
served by FastAPI, so `pip install` is the whole frontend toolchain.

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
`aidam/memoria.py`) and browsable from the **Historial** panel. If a claim was
verified before, the UI shows when and with what verdict — and re-verifies it
anyway: a remembered verdict is context, never a substitute (facts change).
Uncheck **memoria** to skip both the lookup and the save for one run.

## Voice and images (optional extras)

- **🎤 Voice** — with `aidam[voz]` installed, dictation is transcribed
  **locally** with faster-whisper (`/api/voz`; model via `AIDAM_MODELO_VOZ`,
  default `small`, int8 on CPU so the GPU stays free for the verifier). The
  audio never leaves the machine. Without the extra, the UI falls back to the
  browser's speech API where available (Chromium sends audio to Google —
  the local path exists precisely to avoid that).
- **📷 Images** — with `aidam[imagen]` installed, attach / paste / drop a
  screenshot and the claim text is extracted with RapidOCR (ONNX, local,
  `/api/imagen`) into the input box for review before verifying.

Both endpoints answer `501` with the install command when the extra is
missing, and `/api/capacidades` tells the UI what is available.

## WebSocket protocol

One connection per tab, one verification at a time. JSON messages:

```
client → server
  {"tipo": "verificar", "afirmacion": str, "lang": "es", "max_idiomas": 5,
   "preguntas": false, "memoria": true, "modo": "auto" | "permisos"}
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

## Deliberately not done yet

- **Desktop packaging** (Tauri/Electron wrapper): the web app is the core
  either way; wrap it when someone actually needs a dock icon.
- **Spoken verdicts** (TTS): the `voz` extra already ships kokoro-onnx for
  the CLI agent; wiring it to the UI is pending.
- **`investigar` in the UI**: the cascade orchestrator (`aidam investigar`)
  will get a toggle once its CLI surface settles.
- **Authentication**: the server binds to 127.0.0.1 and is single-user by
  design. Do not expose it to a network as-is.

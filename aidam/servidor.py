"""Local web server for the graphical interface: `aidam interfaz`.

Serves the static UI in `aidam/interfaz/` and exposes the pipeline over a
WebSocket. Two execution modes, chosen per verification by the client:

- `auto`: the whole pipeline runs unattended (like the CLI).
- `permisos`: every action that reaches the network — evidence retrieval per
  fact, each LLM-generated follow-up search — pauses and asks the user first.
  Denying skips that one action; the pipeline continues with less evidence.

The permission seam needs NO changes to the pipeline: `pipeline.verificar()`
already accepts injectable `recuperador` / `buscador_preguntas` callables
(the same seam the offline AVeriTeC evaluation uses), so this module wraps
them with an ask-the-user gate.

WebSocket protocol (JSON messages, documented in docs/INTERFAZ.md):

  client → server
    {"tipo": "verificar", "afirmacion": str, "lang": str, "max_idiomas": int,
     "modo": "auto" | "permisos", "carpeta": str?}
    # "preguntas" (bool) is accepted but optional: if absent, the agent
    # decides — LLM-guided search runs whenever the local model is present.
    # "carpeta" (optional) is the agent's working folder, chosen visually in
    # the UI; it is validated (must exist) and kept on the session as the
    # workspace root for file-facing agent tools.
    {"tipo": "permiso_respuesta", "id": int, "aprobado": bool, "todo": bool}
    {"tipo": "cancelar"}

  server → client
    {"tipo": "progreso", "mensaje": str}
    {"tipo": "permiso", "id": int, "accion": str, "detalle": str}
    {"tipo": "memoria", "previas": [{"veredicto", "confianza", "fecha"}, …]}
    {"tipo": "informe", "informe": {…}}      # models.informe_a_dict shape
    {"tipo": "cancelado"}
    {"tipo": "error", "mensaje": str}

The client may add "memoria": false to a `verificar` message to skip both
the history lookup and the save (the CLI's --sin-memoria).
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import itertools
import json
import os
import threading
import webbrowser
from functools import lru_cache
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .models import Informe, Veredicto, informe_a_dict

RUTA_INTERFAZ = Path(__file__).parent / "interfaz"

_FALTA_IMAGEN = (
    "Reconocimiento de imágenes no instalado. "
    "Instálalo con: uv pip install -e '.[imagen]'"
)
_FALTA_VOZ = (
    "Reconocimiento de voz local no instalado. "
    "Instálalo con: uv pip install -e '.[voz]'"
)
_FALTA_PDF = (
    "Lectura de PDF no instalada. "
    "Instálala con: uv pip install -e '.[interfaz]' (incluye pypdf)"
)


def _preguntas_disponibles() -> bool:
    """LLM-guided search is an agent capability, not a user toggle: it runs
    whenever the local question model is present, and silently doesn't when
    it isn't (the pipeline already degrades gracefully)."""
    try:
        from .questions import ruta_modelo

        return ruta_modelo() is not None
    except Exception:
        return False


class _Cancelado(Exception):
    """Raised inside the worker thread when the user cancels the run."""


@lru_cache(maxsize=1)
def _verificador_cacheado():
    """Loads the NLI verifier ONCE per server process (same rationale as the
    question generator in pipeline.py: reloading leaks memory)."""
    from .verify import crear_verificador

    return crear_verificador()


def _verificar_por_defecto(afirmacion: str, *, progreso, **kwargs) -> Informe:
    from .pipeline import verificar

    if _verificador_cacheado.cache_info().currsize == 0:
        # First-run installs (packaged app, fresh CPU env) may need to fetch
        # the model from HuggingFace before anything can load.
        from .modelos import asegurar_verificador

        asegurar_verificador(progreso)
        progreso("Cargando el núcleo verificador…")
    return verificar(
        afirmacion, progreso=progreso, verificador=_verificador_cacheado(), **kwargs
    )


class _Sesion:
    """One WebSocket connection: at most one verification at a time.

    The blocking pipeline runs in a worker thread (`asyncio.to_thread`); events
    flow back to the client via `run_coroutine_threadsafe`, which preserves
    ordering. A permission request blocks the worker on a `threading.Event`
    until the user answers, cancels, or disconnects.
    """

    def __init__(
        self,
        ws: WebSocket,
        verificar_fn: Callable[..., Informe],
        obtener_memoria: Callable[[], object | None] = lambda: None,
        recuperar_fn: Callable[..., list] | None = None,
        buscar_web_fn: Callable[..., list] | None = None,
    ):
        self.ws = ws
        self.verificar_fn = verificar_fn
        self.obtener_memoria = obtener_memoria
        # Injectable so tests exercise the permission gate without network.
        self.recuperar_fn = recuperar_fn
        self.buscar_web_fn = buscar_web_fn
        self.loop = asyncio.get_running_loop()
        self.modo = "auto"
        self.carpeta_trabajo: Path | None = None
        self.tarea: asyncio.Task | None = None
        self.cancelado = threading.Event()
        self._permisos: dict[int, tuple[threading.Event, dict]] = {}
        self._ids = itertools.count(1)

    # -- sending (async side and worker thread) ------------------------------

    async def _enviar_async(self, evento: dict) -> None:
        try:
            await self.ws.send_text(json.dumps(evento, ensure_ascii=False))
        except Exception:
            pass  # client gone; the run is being cancelled anyway

    def _enviar(self, evento: dict) -> None:
        """Thread-safe fire-and-forget send from the worker thread."""
        asyncio.run_coroutine_threadsafe(self._enviar_async(evento), self.loop)

    # -- permissions ----------------------------------------------------------

    def pedir_permiso(self, accion: str, detalle: str) -> bool:
        """Blocks the worker thread until the user answers. `auto` mode always
        grants; cancellation or disconnect raises instead of leaking the wait."""
        if self.cancelado.is_set():
            raise _Cancelado()
        if self.modo != "permisos":
            return True
        id_permiso = next(self._ids)
        listo = threading.Event()
        respuesta = {"aprobado": False}
        self._permisos[id_permiso] = (listo, respuesta)
        self._enviar(
            {"tipo": "permiso", "id": id_permiso, "accion": accion, "detalle": detalle}
        )
        listo.wait()
        self._permisos.pop(id_permiso, None)
        if self.cancelado.is_set():
            raise _Cancelado()
        return respuesta["aprobado"]

    def responder_permiso(self, id_permiso, aprobado, todo=False) -> None:
        if todo and aprobado:
            self.modo = "auto"  # «permitir todo»: the rest of this run is automatic
        par = self._permisos.get(id_permiso)
        if par is not None:
            par[1]["aprobado"] = bool(aprobado)
            par[0].set()

    def cancelar(self) -> None:
        self.cancelado.set()
        for listo, _respuesta in list(self._permisos.values()):
            listo.set()

    # -- gated pipeline seams --------------------------------------------------

    def _recuperador(self, hecho, lang="es", max_idiomas=5, categoria=None):
        if self.cancelado.is_set():
            raise _Cancelado()
        # Router slugs are identifiers; the user reads proper Spanish.
        legible = {"programacion": "programación", "matematicas": "matemáticas"}
        permitido = self.pedir_permiso(
            "buscar_evidencia",
            f"Buscar evidencia sobre «{hecho.texto}» "
            f"(fuentes de la categoría: {legible.get(categoria, categoria) or 'todas'})",
        )
        if not permitido:
            self._enviar(
                {"tipo": "progreso", "mensaje": "Búsqueda omitida por decisión del usuario"}
            )
            return []
        recuperar = self.recuperar_fn
        if recuperar is None:
            from .retrieve import recuperar

        return recuperar(hecho, lang=lang, max_idiomas=max_idiomas, categoria=categoria)

    def _buscador_preguntas(self, lang: str):
        def buscar(pregunta: str):
            if self.cancelado.is_set():
                raise _Cancelado()
            if not self.pedir_permiso(
                "buscar_pregunta", f"Buscar en la web: «{pregunta}»"
            ):
                self._enviar(
                    {"tipo": "progreso", "mensaje": "Pregunta omitida por decisión del usuario"}
                )
                return []
            buscar_web = self.buscar_web_fn
            if buscar_web is None:
                from .retrieve import buscar_web

            # Same defaults pipeline.verificar uses when nothing is injected.
            return buscar_web(pregunta, max_resultados=4, lang=lang, paginas_completas=1)

        return buscar

    # -- run -------------------------------------------------------------------

    def _verificar_bloqueante(
        self, afirmacion: str, lang: str, max_idiomas: int, preguntas: bool,
        excluir_dominios: set[str] | None = None,
    ) -> Informe:
        def progreso(mensaje: str) -> None:
            # The pipeline reports progress often, so this doubles as the
            # cancellation check between stages.
            if self.cancelado.is_set():
                raise _Cancelado()
            self._enviar({"tipo": "progreso", "mensaje": mensaje})

        return self.verificar_fn(
            afirmacion,
            lang=lang,
            max_idiomas=max_idiomas,
            preguntas=preguntas,
            progreso=progreso,
            recuperador=self._recuperador,
            buscador_preguntas=self._buscador_preguntas(lang),
            excluir_dominios=excluir_dominios,
        )

    async def ejecutar(self, peticion: dict) -> None:
        afirmacion = (peticion.get("afirmacion") or "").strip()
        if not afirmacion:
            await self._enviar_async(
                {"tipo": "error", "mensaje": "La afirmación está vacía."}
            )
            return
        self.cancelado.clear()
        self.modo = peticion.get("modo", "auto")

        # Working folder: the agent's workspace root, chosen visually in the
        # UI. Validated here so a typo fails loud, then kept on the session
        # for the file-facing agent tools (agente/herramientas) to anchor on.
        carpeta = (peticion.get("carpeta") or "").strip()
        if carpeta:
            ruta = Path(carpeta).expanduser()
            if not ruta.is_dir():
                await self._enviar_async(
                    {
                        "tipo": "error",
                        "mensaje": f"La carpeta de trabajo no existe: {ruta}",
                    }
                )
                return
            self.carpeta_trabajo = ruta

        # Conversational context: a follow-up («¿y en el contexto de…?»)
        # is rewritten self-contained against the best antecedent turn —
        # recent by default, an older one when the meaning matches it
        # better. RAM only; the interpretation is SHOWN, never silent.
        from .agente.contexto import ContextoConversacion, es_rechazo, respuesta_social

        if not hasattr(self, "contexto"):
            self.contexto = ContextoConversacion()
            self.pregunta_activa: str | None = None
            self.dominios_rechazados: set[str] = set()

        social = respuesta_social(afirmacion)
        if social is not None:
            # A greeting/thanks is a conversation, not a claim: answer like
            # a person, verify nothing, spend nothing.
            await self._enviar_async({
                "tipo": "informe",
                "informe": informe_a_dict(Informe(
                    afirmacion=afirmacion, veredicto=Veredicto.INSUFICIENTE,
                    confianza=1.0, hechos=[], tipo="pregunta", respuesta=social,
                )),
            })
            return

        # Spelling cleanup, questions only, always shown (never claims:
        # their exact wording is what gets verified).
        from .agente.ortografia import corregir_pregunta
        from .agente.sintesis import es_pregunta

        if es_pregunta(afirmacion):
            corregida, cambios = corregir_pregunta(
                afirmacion, peticion.get("lang", "es"))
            if cambios:
                await self._enviar_async(
                    {"tipo": "progreso",
                     "mensaje": "ortografía interpretada: " + ", ".join(cambios)})
                afirmacion = corregida

        excluir: set[str] = set()
        if es_rechazo(afirmacion) and self.pregunta_activa:
            # «no, no es esa» is a dialogue act, not a claim: re-answer the
            # SAME question with the rejected sources stepping aside.
            self.dominios_rechazados |= set(
                re.findall(r"[a-z0-9.-]+\.[a-z]{2,}", getattr(self, "ultima_respuesta", ""))
            )
            afirmacion = self.pregunta_activa
            excluir = self.dominios_rechazados
            await self._enviar_async(
                {"tipo": "progreso",
                 "mensaje": f"entendido — busco otra respuesta para: «{afirmacion}» "
                            f"(excluyendo {', '.join(sorted(excluir)) or 'nada'})"}
            )
        else:
            resuelta = self.contexto.resolver(afirmacion)
            if resuelta != afirmacion:
                await self._enviar_async(
                    {"tipo": "progreso",
                     "mensaje": f"pregunta interpretada con el contexto: «{resuelta}»"}
                )
                afirmacion = resuelta
            self.pregunta_activa = afirmacion
            self.dominios_rechazados = set()

        # Remembered verdicts are CONTEXT for the user, never a shortcut:
        # the claim is re-verified below regardless (same rule as the CLI).
        memoria = (
            self.obtener_memoria() if bool(peticion.get("memoria", True)) else None
        )
        if memoria is not None:
            try:
                previas = [
                    {k: p[k] for k in ("veredicto", "confianza", "fecha")}
                    for p in memoria.buscar(afirmacion)
                ]
            except Exception:
                previas = []
            if previas:
                await self._enviar_async({"tipo": "memoria", "previas": previas})

        preguntas = peticion.get("preguntas")
        if preguntas is None:  # the agent decides, by model availability
            preguntas = _preguntas_disponibles()

        try:
            informe = await asyncio.to_thread(
                self._verificar_bloqueante,
                afirmacion,
                peticion.get("lang", "es"),
                int(peticion.get("max_idiomas", 5)),
                bool(preguntas),
                excluir or None,
            )
            self.ultima_respuesta = informe.respuesta or ""
            if memoria is not None:
                try:
                    memoria.guardar(informe)
                except Exception:
                    pass  # a memory failure must never eat the verdict
            await self._enviar_async(
                {"tipo": "informe", "informe": informe_a_dict(informe)}
            )
        except _Cancelado:
            await self._enviar_async({"tipo": "cancelado"})
        except Exception as exc:  # surface the failure instead of a dead socket
            await self._enviar_async(
                {"tipo": "error", "mensaje": f"La verificación falló: {exc}"}
            )


# -- optional capabilities: OCR and local voice --------------------------------


@lru_cache(maxsize=1)
def _motor_ocr():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _extraer_texto_imagen(datos: bytes) -> str:
    resultado, _tiempos = _motor_ocr()(datos)
    return "\n".join(linea[1] for linea in resultado or [])


def _extraer_texto_documento(nombre: str, datos: bytes) -> str:
    """PDF via pypdf; anything else is treated as UTF-8 text (.txt, .md…)."""
    if Path(nombre or "").suffix.lower() == ".pdf":
        from pypdf import PdfReader

        lector = PdfReader(io.BytesIO(datos))
        return "\n".join((pagina.extract_text() or "") for pagina in lector.pages).strip()
    return datos.decode("utf-8", errors="replace").strip()


@lru_cache(maxsize=1)
def _modelo_voz():
    from faster_whisper import WhisperModel

    # int8 on CPU: reliable everywhere; the GPU stays free for the verifier.
    nombre = os.environ.get("AIDAM_MODELO_VOZ", "small")
    return WhisperModel(nombre, device="cpu", compute_type="int8")


def _transcribir(datos: bytes, lang: str) -> str:
    segmentos, _info = _modelo_voz().transcribe(
        io.BytesIO(datos), language=lang or None
    )
    return " ".join(s.text.strip() for s in segmentos).strip()


# -- app ------------------------------------------------------------------------


def crear_app(
    verificar_fn: Callable[..., Informe] | None = None,
    ruta_memoria: str | None = None,
    recuperar_fn: Callable[..., list] | None = None,
    buscar_web_fn: Callable[..., list] | None = None,
) -> FastAPI:
    """Builds the FastAPI app. `verificar_fn` accepts the same contract as
    `pipeline.verificar` — tests inject a fake to exercise the protocol
    without models or network. `ruta_memoria` overrides where the agent
    memory lives (tests point it at a temp file); `recuperar_fn` and
    `buscar_web_fn` replace live retrieval behind the permission gate."""
    verificar_fn = verificar_fn or _verificar_por_defecto
    app = FastAPI(title="AIDAM", version=__version__)
    app.state.memoria = None

    def obtener_memoria():
        """One agent-memory session per server run, created lazily; if the
        memory can't open, the interface keeps working without it."""
        if app.state.memoria is None:
            try:
                from .memoria import MemoriaAgente

                app.state.memoria = MemoriaAgente(ruta_memoria)
            except Exception:
                return None
        return app.state.memoria


    @app.post("/v1/chat/completions")
    async def chat_completions(peticion: dict):
        """OpenAI-compatible endpoint: AIDAM as a provider for assistant
        infrastructure (OpenClaw gateways, and any OpenAI-style client).
        Jeffrey's integration path (2026-07-16): instead of building 29
        messenger bridges, expose the standard surface those gateways
        already speak — verification from WhatsApp/Telegram/Discord comes
        free through them. Non-streaming; the verdict/answer text is the
        assistant message, with the same dialogue routing as the UI
        (social, computable, question, claim)."""
        mensajes = peticion.get("messages") or []
        usuario = next(
            (m.get("content", "") for m in reversed(mensajes)
             if m.get("role") == "user" and (m.get("content") or "").strip()),
            "",
        )
        if not usuario:
            return JSONResponse({"error": {"message": "sin mensaje de usuario"}}, status_code=400)

        from .agente.contexto import respuesta_social

        social = respuesta_social(usuario)
        if social is not None:
            texto = social
        else:
            def progreso(_m: str) -> None:
                pass

            informe = await asyncio.to_thread(
                verificar_fn, usuario, progreso=progreso,
            )
            if informe.tipo == "pregunta":
                texto = informe.respuesta
            else:
                estilo = {
                    "sustentado": "✓ SUSTENTADO",
                    "refutado": "✗ REFUTADO",
                    "evidencia_contradictoria": "⚡ EVIDENCIA CONTRADICTORIA",
                    "evidencia_insuficiente": "? EVIDENCIA INSUFICIENTE",
                }.get(informe.veredicto.value, informe.veredicto.value)
                texto = f"{estilo} · confianza {informe.confianza:.0%}\n{informe.respuesta}"
            try:
                memoria = obtener_memoria()
                if memoria is not None and social is None:
                    memoria.guardar(informe)
            except Exception:
                pass

        import time as _t

        return {
            "id": "aidam-chat",
            "object": "chat.completion",
            "created": int(_t.time()),
            "model": peticion.get("model", "aidam-verificador"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": texto},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    @app.get("/api/capacidades")
    def capacidades():
        return {
            "version": __version__,
            "voz": importlib.util.find_spec("faster_whisper") is not None,
            "imagen": importlib.util.find_spec("rapidocr_onnxruntime") is not None,
            "pdf": importlib.util.find_spec("pypdf") is not None,
        }

    @app.get("/api/fuentes")
    def api_fuentes():
        from .retrieve import FUENTES

        return {
            "fuentes": [
                {
                    "nombre": nombre,
                    "descripcion": descripcion,
                    "categorias": sorted(categorias) if categorias else [],
                }
                for nombre, (descripcion, categorias, _funcion) in FUENTES.items()
            ]
        }

    # async on purpose: the SQLite connection lives on the event-loop thread
    # (a sync endpoint would run in the threadpool and trip check_same_thread).
    @app.get("/api/historial")
    async def api_historial(limite: int = 20):
        memoria = obtener_memoria()
        if memoria is None:
            return {"historial": []}
        try:
            return {"historial": memoria.historial(limite)}
        except Exception:
            return {"historial": []}

    @app.get("/api/verificacion/{id_verificacion}")
    async def api_verificacion(id_verificacion: int):
        """Stored report by id: the interface reopens past conversations."""
        memoria = obtener_memoria()
        guardada = None
        if memoria is not None:
            try:
                guardada = memoria.informe_por_id(id_verificacion)
            except Exception:
                guardada = None
        if guardada is None:
            return JSONResponse(
                status_code=404, content={"error": "Verificación no encontrada."}
            )
        return guardada

    @app.post("/api/imagen")
    async def api_imagen(archivo: UploadFile):
        if importlib.util.find_spec("rapidocr_onnxruntime") is None:
            return JSONResponse(status_code=501, content={"error": _FALTA_IMAGEN})
        datos = await archivo.read()
        texto = await asyncio.to_thread(_extraer_texto_imagen, datos)
        return {"texto": texto}

    @app.post("/api/documento")
    async def api_documento(archivo: UploadFile):
        nombre = archivo.filename or ""
        if (
            nombre.lower().endswith(".pdf")
            and importlib.util.find_spec("pypdf") is None
        ):
            return JSONResponse(status_code=501, content={"error": _FALTA_PDF})
        datos = await archivo.read()
        try:
            texto = await asyncio.to_thread(_extraer_texto_documento, nombre, datos)
        except Exception as exc:
            return JSONResponse(
                status_code=422,
                content={"error": f"No se pudo leer el documento: {exc}"},
            )
        return {"texto": texto}

    @app.post("/api/voz")
    async def api_voz(archivo: UploadFile, lang: str = "es"):
        if importlib.util.find_spec("faster_whisper") is None:
            return JSONResponse(status_code=501, content={"error": _FALTA_VOZ})
        datos = await archivo.read()
        texto = await asyncio.to_thread(_transcribir, datos, lang)
        return {"texto": texto}

    @app.websocket("/ws")
    async def ws_verificar(ws: WebSocket):
        await ws.accept()
        sesion = _Sesion(
            ws, verificar_fn, obtener_memoria, recuperar_fn, buscar_web_fn
        )
        try:
            while True:
                try:
                    mensaje = json.loads(await ws.receive_text())
                except json.JSONDecodeError:
                    await sesion._enviar_async(
                        {"tipo": "error", "mensaje": "Mensaje malformado (no es JSON)."}
                    )
                    continue
                tipo = mensaje.get("tipo")
                if tipo == "verificar":
                    if sesion.tarea is not None and not sesion.tarea.done():
                        await sesion._enviar_async(
                            {
                                "tipo": "error",
                                "mensaje": "Ya hay una verificación en curso.",
                            }
                        )
                    else:
                        sesion.tarea = asyncio.create_task(sesion.ejecutar(mensaje))
                elif tipo == "permiso_respuesta":
                    sesion.responder_permiso(
                        mensaje.get("id"),
                        mensaje.get("aprobado", False),
                        mensaje.get("todo", False),
                    )
                elif tipo == "cancelar":
                    sesion.cancelar()
                else:
                    await sesion._enviar_async(
                        {"tipo": "error", "mensaje": f"Tipo desconocido: {tipo!r}"}
                    )
        except WebSocketDisconnect:
            pass
        finally:
            sesion.cancelar()  # unblocks any worker waiting on a permission

    # Mounted last so /api/* and /ws win; html=True serves index.html at «/».
    app.mount("/", StaticFiles(directory=RUTA_INTERFAZ, html=True), name="interfaz")
    return app


def servir(host: str = "127.0.0.1", puerto: int = 8236, abrir: bool = True) -> None:
    """Starts the local server and (optionally) opens the browser."""
    import uvicorn

    if abrir:
        threading.Timer(
            1.0, webbrowser.open, args=(f"http://{host}:{puerto}",)
        ).start()
    uvicorn.run(crear_app(), host=host, port=puerto, log_level="warning")

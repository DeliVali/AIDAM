/* AIDAM — lógica de la interfaz. Vanilla JS, sin dependencias.
 *
 * Protocolo WebSocket documentado en aidam/servidor.py y docs/INTERFAZ.md.
 */

"use strict";

// ---------------------------------------------------------------- estado ----

const $ = (id) => document.getElementById(id);

const ui = {
  conversacion: $("conversacion"),
  bienvenida: $("bienvenida"),
  entrada: $("entrada"),
  enviar: $("boton-enviar"),
  voz: $("boton-voz"),
  imagen: $("boton-imagen"),
  selectorImagen: $("selector-imagen"),
  avisoAdjunto: $("aviso-adjunto"),
  modoAuto: $("modo-auto"),
  modoPermisos: $("modo-permisos"),
  idioma: $("idioma"),
  preguntas: $("opcion-preguntas"),
  memoria: $("opcion-memoria"),
  estadoConexion: $("estado-conexion"),
  estadoTexto: $("estado-texto"),
  avisos: $("avisos"),
  botonHistorial: $("boton-historial"),
  panelHistorial: $("panel-historial"),
  cerrarHistorial: $("cerrar-historial"),
  listaHistorial: $("lista-historial"),
};

const estado = {
  ws: null,
  conectado: false,
  intentoReconexion: 0,
  enCurso: false,     // hay una verificación corriendo
  turno: null,        // elementos DOM del turno activo
  capacidades: { voz: false, imagen: false },
  grabadora: null,    // MediaRecorder activo
  reconocedor: null,  // SpeechRecognition del navegador activo
};

const VEREDICTOS = {
  sustentado: { clase: "sustentado", icono: "✓", titulo: "Sustentado" },
  refutado: { clase: "refutado", icono: "✗", titulo: "Refutado" },
  evidencia_contradictoria: { clase: "contradictorio", icono: "⚡", titulo: "Evidencia contradictoria" },
  evidencia_insuficiente: { clase: "insuficiente", icono: "?", titulo: "Evidencia insuficiente" },
};

// ------------------------------------------------------------ utilidades ----

function crear(tag, clase, texto) {
  const el = document.createElement(tag);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

function avisar(mensaje, esError) {
  const aviso = crear("div", "aviso" + (esError ? " error" : ""), mensaje);
  ui.avisos.appendChild(aviso);
  setTimeout(() => aviso.remove(), 7000);
}

function bajarConversacion() {
  ui.conversacion.scrollTop = ui.conversacion.scrollHeight;
}

function fechaCorta(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------- preferencias ----

function cargarPreferencias() {
  let prefs = {};
  try { prefs = JSON.parse(localStorage.getItem("aidam.prefs") || "{}"); } catch {}
  if (prefs.modo === "permisos") activarModo("permisos");
  if (prefs.idioma) ui.idioma.value = prefs.idioma;
  ui.preguntas.checked = Boolean(prefs.preguntas);
  ui.memoria.checked = prefs.memoria !== false;
}

function guardarPreferencias() {
  localStorage.setItem("aidam.prefs", JSON.stringify({
    modo: ui.modoPermisos.classList.contains("activo") ? "permisos" : "auto",
    idioma: ui.idioma.value,
    preguntas: ui.preguntas.checked,
    memoria: ui.memoria.checked,
  }));
}

function activarModo(modo) {
  ui.modoAuto.classList.toggle("activo", modo === "auto");
  ui.modoPermisos.classList.toggle("activo", modo === "permisos");
}

ui.modoAuto.addEventListener("click", () => { activarModo("auto"); guardarPreferencias(); });
ui.modoPermisos.addEventListener("click", () => { activarModo("permisos"); guardarPreferencias(); });
ui.idioma.addEventListener("change", guardarPreferencias);
ui.preguntas.addEventListener("change", guardarPreferencias);
ui.memoria.addEventListener("change", guardarPreferencias);

// -------------------------------------------------------------- websocket ----

function conectar() {
  const protocolo = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocolo}://${location.host}/ws`);
  estado.ws = ws;

  ws.onopen = () => {
    estado.conectado = true;
    estado.intentoReconexion = 0;
    ui.estadoConexion.className = "estado-conexion conectado";
    ui.estadoTexto.textContent = "conectado";
  };

  ws.onmessage = (evento) => {
    let mensaje;
    try { mensaje = JSON.parse(evento.data); } catch { return; }
    manejarMensaje(mensaje);
  };

  ws.onclose = () => {
    estado.conectado = false;
    ui.estadoConexion.className = "estado-conexion desconectado";
    ui.estadoTexto.textContent = "desconectado";
    if (estado.enCurso) terminarTurno();
    const espera = Math.min(10000, 500 * 2 ** estado.intentoReconexion++);
    setTimeout(conectar, espera);
  };
}

function manejarMensaje(m) {
  switch (m.tipo) {
    case "progreso": return anotarProgreso(m.mensaje);
    case "permiso": return pedirPermiso(m);
    case "memoria": return mostrarMemoria(m.previas);
    case "informe": return mostrarInforme(m.informe);
    case "cancelado": return mostrarCancelado();
    case "error": return mostrarError(m.mensaje);
  }
}

// ------------------------------------------------------- envío y progreso ----

function enviarVerificacion() {
  const afirmacion = ui.entrada.value.trim();
  if (!afirmacion || !estado.conectado) return;
  if (estado.enCurso) return;

  const modo = ui.modoPermisos.classList.contains("activo") ? "permisos" : "auto";
  estado.ws.send(JSON.stringify({
    tipo: "verificar",
    afirmacion,
    lang: ui.idioma.value,
    preguntas: ui.preguntas.checked,
    memoria: ui.memoria.checked,
    modo,
  }));

  ui.bienvenida?.remove();
  ui.bienvenida = null;

  const turno = crear("div", "turno");
  turno.appendChild(crear("div", "burbuja-usuario", afirmacion));
  const registro = crear("div", "registro");
  turno.appendChild(registro);
  ui.conversacion.appendChild(turno);

  estado.turno = { contenedor: turno, registro, pasos: 0 };
  estado.enCurso = true;
  ui.entrada.value = "";
  ajustarAltura();
  ui.enviar.textContent = "■";
  ui.enviar.title = "Detener la verificación";
  ui.enviar.classList.add("detener");
  bajarConversacion();
}

function anotarProgreso(mensaje) {
  const t = estado.turno;
  if (!t) return;
  t.registro.querySelector(".actual")?.classList.remove("actual");
  t.registro.appendChild(crear("div", "actual", mensaje));
  t.pasos++;
  t.registro.scrollTop = t.registro.scrollHeight;
  bajarConversacion();
}

function terminarTurno() {
  const t = estado.turno;
  estado.enCurso = false;
  ui.enviar.textContent = "➤";
  ui.enviar.title = "Verificar (Enter)";
  ui.enviar.classList.remove("detener");
  if (!t) return;

  // El registro en vivo se pliega a un resumen expandible.
  t.registro.querySelector(".actual")?.classList.remove("actual");
  const plegado = document.createElement("details");
  plegado.className = "registro-plegado";
  const resumen = crear("summary", null, `ver proceso (${t.pasos} pasos)`);
  plegado.appendChild(resumen);
  t.registro.replaceWith(plegado);
  plegado.appendChild(t.registro);
  estado.turno = null;
}

function cancelarVerificacion() {
  if (estado.conectado) estado.ws.send(JSON.stringify({ tipo: "cancelar" }));
}

// ---------------------------------------------------------------- permisos ----

function pedirPermiso(m) {
  const t = estado.turno;
  if (!t) return;

  const tarjeta = crear("div", "tarjeta-permiso");
  tarjeta.appendChild(crear("div", "permiso-titulo", "🔒 El agente pide permiso"));
  tarjeta.appendChild(crear("div", "permiso-detalle", m.detalle));
  const botones = crear("div", "permiso-botones");

  const responder = (aprobado, todo, etiqueta) => {
    estado.ws.send(JSON.stringify({
      tipo: "permiso_respuesta", id: m.id, aprobado, todo: Boolean(todo),
    }));
    tarjeta.classList.add("respondida");
    botones.querySelectorAll("button").forEach((b) => (b.disabled = true));
    tarjeta.appendChild(crear("div", "permiso-resultado", etiqueta));
  };

  const permitir = crear("button", "boton-primario", "Permitir");
  permitir.onclick = () => responder(true, false, "✓ permitido");
  const todo = crear("button", "boton-secundario", "Permitir todo");
  todo.title = "Aprueba esta acción y el resto de la verificación sigue en automático";
  todo.onclick = () => responder(true, true, "✓ permitido todo — el resto sigue en automático");
  const denegar = crear("button", "boton-peligro", "Denegar");
  denegar.onclick = () => responder(false, false, "✗ denegado — esa búsqueda se omite");

  botones.append(permitir, todo, denegar);
  tarjeta.appendChild(botones);
  t.contenedor.appendChild(tarjeta);
  bajarConversacion();
}

// ---------------------------------------------------------------- memoria ----

function mostrarMemoria(previas) {
  const t = estado.turno;
  if (!t || !previas?.length) return;
  const ultima = previas[0];
  const v = VEREDICTOS[ultima.veredicto] || { titulo: ultima.veredicto };
  const chip = crear(
    "div", "chip-memoria",
    `🧠 ya verificada el ${fechaCorta(ultima.fecha)}: ${v.titulo.toLowerCase()} ` +
    `(confianza ${Math.round(ultima.confianza * 100)}%) — se vuelve a verificar igualmente`
  );
  t.contenedor.insertBefore(chip, t.registro);
  bajarConversacion();
}

// ---------------------------------------------------------------- informe ----

function mostrarInforme(informe) {
  const t = estado.turno;
  if (!t) return;
  const contenedor = t.contenedor;
  terminarTurno();

  const v = VEREDICTOS[informe.veredicto] || VEREDICTOS.evidencia_insuficiente;
  const tarjeta = crear("div", `tarjeta-veredicto ${v.clase}`);

  const titulo = crear("div", "veredicto-titulo");
  titulo.appendChild(crear("span", "icono", v.icono));
  titulo.appendChild(crear("span", null, v.titulo.toUpperCase()));
  tarjeta.appendChild(titulo);

  const barra = crear("div", "barra-confianza");
  const relleno = crear("div");
  relleno.style.width = `${Math.round(informe.confianza * 100)}%`;
  barra.appendChild(relleno);
  tarjeta.appendChild(barra);
  tarjeta.appendChild(crear("div", "confianza-texto", `confianza ${Math.round(informe.confianza * 100)}%`));

  for (const hecho of informe.hechos || []) tarjeta.appendChild(renderHecho(hecho));

  contenedor.appendChild(tarjeta);
  bajarConversacion();
  cargarHistorial(); // refresca el panel con la verificación recién guardada
}

function renderHecho(vh) {
  const nodo = crear("div", "hecho");
  nodo.appendChild(crear("div", "hecho-texto", vh.hecho.texto));

  const v = VEREDICTOS[vh.veredicto] || VEREDICTOS.evidencia_insuficiente;
  const linea = crear("div", `hecho-veredicto ${v.clase}`);
  linea.appendChild(crear("span", "veredicto-titulo", `${v.icono} ${v.titulo}`));
  linea.appendChild(crear("span", "confianza-texto", ` · confianza ${Math.round(vh.confianza * 100)}%`));
  nodo.appendChild(linea);

  const evidencias = [
    ...(vh.a_favor || []).map((p) => ({ p, lado: "a-favor", etiqueta: "A favor" })),
    ...(vh.en_contra || []).map((p) => ({ p, lado: "en-contra", etiqueta: "En contra" })),
  ];

  if (!evidencias.length) {
    nodo.appendChild(crear("div", "sin-evidencia", "Sin evidencia concluyente en las fuentes consultadas."));
    return nodo;
  }

  const lista = crear("ul", "evidencias");
  const visibles = evidencias.slice(0, 3);
  const resto = evidencias.slice(3);
  for (const e of visibles) lista.appendChild(renderEvidencia(e));
  nodo.appendChild(lista);

  if (resto.length) {
    const mas = document.createElement("details");
    const resumen = crear("summary", "confianza-texto", `ver ${resto.length} evidencia(s) más`);
    resumen.style.cursor = "pointer";
    mas.appendChild(resumen);
    const listaResto = crear("ul", "evidencias");
    for (const e of resto) listaResto.appendChild(renderEvidencia(e));
    mas.appendChild(listaResto);
    nodo.appendChild(mas);
  }
  return nodo;
}

function renderEvidencia({ p, lado, etiqueta }) {
  const item = crear("li", "evidencia");
  const meta = crear("div", "evidencia-meta");
  meta.appendChild(crear("span", `evidencia-etiqueta ${lado}`, `${etiqueta} ${Math.round(p.prob * 100)}%`));
  meta.appendChild(crear("span", null, p.evidencia.dominio));
  if (p.evidencia.idioma) meta.appendChild(crear("span", null, p.evidencia.idioma));
  item.appendChild(meta);

  const texto = p.evidencia.texto.length > 280
    ? p.evidencia.texto.slice(0, 280) + "…"
    : p.evidencia.texto;
  item.appendChild(crear("div", "evidencia-texto", `«${texto}»`));

  if (p.evidencia.url) {
    const enlace = crear("a", null, p.evidencia.titulo || p.evidencia.url);
    enlace.href = p.evidencia.url;
    enlace.target = "_blank";
    enlace.rel = "noopener noreferrer";
    item.appendChild(enlace);
  }
  return item;
}

function mostrarCancelado() {
  const t = estado.turno;
  const contenedor = t?.contenedor;
  terminarTurno();
  contenedor?.appendChild(crear("div", "nota-cancelado", "Verificación cancelada."));
}

function mostrarError(mensaje) {
  const t = estado.turno;
  if (t) {
    const contenedor = t.contenedor;
    terminarTurno();
    contenedor.appendChild(crear("div", "nota-error", mensaje));
    bajarConversacion();
  } else {
    avisar(mensaje, true);
  }
}

// ------------------------------------------------------------------- voz ----

const IDIOMAS_NAVEGADOR = { es: "es-ES", en: "en-US", fr: "fr-FR", de: "de-DE", pt: "pt-BR", it: "it-IT" };

async function alternarVoz() {
  if (estado.grabadora) return detenerGrabacion();
  if (estado.reconocedor) { estado.reconocedor.stop(); return; }

  if (estado.capacidades.voz) return iniciarGrabacionLocal();

  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Reconocimiento) return iniciarReconocimientoNavegador(Reconocimiento);

  avisar("Sin reconocimiento de voz: instala «uv pip install -e '.[voz]'» para " +
         "transcripción local privada, o usa un navegador compatible.", true);
}

async function iniciarGrabacionLocal() {
  let flujo;
  try {
    flujo = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    avisar("No se pudo acceder al micrófono.", true);
    return;
  }
  const tipo = ["audio/webm", "audio/mp4", "audio/ogg"].find((t) => MediaRecorder.isTypeSupported(t)) || "";
  const grabadora = new MediaRecorder(flujo, tipo ? { mimeType: tipo } : undefined);
  const trozos = [];
  grabadora.ondataavailable = (e) => e.data.size && trozos.push(e.data);
  grabadora.onstop = async () => {
    flujo.getTracks().forEach((pista) => pista.stop());
    ui.voz.classList.remove("grabando");
    estado.grabadora = null;
    const audio = new Blob(trozos, { type: tipo || "audio/webm" });
    if (!audio.size) return;
    mostrarAdjunto("🎤 transcribiendo localmente…");
    try {
      const datos = new FormData();
      datos.append("archivo", audio, "dictado.webm");
      const respuesta = await fetch(`/api/voz?lang=${encodeURIComponent(ui.idioma.value)}`, {
        method: "POST", body: datos,
      });
      const cuerpo = await respuesta.json();
      if (!respuesta.ok) throw new Error(cuerpo.error || respuesta.statusText);
      insertarTexto(cuerpo.texto);
      mostrarAdjunto(cuerpo.texto ? "🎤 dictado transcrito" : "🎤 no se reconoció voz en el audio");
    } catch (err) {
      mostrarAdjunto("");
      avisar(`Transcripción fallida: ${err.message}`, true);
    }
  };
  grabadora.start();
  estado.grabadora = grabadora;
  ui.voz.classList.add("grabando");
  ui.voz.title = "Detener el dictado";
}

function detenerGrabacion() {
  estado.grabadora?.stop();
  ui.voz.title = "Dictar la afirmación";
}

function iniciarReconocimientoNavegador(Reconocimiento) {
  const rec = new Reconocimiento();
  rec.lang = IDIOMAS_NAVEGADOR[ui.idioma.value] || ui.idioma.value;
  rec.interimResults = false;
  rec.continuous = false;
  rec.onresult = (e) => insertarTexto(Array.from(e.results).map((r) => r[0].transcript).join(" "));
  rec.onerror = (e) => { if (e.error !== "aborted") avisar(`Reconocimiento de voz: ${e.error}`, true); };
  rec.onend = () => {
    ui.voz.classList.remove("grabando");
    estado.reconocedor = null;
  };
  rec.start();
  estado.reconocedor = rec;
  ui.voz.classList.add("grabando");
}

// ---------------------------------------------------------------- imágenes ----

async function procesarImagen(archivo) {
  if (!archivo) return;
  if (!estado.capacidades.imagen) {
    avisar("Reconocimiento de imágenes no instalado en el servidor: " +
           "«uv pip install -e '.[imagen]'» y reinicia «aidam interfaz».", true);
    return;
  }
  mostrarAdjunto(`🖼 extrayendo texto de ${archivo.name || "la imagen"}…`);
  try {
    const datos = new FormData();
    datos.append("archivo", archivo, archivo.name || "imagen.png");
    const respuesta = await fetch("/api/imagen", { method: "POST", body: datos });
    const cuerpo = await respuesta.json();
    if (!respuesta.ok) throw new Error(cuerpo.error || respuesta.statusText);
    if (cuerpo.texto) {
      insertarTexto(cuerpo.texto);
      mostrarAdjunto(`🖼 texto extraído de ${archivo.name || "la imagen"} — revísalo antes de verificar`);
    } else {
      mostrarAdjunto("🖼 la imagen no contiene texto legible");
    }
  } catch (err) {
    mostrarAdjunto("");
    avisar(`OCR fallido: ${err.message}`, true);
  }
}

function mostrarAdjunto(mensaje) {
  ui.avisoAdjunto.textContent = mensaje;
  ui.avisoAdjunto.classList.toggle("oculto", !mensaje);
}

function insertarTexto(texto) {
  if (!texto) return;
  const actual = ui.entrada.value.trim();
  ui.entrada.value = actual ? `${actual} ${texto}` : texto;
  ajustarAltura();
  ui.entrada.focus();
}

// --------------------------------------------------------------- historial ----

async function cargarHistorial() {
  try {
    const respuesta = await fetch("/api/historial?limite=30");
    const { historial } = await respuesta.json();
    ui.listaHistorial.replaceChildren();
    if (!historial.length) {
      ui.listaHistorial.appendChild(crear("li", "historial-vacio", "Sin verificaciones guardadas todavía."));
      return;
    }
    for (const fila of historial) {
      const item = crear("li");
      const v = VEREDICTOS[fila.veredicto] || { icono: "?", titulo: fila.veredicto, clase: "insuficiente" };
      item.appendChild(crear("span", "historial-afirmacion", `${v.icono} ${fila.afirmacion}`));
      item.appendChild(crear("span", "historial-meta",
        `${v.titulo.toLowerCase()} · ${Math.round(fila.confianza * 100)}% · ${fechaCorta(fila.fecha)}`));
      item.title = "Copiar al cuadro de entrada";
      item.onclick = () => {
        ui.entrada.value = fila.afirmacion;
        ajustarAltura();
        ui.panelHistorial.classList.add("oculto");
        ui.entrada.focus();
      };
      ui.listaHistorial.appendChild(item);
    }
  } catch {
    /* la memoria es opcional: sin ella el panel simplemente queda vacío */
  }
}

ui.botonHistorial.addEventListener("click", () => {
  ui.panelHistorial.classList.toggle("oculto");
  if (!ui.panelHistorial.classList.contains("oculto")) cargarHistorial();
});
ui.cerrarHistorial.addEventListener("click", () => ui.panelHistorial.classList.add("oculto"));

// ---------------------------------------------------------------- entrada ----

function ajustarAltura() {
  ui.entrada.style.height = "auto";
  ui.entrada.style.height = `${Math.min(ui.entrada.scrollHeight, 160)}px`;
}

ui.entrada.addEventListener("input", ajustarAltura);

ui.entrada.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!estado.enCurso) enviarVerificacion();
  }
});

ui.entrada.addEventListener("paste", (e) => {
  const imagen = Array.from(e.clipboardData?.items || []).find((i) => i.type.startsWith("image/"));
  if (imagen) {
    e.preventDefault();
    procesarImagen(imagen.getAsFile());
  }
});

document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  const archivo = e.dataTransfer?.files?.[0];
  if (archivo?.type.startsWith("image/")) procesarImagen(archivo);
});

ui.enviar.addEventListener("click", () => {
  if (estado.enCurso) cancelarVerificacion();
  else enviarVerificacion();
});

ui.voz.addEventListener("click", alternarVoz);
ui.imagen.addEventListener("click", () => ui.selectorImagen.click());
ui.selectorImagen.addEventListener("change", () => {
  procesarImagen(ui.selectorImagen.files?.[0]);
  ui.selectorImagen.value = "";
});

document.querySelectorAll(".ejemplo").forEach((boton) => {
  boton.addEventListener("click", () => {
    ui.entrada.value = boton.textContent;
    ajustarAltura();
    ui.entrada.focus();
  });
});

// ------------------------------------------------------------------ inicio ----

async function iniciar() {
  cargarPreferencias();
  conectar();
  cargarHistorial();
  try {
    const respuesta = await fetch("/api/capacidades");
    estado.capacidades = await respuesta.json();
  } catch {
    /* sin capacidades opcionales; los botones lo explican al usarse */
  }
  ui.entrada.focus();
}

iniciar();

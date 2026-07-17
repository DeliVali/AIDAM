/* AIDAM — lógica de la interfaz. Vanilla JS, sin dependencias.
 *
 * Protocolo WebSocket documentado en aidam/servidor.py y docs/INTERFAZ.md.
 * Layout tipo chat: barra lateral con historial reabrible + nueva
 * verificación; entrada con documentos (imagen OCR, PDF, texto) y modo de
 * ejecución del agente. Sin voz por diseño.
 */

"use strict";

// ---------------------------------------------------------------- estado ----

const $ = (id) => document.getElementById(id);

const ui = {
  conversacion: $("conversacion"),
  plantillaBienvenida: $("plantilla-bienvenida"),
  entrada: $("entrada"),
  enviar: $("boton-enviar"),
  adjuntar: $("boton-adjuntar"),
  menuAdjuntar: $("menu-adjuntar"),
  selectorArchivo: $("selector-archivo"),
  avisoAdjunto: $("aviso-adjunto"),
  modo: $("modo"),
  idioma: $("idioma"),
  memoria: $("opcion-memoria"),
  estadoConexion: $("estado-conexion"),
  estadoTexto: $("estado-texto"),
  avisos: $("avisos"),
  nuevaVerificacion: $("nueva-verificacion"),
  listaHistorial: $("lista-historial"),
  acercaVersion: $("acerca-version"),
};

const estado = {
  ws: null,
  conectado: false,
  intentoReconexion: 0,
  enCurso: false,     // hay una verificación corriendo
  turno: null,        // elementos DOM del turno activo
  capacidades: { imagen: false, pdf: false },
  tipoAdjunto: null,  // "imagen" | "pdf" | "texto" elegido en el menú
};

const VEREDICTOS = {
  sustentado: { clase: "sustentado", icono: "✓", titulo: "Sustentado" },
  refutado: { clase: "refutado", icono: "✗", titulo: "Refutado" },
  evidencia_contradictoria: { clase: "contradictorio", icono: "⚡", titulo: "Evidencia contradictoria" },
  evidencia_insuficiente: { clase: "insuficiente", icono: "?", titulo: "Evidencia insuficiente" },
};

const MAX_TEXTO_DOCUMENTO = 4000; // lo que se vuelca al cuadro de entrada

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

function tituloVeredicto(v) {
  const titulo = crear("div", "veredicto-titulo");
  titulo.appendChild(crear("span", "punto-veredicto"));
  titulo.appendChild(crear("span", null, v.titulo.toUpperCase()));
  return titulo;
}

// ---------------------------------------------------------- preferencias ----

function cargarPreferencias() {
  let prefs = {};
  try { prefs = JSON.parse(localStorage.getItem("aidam.prefs") || "{}"); } catch {}
  if (prefs.modo === "permisos") ui.modo.value = "permisos";
  if (prefs.idioma) ui.idioma.value = prefs.idioma;
  ui.memoria.checked = prefs.memoria !== false;
}

function guardarPreferencias() {
  localStorage.setItem("aidam.prefs", JSON.stringify({
    modo: ui.modo.value,
    idioma: ui.idioma.value,
    memoria: ui.memoria.checked,
  }));
}

ui.modo.addEventListener("change", guardarPreferencias);
ui.idioma.addEventListener("change", guardarPreferencias);
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

// ---------------------------------------------------------- conversaciones ----

function nuevaConversacion() {
  if (estado.enCurso) cancelarVerificacion();
  estado.turno = null;
  ui.conversacion.replaceChildren(ui.plantillaBienvenida.content.cloneNode(true));
  conectarEjemplos();
  marcarHistorialActivo(null);
  ui.entrada.value = "";
  ajustarAltura();
  ui.entrada.focus();
}

function quitarBienvenida() {
  ui.conversacion.querySelector(".bienvenida")?.remove();
}

async function abrirVerificacion(id) {
  if (estado.enCurso) {
    avisar("Espera a que termine la verificación en curso (o cancélala).");
    return;
  }
  try {
    const respuesta = await fetch(`/api/verificacion/${id}`);
    const guardada = await respuesta.json();
    if (!respuesta.ok) throw new Error(guardada.error || respuesta.statusText);

    ui.conversacion.replaceChildren();
    const turno = crear("div", "turno");
    turno.appendChild(crear("span", "chip-fecha", `verificada el ${fechaCorta(guardada.fecha)}`));
    turno.appendChild(crear("div", "burbuja-usuario", guardada.afirmacion));
    turno.appendChild(renderInforme(guardada.informe));
    ui.conversacion.appendChild(turno);
    marcarHistorialActivo(id);
    bajarConversacion();
  } catch (err) {
    avisar(`No se pudo abrir la verificación: ${err.message}`, true);
  }
}

function marcarHistorialActivo(id) {
  ui.listaHistorial.querySelectorAll("li").forEach((li) => {
    li.classList.toggle("activa", id !== null && li.dataset.id === String(id));
  });
}

// ------------------------------------------------------- envío y progreso ----

function enviarVerificacion() {
  const afirmacion = ui.entrada.value.trim();
  if (!afirmacion || !estado.conectado) return;
  if (estado.enCurso) return;

  // Nota: no se envía "preguntas": la búsqueda guiada por LLM es una
  // capacidad del agente — el servidor la activa si el modelo local existe.
  estado.ws.send(JSON.stringify({
    tipo: "verificar",
    afirmacion,
    lang: ui.idioma.value,
    memoria: ui.memoria.checked,
    modo: ui.modo.value,
  }));

  quitarBienvenida();
  marcarHistorialActivo(null);
  mostrarAdjunto("");

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
    `🕊 ya verificada el ${fechaCorta(ultima.fecha)}: ${v.titulo.toLowerCase()} ` +
    `(confianza ${Math.round(ultima.confianza * 100)}%) — se vuelve a verificar igualmente`
  );
  t.contenedor.insertBefore(chip, t.registro);
  bajarConversacion();
}

// ---------------------------------------------------------------- informe ----

function renderInforme(informe) {
  // Una pregunta no se "refuta": el modo respuesta muestra el texto con sus
  // citas y NUNCA una etiqueta de veredicto (fallo medido 2026-07-16).
  if (informe.tipo === "pregunta") {
    const tarjeta = crear("div", "tarjeta-veredicto veredicto-respuesta");
    tarjeta.appendChild(tituloVeredicto({ titulo: "Respuesta" }));
    tarjeta.appendChild(crear("div", "respuesta-texto", informe.respuesta || ""));
    for (const hecho of informe.hechos || []) {
      tarjeta.appendChild(renderHecho(hecho, { sinVeredicto: true }));
    }
    return tarjeta;
  }

  const v = VEREDICTOS[informe.veredicto] || VEREDICTOS.evidencia_insuficiente;
  const tarjeta = crear("div", `tarjeta-veredicto ${v.clase}`);
  tarjeta.appendChild(tituloVeredicto(v));

  const barra = crear("div", "barra-confianza");
  const relleno = crear("div");
  relleno.style.width = `${Math.round(informe.confianza * 100)}%`;
  barra.appendChild(relleno);
  tarjeta.appendChild(barra);
  tarjeta.appendChild(crear("div", "confianza-texto", `CONFIANZA ${Math.round(informe.confianza * 100)}%`));

  if (informe.respuesta) {
    tarjeta.appendChild(crear("div", "respuesta-texto", informe.respuesta));
  }

  for (const hecho of informe.hechos || []) tarjeta.appendChild(renderHecho(hecho));
  return tarjeta;
}

function mostrarInforme(informe) {
  const t = estado.turno;
  if (!t) return;
  const contenedor = t.contenedor;
  terminarTurno();
  contenedor.appendChild(renderInforme(informe));
  bajarConversacion();
  cargarHistorial(); // la barra lateral recoge la verificación recién guardada
}

function renderHecho(vh, opciones = {}) {
  const nodo = crear("div", "hecho");
  nodo.appendChild(crear("div", "hecho-texto", vh.hecho.texto));

  if (!opciones.sinVeredicto) {
    const v = VEREDICTOS[vh.veredicto] || VEREDICTOS.evidencia_insuficiente;
    const linea = crear("div", `hecho-veredicto ${v.clase}`);
    linea.appendChild(tituloVeredicto(v));
    linea.appendChild(crear("span", "confianza-texto", `· ${Math.round(vh.confianza * 100)}%`));
    nodo.appendChild(linea);
  }

  const evidencias = [
    ...(vh.a_favor || []).map((p) => ({ p, lado: "a-favor", etiqueta: "A favor" })),
    ...(vh.en_contra || []).map((p) => ({ p, lado: "en-contra", etiqueta: "En contra" })),
  ];

  if (!evidencias.length) {
    nodo.appendChild(crear("div", "sin-evidencia", "Sin evidencia concluyente en las fuentes consultadas."));
    return nodo;
  }

  // Las citas van plegadas por defecto en un desplegable.
  const aFavor = (vh.a_favor || []).length;
  const enContra = (vh.en_contra || []).length;
  const partes = [];
  if (aFavor) partes.push(`${aFavor} a favor`);
  if (enContra) partes.push(`${enContra} en contra`);

  const citas = document.createElement("details");
  citas.className = "citas";
  citas.appendChild(crear(
    "summary", null,
    `${evidencias.length} cita${evidencias.length === 1 ? "" : "s"} · ${partes.join(" · ")}`
  ));
  const lista = crear("ul", "evidencias");
  for (const e of evidencias) lista.appendChild(renderEvidencia(e));
  citas.appendChild(lista);
  nodo.appendChild(citas);
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

// -------------------------------------------------------------- documentos ----

function alternarMenuAdjuntar() {
  ui.menuAdjuntar.classList.toggle("oculto");
}

function elegirTipoAdjunto(boton) {
  const tipo = boton.dataset.tipo;
  if (tipo === "imagen" && !estado.capacidades.imagen) {
    avisar("OCR de imágenes no instalado en el servidor: " +
           "«uv pip install -e '.[imagen]'» y reinicia AIDAM.", true);
    return;
  }
  if (tipo === "pdf" && !estado.capacidades.pdf) {
    avisar("Lectura de PDF no instalada: «uv pip install -e '.[interfaz]'» " +
           "y reinicia AIDAM.", true);
    return;
  }
  estado.tipoAdjunto = tipo;
  ui.selectorArchivo.accept = boton.dataset.accept;
  ui.menuAdjuntar.classList.add("oculto");
  ui.selectorArchivo.click();
}

async function procesarArchivo(archivo, tipo) {
  if (!archivo) return;
  tipo = tipo || estado.tipoAdjunto || (archivo.type.startsWith("image/") ? "imagen" : "texto");
  const esImagen = tipo === "imagen";
  const url = esImagen ? "/api/imagen" : "/api/documento";
  const nombre = archivo.name || (esImagen ? "imagen.png" : "documento");

  mostrarAdjunto(`${esImagen ? "🖼" : "📄"} extrayendo texto de ${nombre}…`);
  try {
    const datos = new FormData();
    datos.append("archivo", archivo, nombre);
    const respuesta = await fetch(url, { method: "POST", body: datos });
    const cuerpo = await respuesta.json();
    if (!respuesta.ok) throw new Error(cuerpo.error || respuesta.statusText);
    if (!cuerpo.texto) {
      mostrarAdjunto(`${esImagen ? "🖼" : "📄"} ${nombre} no contiene texto legible`);
      return;
    }
    let texto = cuerpo.texto;
    let recorte = "";
    if (texto.length > MAX_TEXTO_DOCUMENTO) {
      texto = texto.slice(0, MAX_TEXTO_DOCUMENTO);
      recorte = ` (recortado a ${MAX_TEXTO_DOCUMENTO} caracteres)`;
    }
    insertarTexto(texto);
    mostrarAdjunto(`${esImagen ? "🖼" : "📄"} texto extraído de ${nombre}${recorte} — revísalo antes de verificar`);
  } catch (err) {
    mostrarAdjunto("");
    avisar(`No se pudo leer ${nombre}: ${err.message}`, true);
  } finally {
    estado.tipoAdjunto = null;
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
    const respuesta = await fetch("/api/historial?limite=40");
    const { historial } = await respuesta.json();
    ui.listaHistorial.replaceChildren();
    if (!historial.length) {
      ui.listaHistorial.appendChild(crear("li", "historial-vacio", "Sin verificaciones todavía."));
      return;
    }
    for (const fila of historial) {
      const item = crear("li");
      item.dataset.id = String(fila.id ?? "");
      const v = VEREDICTOS[fila.veredicto] || { icono: "?", titulo: fila.veredicto };
      item.appendChild(crear("span", "historial-afirmacion", `${v.icono} ${fila.afirmacion}`));
      item.appendChild(crear("span", "historial-meta",
        `${v.titulo.toLowerCase()} · ${Math.round(fila.confianza * 100)}% · ${fechaCorta(fila.fecha)}`));
      item.title = "Reabrir esta verificación";
      item.onclick = () => abrirVerificacion(fila.id);
      ui.listaHistorial.appendChild(item);
    }
  } catch {
    /* la memoria es opcional: sin ella la lista simplemente queda vacía */
  }
}

// ---------------------------------------------------------------- entrada ----

function ajustarAltura() {
  ui.entrada.style.height = "auto";
  ui.entrada.style.height = `${Math.min(ui.entrada.scrollHeight, 160)}px`;
}

function conectarEjemplos() {
  ui.conversacion.querySelectorAll(".ejemplo").forEach((boton) => {
    boton.addEventListener("click", () => {
      ui.entrada.value = boton.textContent;
      ajustarAltura();
      ui.entrada.focus();
    });
  });
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
    procesarArchivo(imagen.getAsFile(), "imagen");
  }
});

document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  const archivo = e.dataTransfer?.files?.[0];
  if (!archivo) return;
  if (archivo.type.startsWith("image/")) procesarArchivo(archivo, "imagen");
  else if (archivo.name?.toLowerCase().endsWith(".pdf")) procesarArchivo(archivo, "pdf");
  else procesarArchivo(archivo, "texto");
});

ui.enviar.addEventListener("click", () => {
  if (estado.enCurso) cancelarVerificacion();
  else enviarVerificacion();
});

ui.adjuntar.addEventListener("click", (e) => {
  e.stopPropagation();
  alternarMenuAdjuntar();
});

ui.menuAdjuntar.querySelectorAll(".menu-opcion").forEach((boton) => {
  boton.addEventListener("click", () => elegirTipoAdjunto(boton));
});

document.addEventListener("click", (e) => {
  if (!ui.menuAdjuntar.classList.contains("oculto") && !ui.menuAdjuntar.contains(e.target)) {
    ui.menuAdjuntar.classList.add("oculto");
  }
});

ui.selectorArchivo.addEventListener("change", () => {
  procesarArchivo(ui.selectorArchivo.files?.[0]);
  ui.selectorArchivo.value = "";
});

ui.nuevaVerificacion.addEventListener("click", nuevaConversacion);

// ------------------------------------------------------------------ inicio ----

async function iniciar() {
  cargarPreferencias();
  ui.conversacion.appendChild(ui.plantillaBienvenida.content.cloneNode(true));
  conectarEjemplos();
  conectar();
  cargarHistorial();
  try {
    const respuesta = await fetch("/api/capacidades");
    estado.capacidades = await respuesta.json();
    ui.acercaVersion.textContent = estado.capacidades.version || "—";
  } catch {
    /* sin capacidades opcionales; los botones lo explican al usarse */
  }
  ui.entrada.focus();
}

iniciar();

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
  listaEspacios: $("lista-espacios"),
  anadirCarpeta: $("boton-anadir-carpeta"),
  listaConversaciones: $("lista-conversaciones"),
  acercaVersion: $("acerca-version"),
};

const estado = {
  ws: null,
  conectado: false,
  intentoReconexion: 0,
  enCurso: false,     // hay una verificación corriendo
  turno: null,        // elementos DOM del turno activo
  capacidades: { imagen: false, pdf: false },
  tipoAdjunto: null,   // "imagen" | "pdf" | "texto" elegido en el menú
  carpetas: [],        // espacios añadidos por el usuario (rutas absolutas)
  espacio: null,       // espacio activo: null = General, o una ruta de carpetas
  conversacion: null,  // id de la conversación activa (null = aún sin crear)
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
  estado.carpetas = Array.isArray(prefs.carpetas) ? prefs.carpetas : [];
  if (prefs.carpeta && !estado.carpetas.includes(prefs.carpeta)) {
    estado.carpetas.push(prefs.carpeta); // migración: carpeta única → lista
  }
  estado.espacio = estado.carpetas.includes(prefs.espacio) ? prefs.espacio : null;
}

function guardarPreferencias() {
  localStorage.setItem("aidam.prefs", JSON.stringify({
    modo: ui.modo.value,
    idioma: ui.idioma.value,
    memoria: ui.memoria.checked,
    carpetas: estado.carpetas,
    espacio: estado.espacio,
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
    ui.estadoTexto.textContent = "Conectado";
    // Los fetch de arranque pueden perder la carrera contra un servidor que
    // aún despierta; el WS sí reintenta, así que al conectar se recargan.
    cargarConversaciones();
    if (ui.acercaVersion.textContent === "—") cargarCapacidades();
  };

  ws.onmessage = (evento) => {
    let mensaje;
    try { mensaje = JSON.parse(evento.data); } catch { return; }
    manejarMensaje(mensaje);
  };

  ws.onclose = () => {
    estado.conectado = false;
    ui.estadoConexion.className = "estado-conexion desconectado";
    ui.estadoTexto.textContent = "Desconectado";
    if (estado.enCurso) terminarTurno();
    const espera = Math.min(10000, 500 * 2 ** estado.intentoReconexion++);
    setTimeout(conectar, espera);
  };
}

function manejarMensaje(m) {
  switch (m.tipo) {
    case "progreso": return anotarProgreso(m.mensaje);
    case "conversacion": return engancharConversacion(m.id);
    case "permiso": return pedirPermiso(m);
    case "memoria": return mostrarMemoria(m.previas);
    case "informe": return mostrarInforme(m.informe);
    case "cancelado": return mostrarCancelado();
    case "error": return mostrarError(m.mensaje);
  }
}

function engancharConversacion(id) {
  // El servidor creó el hilo para este turno: los siguientes siguen en él.
  estado.conversacion = id;
}

// ------------------------------------------------------ espacios de trabajo ----

function nombreDeCarpeta(ruta) {
  return ruta.replace(/[/\\]+$/, "").split(/[/\\]/).pop() || ruta;
}

function renderEspacios() {
  ui.listaEspacios.replaceChildren();

  const general = crear("li");
  general.appendChild(crear("span", null, "🏠"));
  general.appendChild(crear("span", "espacio-nombre", "General"));
  general.title = "Espacio general: siempre disponible, sin carpeta que elegir";
  general.classList.toggle("activa", estado.espacio === null);
  general.onclick = () => seleccionarEspacio(null);
  ui.listaEspacios.appendChild(general);

  for (const ruta of estado.carpetas) {
    const item = crear("li");
    item.appendChild(crear("span", null, "📁"));
    item.appendChild(crear("span", "espacio-nombre", nombreDeCarpeta(ruta)));
    item.title = ruta;
    item.classList.toggle("activa", estado.espacio === ruta);
    item.onclick = () => seleccionarEspacio(ruta);
    const quitar = crear("span", "espacio-quitar", "✕");
    quitar.title = "Quitar este espacio de la lista (sus conversaciones no se borran)";
    quitar.onclick = (e) => {
      e.stopPropagation();
      estado.carpetas = estado.carpetas.filter((c) => c !== ruta);
      if (estado.espacio === ruta) seleccionarEspacio(null);
      else { guardarPreferencias(); renderEspacios(); }
    };
    item.appendChild(quitar);
    ui.listaEspacios.appendChild(item);
  }
}

function seleccionarEspacio(ruta) {
  estado.espacio = ruta;
  guardarPreferencias();
  renderEspacios();
  cargarConversaciones();
  nuevaConversacion();
}

async function anadirCarpeta() {
  let ruta = null;
  if (window.aidamEscritorio?.elegirCarpeta) {
    ruta = await window.aidamEscritorio.elegirCarpeta(); // diálogo nativo (app de escritorio)
  } else {
    // En navegador no hay diálogo con ruta real: entrada manual honesta.
    ruta = prompt("Ruta de la carpeta a añadir como espacio de trabajo:", "~/");
  }
  if (!ruta) return;
  ruta = ruta.trim();
  if (!estado.carpetas.includes(ruta)) estado.carpetas.push(ruta);
  seleccionarEspacio(ruta);
}

ui.anadirCarpeta.addEventListener("click", anadirCarpeta);

// ---------------------------------------------------------- conversaciones ----

function nuevaConversacion() {
  if (estado.enCurso) cancelarVerificacion();
  estado.turno = null;
  estado.conversacion = null; // el siguiente mensaje abre conversación nueva
  ui.conversacion.replaceChildren(ui.plantillaBienvenida.content.cloneNode(true));
  conectarEjemplos();
  marcarConversacionActiva(null);
  ui.entrada.value = "";
  ajustarAltura();
  ui.entrada.focus();
}

function quitarBienvenida() {
  ui.conversacion.querySelector(".bienvenida")?.remove();
}

async function abrirConversacion(id) {
  if (estado.enCurso) {
    avisar("Espera a que termine la verificación en curso (o cancélala).");
    return;
  }
  try {
    const respuesta = await fetch(`/api/conversacion/${id}`);
    const guardada = await respuesta.json();
    if (!respuesta.ok) throw new Error(guardada.error || respuesta.statusText);

    ui.conversacion.replaceChildren();
    for (const turno of guardada.turnos) {
      const nodo = crear("div", "turno");
      nodo.appendChild(crear("span", "chip-fecha", fechaCorta(turno.fecha)));
      nodo.appendChild(crear("div", "burbuja-usuario", turno.afirmacion));
      nodo.appendChild(renderInforme(turno.informe));
      ui.conversacion.appendChild(nodo);
    }
    estado.conversacion = id; // seguir escribiendo continúa este hilo
    marcarConversacionActiva(id);
    bajarConversacion();
    ui.entrada.focus();
  } catch (err) {
    avisar(`No se pudo abrir la conversación: ${err.message}`, true);
  }
}

function marcarConversacionActiva(id) {
  ui.listaConversaciones.querySelectorAll("li").forEach((li) => {
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
    carpeta: estado.espacio || undefined,          // ausente = espacio General
    conversacion: estado.conversacion ?? undefined, // ausente = hilo nuevo
  }));

  quitarBienvenida();
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
  const resumen = crear("summary", null, `Ver el proceso (${t.pasos} pasos)`);
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
  permitir.onclick = () => responder(true, false, "✓ Permitido");
  const todo = crear("button", "boton-secundario", "Permitir todo");
  todo.title = "Aprueba esta acción y el resto de la verificación sigue en automático";
  todo.onclick = () => responder(true, true, "✓ Permitido todo — el resto sigue en automático");
  const denegar = crear("button", "boton-peligro", "Denegar");
  denegar.onclick = () => responder(false, false, "✗ Denegado — esa búsqueda se omite");

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
    `🕊 Ya verificada el ${fechaCorta(ultima.fecha)}: ${v.titulo.toLowerCase()} ` +
    `(confianza ${Math.round(ultima.confianza * 100)}%) — se vuelve a verificar igualmente`
  );
  t.contenedor.insertBefore(chip, t.registro);
  bajarConversacion();
}

// ---------------------------------------------------------------- informe ----


// Respuestas con código: los tramos entre ``` se vuelven bloques <pre>
// copiables con un clic (pedido de producto 2026-07-16).
function renderRespuesta(texto) {
  const cont = crear("div", "respuesta-texto");
  const partes = String(texto || "").split(/```(?:[a-z]*\n)?/);
  partes.forEach((parte, i) => {
    if (!parte.trim()) return;
    if (i % 2 === 1) {
      const caja = crear("div", "bloque-codigo");
      const pre = document.createElement("pre");
      pre.textContent = parte.replace(/\n$/, "");
      const boton = crear("button", "boton-copiar", "copiar");
      boton.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(pre.textContent);
          boton.textContent = "copiado ✓";
          setTimeout(() => (boton.textContent = "copiar"), 1500);
        } catch { boton.textContent = "error"; }
      });
      caja.appendChild(boton);
      caja.appendChild(pre);
      cont.appendChild(caja);
    } else {
      cont.appendChild(crear("div", null, parte.trim()));
    }
  });
  return cont;
}

function renderInforme(informe) {
  // Una pregunta no se "refuta": el modo respuesta muestra el texto con sus
  // citas y NUNCA una etiqueta de veredicto (fallo medido 2026-07-16).
  if (informe.tipo === "pregunta" || informe.tipo === "aclaracion") {
    const tarjeta = crear("div", "tarjeta-veredicto veredicto-respuesta");
    tarjeta.appendChild(tituloVeredicto({ titulo: informe.tipo === "aclaracion" ? "Necesito una aclaración" : "Respuesta" }));
    tarjeta.appendChild(renderRespuesta(informe.respuesta || ""));
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
    tarjeta.appendChild(renderRespuesta(informe.respuesta));
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
  cargarConversaciones(); // la barra lateral recoge el turno recién guardado
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

  mostrarAdjunto(`${esImagen ? "🖼" : "📄"} Extrayendo texto de ${nombre}…`);
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
    mostrarAdjunto(`${esImagen ? "🖼" : "📄"} Texto extraído de ${nombre}${recorte} — revísalo antes de verificar`);
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

// ---------------------------------------------- conversaciones del espacio ----

async function cargarConversaciones() {
  try {
    const carpeta = encodeURIComponent(estado.espacio || "");
    const respuesta = await fetch(`/api/conversaciones?carpeta=${carpeta}&limite=40`);
    const { conversaciones } = await respuesta.json();
    ui.listaConversaciones.replaceChildren();
    if (!conversaciones.length) {
      ui.listaConversaciones.appendChild(
        crear("li", "historial-vacio", "Sin conversaciones todavía."));
      return;
    }
    for (const fila of conversaciones) {
      const item = crear("li");
      item.dataset.id = String(fila.id);
      item.appendChild(crear("span", "historial-afirmacion", fila.titulo || "(Sin título)"));
      const turnos = `${fila.turnos} turno${fila.turnos === 1 ? "" : "s"}`;
      item.appendChild(crear("span", "historial-meta",
        `${turnos} · ${fechaCorta(fila.ultima)}`));
      item.title = "Reabrir y continuar esta conversación";
      item.onclick = () => abrirConversacion(fila.id);
      item.classList.toggle("activa", estado.conversacion === fila.id);
      ui.listaConversaciones.appendChild(item);
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

async function cargarCapacidades() {
  try {
    const respuesta = await fetch("/api/capacidades");
    estado.capacidades = await respuesta.json();
    ui.acercaVersion.textContent = estado.capacidades.version || "—";
  } catch {
    /* sin capacidades opcionales; los botones lo explican al usarse */
  }
}

async function iniciar() {
  cargarPreferencias();
  ui.conversacion.appendChild(ui.plantillaBienvenida.content.cloneNode(true));
  conectarEjemplos();
  conectar();
  renderEspacios();
  cargarConversaciones();
  cargarCapacidades();
  ui.entrada.focus();
}

iniciar();

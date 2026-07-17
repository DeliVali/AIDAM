/* AIDAM — aplicación de escritorio (Electron).
 *
 * Ventana nativa que embebe la interfaz local. Al abrirla, levanta ella misma
 * el backend (`aidam interfaz`) en un puerto libre de localhost y lo apaga al
 * cerrar: una sola aplicación, sin navegador, estilo Ollama/Claude Desktop.
 *
 * El backend se resuelve en este orden:
 *   1. $AIDAM_BACKEND_BIN            (override explícito)
 *   2. resources/backend/aidam       (release empaquetado: binario PyInstaller)
 *   3. ../.venv/bin/aidam            (desarrollo: el venv del repositorio)
 */

"use strict";

const { app, BrowserWindow, dialog, net: electronNet } = require("electron");
const { spawn } = require("node:child_process");
const net = require("node:net");
const fs = require("node:fs");
const path = require("node:path");

let backend = null;
let cerrandoAdrede = false;

function rutaBackend() {
  if (process.env.AIDAM_BACKEND_BIN) return process.env.AIDAM_BACKEND_BIN;
  const binario = process.platform === "win32" ? "aidam.exe" : "aidam";
  const empaquetado = path.join(process.resourcesPath || "", "backend", binario);
  if (app.isPackaged && fs.existsSync(empaquetado)) return empaquetado;
  return path.join(__dirname, "..", ".venv", "bin", "aidam");
}

function puertoLibre() {
  return new Promise((resolver, rechazar) => {
    const servidor = net.createServer();
    servidor.unref();
    servidor.on("error", rechazar);
    servidor.listen(0, "127.0.0.1", () => {
      const { port } = servidor.address();
      servidor.close(() => resolver(port));
    });
  });
}

function esperar(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function esperarBackend(base, intentos = 150) {
  for (let i = 0; i < intentos; i++) {
    if (backend === null) throw new Error("el backend terminó antes de arrancar");
    try {
      const respuesta = await electronNet.fetch(`${base}/api/capacidades`);
      if (respuesta.ok) return;
    } catch {
      /* aún no escucha */
    }
    await esperar(100);
  }
  throw new Error("el backend no respondió a tiempo");
}

function lanzarBackend(puerto) {
  const bin = rutaBackend();
  backend = spawn(bin, ["interfaz", "--sin-navegador", "--puerto", String(puerto)], {
    stdio: ["ignore", "inherit", "inherit"],
  });
  backend.on("error", () => {
    backend = null;
  });
  backend.on("exit", () => {
    backend = null;
    if (!cerrandoAdrede) app.quit();
  });
  return bin;
}

async function crearVentana() {
  const puerto = await puertoLibre();
  const bin = lanzarBackend(puerto);
  const base = `http://127.0.0.1:${puerto}`;

  try {
    await esperarBackend(base);
  } catch (err) {
    dialog.showErrorBox(
      "AIDAM no pudo arrancar",
      `${err.message}\n\nBackend: ${bin}\n\n` +
        "En desarrollo, instala el backend con:\n" +
        "  uv pip install -e \".[verificador,interfaz]\"",
    );
    app.quit();
    return;
  }

  const ventana = new BrowserWindow({
    width: 1100,
    height: 780,
    minWidth: 720,
    minHeight: 520,
    backgroundColor: "#05070a",
    autoHideMenuBar: true,
    icon: path.join(__dirname, "build", "icon.png"),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  ventana.loadURL(base);
}

app.whenReady().then(crearVentana);

app.on("window-all-closed", () => app.quit());

app.on("quit", () => {
  cerrandoAdrede = true;
  if (backend) backend.kill();
});

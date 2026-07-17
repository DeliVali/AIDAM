/* AIDAM — puente seguro entre la interfaz web y el escritorio.
 *
 * Expone SOLO lo imprescindible (contextIsolation): hoy, el diálogo nativo
 * para elegir la carpeta de trabajo del agente. En navegador este objeto no
 * existe y la interfaz cae a la entrada manual de ruta.
 */

"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("aidamEscritorio", {
  elegirCarpeta: () => ipcRenderer.invoke("elegir-carpeta"),
});

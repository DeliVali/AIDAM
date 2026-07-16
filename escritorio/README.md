# AIDAM — aplicación de escritorio

Ventana nativa (Electron) que embebe la interfaz local de AIDAM. Al abrirla,
levanta ella misma el backend (`aidam interfaz`) en un puerto libre y lo apaga
al cerrar. No es una pestaña de navegador: es una app con su icono (la manzana
del logo), su entrada en el menú y su ventana propia.

## Desarrollo

```bash
# backend (una vez, desde la raíz del repo):
uv venv --python 3.12 && uv pip install -e ".[verificador,interfaz]"

# app:
cd escritorio
npm install
npm start
```

`main.js` busca el backend en este orden: `$AIDAM_BACKEND_BIN`, el binario
empaquetado en `resources/backend/aidam`, y por último `../.venv/bin/aidam`
(desarrollo).

Nota: si lanzas `npm start` desde una terminal integrada de VSCode y la ventana
no abre, ejecuta `env -u ELECTRON_RUN_AS_NODE npm start` (VSCode inyecta esa
variable y rompe Electron).

## Releases para GitHub

```bash
npm run empaquetar        # → dist/AIDAM-<versión>.AppImage y dist/*.deb
```

Esos artefactos de `dist/` son los que se suben al release de GitHub.

**Requisito para un paquete autocontenido:** antes de empaquetar, coloca en
`escritorio/backend/` un binario `aidam` del backend (PyInstaller sobre el
backend ONNX de CPU, para que no exija PyTorch ni Python instalados). Sin él,
el paquete solo funciona en máquinas con el repo y su `.venv` — útil para
probar, no para publicar. La receta del binario del backend está pendiente de
automatizar (ver docs/INTERFAZ.md).

Plataformas: `--linux` (AppImage, deb) hoy; `--win`/`--mac` cuando haya
máquinas donde compilarlos (electron-builder no cruza plataformas con
fiabilidad).

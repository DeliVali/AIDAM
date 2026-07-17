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

## Releases para GitHub (Linux + Windows + macOS)

Publicar un release es empujar un tag:

```bash
git tag v0.1.0 && git push --tags
```

`.github/workflows/release.yml` construye en las tres plataformas y sube los
instaladores al release automáticamente:

| SO | Artefacto |
|---|---|
| Linux | `AIDAM-<v>.AppImage` + `.deb` |
| Windows | instalador NSIS `.exe` |
| macOS | `.dmg` (arm64 + x64) |

Cada instalador lleva dentro el **backend autocontenido** (PyInstaller sobre el
backend ONNX de CPU: sin PyTorch ni Python en la máquina destino, ~300 MB). El
modelo del verificador NO va embebido: se descarga de HuggingFace al primer
uso (~300 MB, `aidam/modelos.py`), con progreso visible en la interfaz.

### Empaquetado local (la misma receta que corre el CI)

```bash
# desde la raíz del repo, con las dependencias de runtime instaladas:
uv pip install pyinstaller
.venv/bin/python packaging/empaquetar_backend.py   # → escritorio/backend/
cd escritorio && npm run empaquetar                # → dist/*.AppImage + *.deb
```

Notas honestas:
- Windows y macOS solo se compilan en el CI (electron-builder no cruza
  plataformas con fiabilidad); se validan al empujar el primer tag.
- El `.dmg` va sin firma de Apple: Gatekeeper avisará hasta tener certificado.
- Los AppImage requieren FUSE2 en el sistema (`libfuse2`); sin él, se pueden
  ejecutar con `--appimage-extract-and-run`.
- Compilar el backend desde un venv de desarrollo (con torch instalado)
  depende de la lista de exclusiones de `packaging/empaquetar_backend.py` —
  medido: sin ellas el binario pasa de ~300 MB a 1.2 GB.

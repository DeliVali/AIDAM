# backend/

Aquí va el binario `aidam` autocontenido (PyInstaller, backend ONNX de CPU)
antes de ejecutar `npm run empaquetar`. electron-builder copia esta carpeta a
`resources/backend/` dentro del paquete, y `main.js` la usa automáticamente
cuando la app está empaquetada. Ver escritorio/README.md.

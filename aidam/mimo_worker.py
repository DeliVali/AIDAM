"""Worker aislado para el LLM local (MiMo vía llama.cpp).

llama.cpp y PyTorch cohabitando en un proceso producen corrupciones de heap
esporádicas (medido: `corrupted size vs. prev_size` + core dump en una
evaluación larga). Este worker corre el modelo en su propio proceso y habla
JSON por líneas: si llama.cpp corrompe memoria, muere el worker — no la
verificación — y el cliente lo reinicia.

Protocolo (una línea JSON por mensaje):
  worker → {"listo": true}                          al terminar de cargar
  cliente → {"prompt": ..., "max_tokens": ..., "temperature": ..., "stop": [...]}
  worker → {"texto": ...} | {"error": ...}

Se lanza con: python -m aidam.mimo_worker
Config por entorno: AIDAM_MODELO_PREGUNTAS, AIDAM_MIMO_GPU_LAYERS.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> None:
    from .preguntas import _precargar_cuda, ruta_modelo

    _precargar_cuda()
    from llama_cpp import Llama

    ruta = os.environ.get("AIDAM_MODELO_PREGUNTAS") or str(ruta_modelo() or "")
    if not ruta or not os.path.exists(ruta):
        print(json.dumps({"error": f"modelo no encontrado: {ruta!r}"}), flush=True)
        return
    llm = Llama(
        model_path=ruta,
        n_ctx=2048,
        n_gpu_layers=int(os.environ.get("AIDAM_MIMO_GPU_LAYERS", "-1")),
        verbose=False,
    )
    print(json.dumps({"listo": True}), flush=True)

    for linea in sys.stdin:
        if not linea.strip():
            continue
        try:
            pedido = json.loads(linea)
            salida = llm.create_completion(
                prompt=pedido["prompt"],
                max_tokens=pedido.get("max_tokens", 160),
                temperature=pedido.get("temperature", 0.0),
                stop=pedido.get("stop") or None,
            )
            respuesta = {"texto": salida["choices"][0]["text"] or ""}
        except Exception as error:  # el cliente decide reintentar
            respuesta = {"error": str(error)}
        print(json.dumps(respuesta, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

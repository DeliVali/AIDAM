"""Isolated worker for the local LLM (llama.cpp).

llama.cpp and PyTorch cohabiting in one process produce sporadic heap
corruption (measured: `corrupted size vs. prev_size` + core dump during a
long evaluation). This worker runs the model in its own process and speaks
JSON lines: if llama.cpp corrupts memory, the worker dies — not the
verification — and the client restarts it.

Protocol (one JSON line per message):
  worker → {"listo": true}                          when loading finishes
  client → {"prompt": ..., "max_tokens": ..., "temperature": ..., "stop": [...]}
  worker → {"texto": ...} | {"error": ...}

Launched with: python -m aidam.llm_worker
Environment config: AIDAM_MODELO_PREGUNTAS, AIDAM_MIMO_GPU_LAYERS.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> None:
    from .questions import _precargar_cuda, ruta_modelo

    _precargar_cuda()
    from llama_cpp import Llama

    ruta = os.environ.get("AIDAM_MODELO_PREGUNTAS") or str(ruta_modelo() or "")
    if not ruta or not os.path.exists(ruta):
        print(json.dumps({"error": f"modelo no encontrado: {ruta!r}"}), flush=True)
        return
    llm = Llama(
        model_path=ruta,
        n_ctx=int(os.environ.get("AIDAM_MIMO_N_CTX", "4096")),
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
        except Exception as error:  # the client decides whether to retry
            respuesta = {"error": str(error)}
        print(json.dumps(respuesta, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

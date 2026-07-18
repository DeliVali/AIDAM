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
Environment config: AIDAM_MODELO_PREGUNTAS, AIDAM_MIMO_GPU_LAYERS, and the
resource-program knobs (docs/AGENT.md §resource program) — every knob
defaults to llama.cpp's own default, so an unset environment reproduces the
historical behavior exactly:
  AIDAM_MIMO_N_CTX          context window (default 6144)
  AIDAM_MIMO_GPU_LAYERS     layers on GPU (-1 = all; partial = hybrid offload)
  AIDAM_MIMO_FLASH_ATTN     "1" enables flash attention
  AIDAM_MIMO_KV_TIPO        KV-cache quantization: "q8_0" | "q4_0" (both K and V)
  AIDAM_MIMO_HILOS          CPU threads (n_threads)
  AIDAM_MIMO_LOTE           batch size (n_batch)
  AIDAM_MIMO_SIN_MMAP       "1" disables mmap; AIDAM_MIMO_MLOCK "1" locks pages
  AIDAM_MIMO_BORRADOR       "lookup" → speculative decoding by prompt-lookup
"""

from __future__ import annotations

import json
import os
import sys


def _config_llama() -> dict:
    """Builds Llama() kwargs from the environment. Pure and import-free so
    tests can check knob plumbing without llama.cpp or a model present."""
    config: dict = {
        "n_ctx": int(os.environ.get("AIDAM_MIMO_N_CTX", "6144")),
        "n_gpu_layers": int(os.environ.get("AIDAM_MIMO_GPU_LAYERS", "-1")),
        "verbose": False,
    }
    if os.environ.get("AIDAM_MIMO_FLASH_ATTN") == "1":
        config["flash_attn"] = True
    kv = os.environ.get("AIDAM_MIMO_KV_TIPO", "")
    if kv in ("q8_0", "q4_0"):
        # llama.cpp ggml type ids: q8_0 = 8, q4_0 = 2 (f16 default = 1)
        tipo = {"q8_0": 8, "q4_0": 2}[kv]
        config["type_k"] = tipo
        config["type_v"] = tipo
        config["flash_attn"] = True  # quantized V-cache requires flash attention
    if os.environ.get("AIDAM_MIMO_HILOS"):
        config["n_threads"] = int(os.environ["AIDAM_MIMO_HILOS"])
    if os.environ.get("AIDAM_MIMO_LOTE"):
        config["n_batch"] = int(os.environ["AIDAM_MIMO_LOTE"])
    if os.environ.get("AIDAM_MIMO_SIN_MMAP") == "1":
        config["use_mmap"] = False
    if os.environ.get("AIDAM_MIMO_MLOCK") == "1":
        config["use_mlock"] = True
    return config


def _borrador():
    """Speculative decoding via prompt-lookup (AIDAM_MIMO_BORRADOR=lookup):
    drafts tokens by matching the prompt itself — no extra model, and a good
    fit for our loop, where answers re-quote observations verbatim. Isolated
    so a broken import degrades to None (no speculation) instead of killing
    the worker. Model-based drafting can slot here later if measured better."""
    if os.environ.get("AIDAM_MIMO_BORRADOR", "") != "lookup":
        return None
    try:
        from llama_cpp.llama_speculative import LlamaPromptLookupDecoding

        return LlamaPromptLookupDecoding(num_pred_tokens=8)
    except Exception:
        return None


def main() -> None:
    from .questions import _precargar_cuda, ruta_modelo

    _precargar_cuda()
    from llama_cpp import Llama

    ruta = os.environ.get("AIDAM_MODELO_PREGUNTAS") or str(ruta_modelo() or "")
    if not ruta or not os.path.exists(ruta):
        print(json.dumps({"error": f"modelo no encontrado: {ruta!r}"}), flush=True)
        return
    config = _config_llama()
    borrador = _borrador()
    if borrador is not None:
        config["draft_model"] = borrador
    llm = Llama(model_path=ruta, **config)
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

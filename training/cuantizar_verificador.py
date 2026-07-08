"""Verifier quantization: verification on any low-RAM CPU.

Measured recipe (2026-07-06), in order of what worked and what didn't:

- ✗ Dynamic INT8 (weights+activations): DeBERTa-v3 collapses 88.3% → 51.4%.
  Its activations have extreme outliers; quantizing them destroys it.
  Excluding attention doesn't help (FFNs alone also collapse).
- ✓ **Weight-only**: compressed weights, activations intact in fp32 — the
  same technique family today's LLMs use (GGUF/AWQ).
  Block-wise INT4 on the MatMuls (MatMulNBits) + INT8 on the embeddings
  (Gather is a lookup: quantizing it doesn't touch activations).

"mini" model result: 1.1 GB → 319 MB (3.4x), 88.3% → 86.1% accuracy (−2.2),
and 80 → 39 ms/pair on CPU (2x faster than fp32/ONNX, ~3x than PyTorch CPU).

Produces two artifacts:
  modelos/verificador-onnx       (fp32: full accuracy, CPU default)
  modelos/verificador-onnx-mini  (int4+int8: low-RAM machines;
                                  AIDAM_BACKEND=onnx-mini)

Usage:
  python training/quantize_verifier.py [--ejemplos 1000]
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

import numpy as np

SALIDA_FP32 = Path("modelos/verificador-onnx")
SALIDA_MINI = Path("modelos/verificador-onnx-mini")
_MAPA = {"SUPPORTS": "entailment", "REFUTES": "contradiction", "NOT ENOUGH INFO": "neutral"}
_EXTRAS = ("config.json", "tokenizer.json", "tokenizer_config.json")


def _evaluar(ruta: Path, ejemplos: int) -> tuple[float, float, float]:
    from datasets import load_dataset

    from aidam.verify import VerificadorONNX

    datos = load_dataset("tals/vitaminc", split="test").shuffle(seed=42)
    datos = datos.select(range(min(ejemplos, len(datos))))
    import json

    id2label = json.loads((ruta / "config.json").read_text())["id2label"]
    por_nombre = {n.lower(): int(i) for i, n in id2label.items()}
    ids = [por_nombre[_MAPA[e]] for e in datos["label"]]
    verificador = VerificadorONNX(str(ruta))
    predichas: list[int] = []
    inicio = time.time()
    for i in range(0, len(datos), 16):
        indices, _ = verificador._predecir_lote(
            list(datos["evidence"])[i : i + 16], list(datos["claim"])[i : i + 16]
        )
        predichas.extend(indices)
    ms_por_par = (time.time() - inicio) / len(datos) * 1000
    exactitud = float(np.mean(np.array(predichas) == np.array(ids)))
    mb = sum(f.stat().st_size for f in ruta.iterdir()) / 1e6
    return exactitud, ms_por_par, mb


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ejemplos", type=int, default=1_000)
    args = parser.parse_args()

    from aidam.verify import _resolver_modelo

    origen = _resolver_modelo()

    # 1) export fp32 (the default CPU backend: full accuracy)
    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer

    print(f"[cuantizar] exportando {origen} → ONNX fp32")
    modelo = ORTModelForSequenceClassification.from_pretrained(origen, export=True)
    modelo.save_pretrained(str(SALIDA_FP32))
    AutoTokenizer.from_pretrained(origen).save_pretrained(str(SALIDA_FP32))

    # 2) mini: block-wise int4 on MatMul + int8 on embeddings
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from onnxruntime.quantization.matmul_nbits_quantizer import MatMulNBitsQuantizer

    print("[cuantizar] mini: int4 (MatMulNBits) + int8 (embeddings)")
    if SALIDA_MINI.exists():
        shutil.rmtree(SALIDA_MINI)
    SALIDA_MINI.mkdir(parents=True)
    intermedio = SALIDA_MINI / "intermedio.onnx"
    grafo = onnx.load(str(SALIDA_FP32 / "model.onnx"))
    cuantizador = MatMulNBitsQuantizer(grafo, block_size=64, is_symmetric=True)
    cuantizador.process()
    onnx.save_model(
        cuantizador.model.model, str(intermedio),
        save_as_external_data=True, location="intermedio.onnx.data",
    )
    quantize_dynamic(
        str(intermedio), str(SALIDA_MINI / "model.onnx"),
        weight_type=QuantType.QInt8, op_types_to_quantize=["Gather"],
    )
    intermedio.unlink()
    (SALIDA_MINI / "intermedio.onnx.data").unlink(missing_ok=True)
    for extra in _EXTRAS:
        if (SALIDA_FP32 / extra).exists():
            shutil.copy(SALIDA_FP32 / extra, SALIDA_MINI / extra)

    # 3) honest comparison
    for nombre, ruta in (("fp32", SALIDA_FP32), ("mini", SALIDA_MINI)):
        exactitud, ms, mb = _evaluar(ruta, args.ejemplos)
        print(f"[cuantizar] {nombre}: exactitud {exactitud:.1%} · {ms:.0f} ms/par · {mb:.0f} MB")


if __name__ == "__main__":
    main()

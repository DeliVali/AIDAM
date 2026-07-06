"""Cuantización del verificador a INT8/ONNX: verificación en cualquier CPU.

La accesibilidad es un principio del proyecto: la verificación no puede exigir
GPU ni una instalación de 3 GB. La cuantización dinámica INT8 sobre ONNX es la
técnica probada para encoders (~4x menos memoria, 2-4x más rápido en CPU, con
pérdida de exactitud ~nula), y el runtime (onnxruntime) pesa ~50 MB.

Exporta el verificador entrenado a ONNX, lo cuantiza a INT8 dinámico, y
compara exactitud y latencia contra el modelo PyTorch en un subconjunto de
VitaminC test.

Uso:
  python training/cuantizar_verificador.py [--ejemplos 2000]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
from datasets import load_dataset

SALIDA = Path("modelos/verificador-onnx-int8")
_MAPA = {"SUPPORTS": "entailment", "REFUTES": "contradiction", "NOT ENOUGH INFO": "neutral"}


def _exactitud_y_latencia(predecir, premisas, hipotesis, ids) -> tuple[float, float]:
    inicio = time.time()
    predichas = predecir(premisas, hipotesis)
    latencia = (time.time() - inicio) / len(premisas)
    return float((np.array(predichas) == np.array(ids)).mean()), latencia * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ejemplos", type=int, default=2_000)
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    from aidam.verify import _resolver_modelo

    origen = _resolver_modelo()
    print(f"[cuantizar] exportando {origen} → ONNX INT8")

    from optimum.onnxruntime import ORTModelForSequenceClassification, ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig
    from transformers import AutoTokenizer

    modelo_ort = ORTModelForSequenceClassification.from_pretrained(origen, export=True)
    tokenizer = AutoTokenizer.from_pretrained(origen)
    args.salida.mkdir(parents=True, exist_ok=True)

    cuantizador = ORTQuantizer.from_pretrained(modelo_ort)
    configuracion = AutoQuantizationConfig.avx512_vnni(is_static=False, per_channel=False)
    cuantizador.quantize(save_dir=str(args.salida), quantization_config=configuracion)
    tokenizer.save_pretrained(str(args.salida))
    print(f"[cuantizar] guardado en {args.salida}")

    # ── comparación honesta en CPU: exactitud y latencia ──
    datos = load_dataset("tals/vitaminc", split="test").shuffle(seed=42)
    datos = datos.select(range(min(args.ejemplos, len(datos))))
    por_nombre = {n.lower(): i for i, n in modelo_ort.config.id2label.items()}
    ids = [por_nombre[_MAPA[e]] for e in datos["label"]]
    premisas, hipotesis = list(datos["evidence"]), list(datos["claim"])

    from aidam.verify import VerificadorNLI, VerificadorONNX

    onnx = VerificadorONNX(str(args.salida))

    def predecir_onnx(ps, hs):
        predichas = []
        for i in range(0, len(ps), 16):
            indices, _probs = onnx._predecir_lote(ps[i : i + 16], hs[i : i + 16])
            predichas.extend(indices)
        return predichas

    exactitud_onnx, ms_onnx = _exactitud_y_latencia(predecir_onnx, premisas, hipotesis, ids)
    print(f"[cuantizar] INT8/ONNX CPU: exactitud {exactitud_onnx:.1%} · {ms_onnx:.0f} ms/par")

    import torch

    torch_cpu = VerificadorNLI(device="cpu")

    def predecir_torch(ps, hs):
        predichas = []
        for i in range(0, len(ps), 16):
            entradas = torch_cpu.tokenizer(
                ps[i : i + 16], hs[i : i + 16], truncation=True, max_length=512,
                padding=True, return_tensors="pt",
            )
            with torch.inference_mode():
                logits = torch_cpu.modelo(**entradas).logits
            predichas.extend(logits.argmax(dim=-1).tolist())
        return predichas

    exactitud_torch, ms_torch = _exactitud_y_latencia(predecir_torch, premisas, hipotesis, ids)
    print(f"[cuantizar] fp32/PyTorch CPU: exactitud {exactitud_torch:.1%} · {ms_torch:.0f} ms/par")
    print(f"[cuantizar] aceleración {ms_torch / max(ms_onnx, 0.01):.1f}x · "
          f"Δexactitud {exactitud_onnx - exactitud_torch:+.2%}")


if __name__ == "__main__":
    main()

"""Verifier core (Module 3): does this evidence support this fact?

MVP: multilingual textual inference (NLI) with mDeBERTa-v3 (~280M params),
which works in Spanish and English from day one and runs on consumer GPU
or CPU. The `juzgar()` interface is the contract: any future backend
(MiniCheck for English, the Phase 1 in-house verifier) implements it the
same way and the rest of the pipeline doesn't change.
"""

from __future__ import annotations

import os
from pathlib import Path

from .models import EtiquetaPar, Evidencia, HechoAtomico, VeredictoPar

_MAPA_NLI = {
    "entailment": EtiquetaPar.SUSTENTA,
    "contradiction": EtiquetaPar.REFUTA,
    "neutral": EtiquetaPar.NO_CONCLUYE,
}


def _resolver_modelo() -> str:
    """Priority: environment variable > locally trained model > public checkpoint."""
    if entorno := os.environ.get("AIDAM_MODELO_VERIFICADOR"):
        return entorno
    local = Path(__file__).resolve().parent.parent / "models" / "verificador-v0"
    if (local / "config.json").exists():
        return str(local)
    return VerificadorNLI.MODELO


def crear_verificador(device: str | None = None):
    """Picks the best available backend: PyTorch (GPU/CPU) or ONNX INT8 (CPU).

    Accessibility first: if torch is not installed but a quantized model and
    onnxruntime (~50 MB) are available, verification works the same on any
    computer. `AIDAM_BACKEND=onnx` forces it.
    """
    # fp32: accuracy identical to torch and 1.4x faster on CPU (default when
    # torch is missing). mini (int4+int8 weight-only): 319 MB and 2x faster at
    # the cost of −2.2 accuracy — for low-RAM machines (AIDAM_BACKEND=onnx-mini).
    # Dynamic INT8 is ruled out by measurement: quantizing DeBERTa-v3
    # activations (extreme outliers) collapses 88%→51%.
    base = Path(__file__).resolve().parent.parent / "models"
    forzado = os.environ.get("AIDAM_BACKEND", "").lower()
    if forzado == "onnx-mini":
        return VerificadorONNX(str(base / "verificador-onnx-mini"))
    if forzado == "onnx":
        return VerificadorONNX(str(base / "verificador-onnx"))
    if forzado != "torch":
        try:
            import torch  # noqa: F401
        except ImportError:
            for candidato in ("verificador-onnx", "verificador-onnx-mini"):
                if (base / candidato / "config.json").exists():
                    return VerificadorONNX(str(base / candidato))
    return VerificadorNLI(device=device)


class VerificadorONNX:
    """INT8/ONNX verifier: same contract as VerificadorNLI, zero GPU.

    Quantized with `training/quantize_verifier.py`; runs with onnxruntime
    on any CPU. Efficiency is a principle, not an extra.
    """

    def __init__(self, ruta: str):
        import onnxruntime
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(ruta)
        onnx_files = sorted(Path(ruta).glob("*.onnx"))
        if not onnx_files:
            raise FileNotFoundError(f"no ONNX model in {ruta}")
        self.sesion = onnxruntime.InferenceSession(
            str(onnx_files[-1]), providers=["CPUExecutionProvider"]
        )
        self._entradas = {e.name for e in self.sesion.get_inputs()}
        import json as _json

        config = _json.loads((Path(ruta) / "config.json").read_text())
        self._etiquetas = {
            int(i): _MAPA_NLI[nombre.lower()] for i, nombre in config["id2label"].items()
        }

    def _predecir_lote(self, premisas: list[str], hipotesis: list[str]):
        import numpy as np

        entradas = self.tokenizer(
            premisas, hipotesis, truncation=True, max_length=512, padding=True, return_tensors="np"
        )
        entradas = {k: v.astype("int64") for k, v in entradas.items() if k in self._entradas}
        (logits,) = self.sesion.run(None, entradas)
        exp = np.exp(logits - logits.max(axis=-1, keepdims=True))
        return logits.argmax(axis=-1).tolist(), (exp / exp.sum(axis=-1, keepdims=True)).tolist()

    def puntuar_entailment(self, premisa: str, hipotesis: list[str]) -> list[float]:
        indice = next(i for i, et in self._etiquetas.items() if et is EtiquetaPar.SUSTENTA)
        _indices, probs = self._predecir_lote([premisa] * len(hipotesis), hipotesis)
        return [fila[indice] for fila in probs]

    def juzgar(
        self,
        hecho: HechoAtomico,
        evidencias: list[Evidencia],
        batch_size: int = 8,
    ) -> list[VeredictoPar]:
        veredictos: list[VeredictoPar] = []
        for inicio in range(0, len(evidencias), batch_size):
            lote = evidencias[inicio : inicio + batch_size]
            indices, probs = self._predecir_lote(
                [e.texto for e in lote], [hecho.texto] * len(lote)
            )
            for evidencia, indice, fila in zip(lote, indices, probs):
                veredictos.append(
                    VeredictoPar(
                        hecho=hecho,
                        evidencia=evidencia,
                        etiqueta=self._etiquetas[indice],
                        prob=float(fila[indice]),
                    )
                )
        return veredictos


class VerificadorNLI:
    """Multilingual NLI-based verifier: premise=evidence, hypothesis=fact."""

    MODELO = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"

    def __init__(self, device: str | None = None, modelo: str | None = None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        ruta = modelo or _resolver_modelo()
        self.tokenizer = AutoTokenizer.from_pretrained(ruta)
        self.modelo = (
            AutoModelForSequenceClassification.from_pretrained(ruta)
            .to(self.device)
            .eval()
        )
        self._etiquetas = {
            i: _MAPA_NLI[nombre.lower()]
            for i, nombre in self.modelo.config.id2label.items()
        }
        # Calibration temperature (training/calibrate_verifier.py):
        # divides the logits so confidence means actual frequency.
        self._temperatura = 1.0
        calibracion = Path(ruta) / "calibracion.json" if Path(ruta).is_dir() else None
        if calibracion and calibracion.exists():
            import json

            self._temperatura = float(json.loads(calibracion.read_text())["temperatura"])

    def puntuar_entailment(self, premisa: str, hipotesis: list[str]) -> list[float]:
        """Probability that the premise supports each hypothesis.

        Generic use of the model's comparative skill (e.g. the router uses
        it to classify topics zero-shot).
        """
        entradas = self.tokenizer(
            [premisa] * len(hipotesis),
            hipotesis,
            truncation=True,
            max_length=512,
            padding=True,
            return_tensors="pt",
        ).to(self.device)
        with self._torch.inference_mode():
            probs = self._torch.softmax(self.modelo(**entradas).logits, dim=-1)
        indice_entailment = next(
            i for i, et in self._etiquetas.items() if et is EtiquetaPar.SUSTENTA
        )
        return [float(fila[indice_entailment]) for fila in probs]

    def juzgar(
        self,
        hecho: HechoAtomico,
        evidencias: list[Evidencia],
        batch_size: int = 8,
    ) -> list[VeredictoPar]:
        """Judges each (fact, evidence) pair and returns label + probability."""
        veredictos: list[VeredictoPar] = []
        for inicio in range(0, len(evidencias), batch_size):
            lote = evidencias[inicio : inicio + batch_size]
            entradas = self.tokenizer(
                [e.texto for e in lote],
                [hecho.texto] * len(lote),
                truncation=True,
                max_length=512,
                padding=True,
                return_tensors="pt",
            ).to(self.device)
            with self._torch.inference_mode():
                logits = self.modelo(**entradas).logits
            probs = self._torch.softmax(logits / self._temperatura, dim=-1)
            for evidencia, fila in zip(lote, probs):
                indice = int(fila.argmax())
                veredictos.append(
                    VeredictoPar(
                        hecho=hecho,
                        evidencia=evidencia,
                        etiqueta=self._etiquetas[indice],
                        prob=float(fila[indice]),
                    )
                )
        return veredictos

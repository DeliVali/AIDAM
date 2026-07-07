"""Núcleo verificador (Módulo 3): ¿esta evidencia sustenta este hecho?

MVP: inferencia textual (NLI) multilingüe con mDeBERTa-v3 (~280M parámetros),
que funciona en español e inglés desde el día uno y corre en GPU de consumo
o CPU. La interfaz `juzgar()` es el contrato: cualquier backend futuro
(MiniCheck para inglés, el verificador propio de la Fase 1) lo implementa
igual y el resto del pipeline no cambia.
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
    """Prioridad: variable de entorno > modelo entrenado local > checkpoint público."""
    if entorno := os.environ.get("AIDAM_MODELO_VERIFICADOR"):
        return entorno
    local = Path(__file__).resolve().parent.parent / "modelos" / "verificador-v0"
    if (local / "config.json").exists():
        return str(local)
    return VerificadorNLI.MODELO


def crear_verificador(device: str | None = None):
    """Elige el mejor backend disponible: PyTorch (GPU/CPU) u ONNX INT8 (CPU).

    Accesibilidad primero: si torch no está instalado pero hay un modelo
    cuantizado y onnxruntime (~50 MB), la verificación funciona igual en
    cualquier computadora. `AIDAM_BACKEND=onnx` lo fuerza.
    """
    # fp32: exactitud idéntica a torch y 1.4x más rápido en CPU (por defecto
    # sin torch). mini (int4+int8 weight-only): 319 MB y 2x más rápido a costa
    # de −2.2 de exactitud — para máquinas con poca RAM (AIDAM_BACKEND=onnx-mini).
    # INT8 dinámico está descartado por medición: cuantizar las activaciones
    # de DeBERTa-v3 (outliers extremos) colapsa 88%→51%.
    base = Path(__file__).resolve().parent.parent / "modelos"
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
    """Verificador INT8/ONNX: mismo contrato que VerificadorNLI, cero GPU.

    Cuantizado con `training/cuantizar_verificador.py`; corre con onnxruntime
    en cualquier CPU. La eficiencia es un principio, no un extra.
    """

    def __init__(self, ruta: str):
        import onnxruntime
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(ruta)
        onnx_files = sorted(Path(ruta).glob("*.onnx"))
        if not onnx_files:
            raise FileNotFoundError(f"sin modelo ONNX en {ruta}")
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
    """Verificador basado en NLI multilingüe: premisa=evidencia, hipótesis=hecho."""

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
        # Temperatura de calibración (training/calibrar_verificador.py):
        # divide los logits para que la confianza signifique frecuencia real.
        self._temperatura = 1.0
        calibracion = Path(ruta) / "calibracion.json" if Path(ruta).is_dir() else None
        if calibracion and calibracion.exists():
            import json

            self._temperatura = float(json.loads(calibracion.read_text())["temperatura"])

    def puntuar_entailment(self, premisa: str, hipotesis: list[str]) -> list[float]:
        """Probabilidad de que la premisa sustente cada hipótesis.

        Uso genérico de la habilidad comparativa del modelo (p. ej. el router
        la usa para clasificar temas en zero-shot).
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
        """Juzga cada par (hecho, evidencia) y devuelve etiqueta + probabilidad."""
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

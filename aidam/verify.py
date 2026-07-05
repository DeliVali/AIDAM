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
            probs = self._torch.softmax(logits, dim=-1)
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

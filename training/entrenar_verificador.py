"""Fase 1 (v0): especializar el verificador en lógica comparativa con VitaminC.

VitaminC (tals/vitaminc) contiene ~370k pares (afirmación, evidencia) construidos
por contraste: ediciones mínimas de Wikipedia que voltean el veredicto. Entrenar
con estos pares obliga al modelo a fijarse en la diferencia que importa, no en el
parecido superficial — exactamente la habilidad núcleo de AIDAM.

Partimos del checkpoint NLI multilingüe (que ya sabe español) y lo especializamos,
reutilizando su cabeza entailment/neutral/contradiction.

Uso:
  python training/entrenar_verificador.py                  # entrenamiento completo
  python training/entrenar_verificador.py --solo-evaluar   # medir sin entrenar
  python training/entrenar_verificador.py --smoke           # prueba de 30 pasos
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from datasets import load_dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

CHECKPOINT_BASE = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
DATASET = "tals/vitaminc"
SALIDA = Path(__file__).resolve().parent.parent / "modelos" / "verificador-v0"
MAX_LEN = 256
SEMILLA = 42

# VitaminC → etiquetas de la cabeza NLI del checkpoint
_MAPA_VITAMINC = {
    "SUPPORTS": "entailment",
    "REFUTES": "contradiction",
    "NOT ENOUGH INFO": "neutral",
}


def _resolver_ids(modelo) -> dict[str, int]:
    """label→id de la cabeza del checkpoint, para reutilizarla sin reiniciar."""
    por_nombre = {nombre.lower(): i for i, nombre in modelo.config.id2label.items()}
    return {
        vitaminc: por_nombre[nli]
        for vitaminc, nli in _MAPA_VITAMINC.items()
    }


def _metricas(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    exactitud = float((preds == labels).mean())
    f1s = []
    for clase in np.unique(labels):
        tp = int(((preds == clase) & (labels == clase)).sum())
        fp = int(((preds == clase) & (labels != clase)).sum())
        fn = int(((preds != clase) & (labels == clase)).sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        cobertura = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(
            2 * precision * cobertura / (precision + cobertura)
            if precision + cobertura
            else 0.0
        )
    return {"exactitud": exactitud, "f1_macro": float(np.mean(f1s))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solo-evaluar", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="30 pasos, para validar el script")
    parser.add_argument("--ejemplos", type=int, default=120_000, help="ejemplos de entrenamiento")
    parser.add_argument(
        "--ejemplos-nli",
        type=int,
        default=60_000,
        help="ejemplos de MNLI mezclados para conservar la clase neutral. Medido en "
        "producción: entrenar solo con VitaminC (contrastivo) hace que el modelo "
        "sobre-refute con pasajes relacionados pero no probatorios",
    )
    parser.add_argument("--eval-ejemplos", type=int, default=10_000, help="ejemplos de test")
    parser.add_argument("--checkpoint", default=CHECKPOINT_BASE)
    args = parser.parse_args()

    print(f"[entrenar] checkpoint: {args.checkpoint}")
    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    modelo = AutoModelForSequenceClassification.from_pretrained(args.checkpoint)
    etiqueta_a_id = _resolver_ids(modelo)
    print(f"[entrenar] mapa de etiquetas: {etiqueta_a_id}")

    datos = load_dataset(DATASET)

    def preparar(lote):
        # Mismo orden que aidam/verify.py: premisa=evidencia, hipótesis=afirmación.
        entradas = tokenizer(
            lote["evidence"], lote["claim"], truncation=True, max_length=MAX_LEN
        )
        entradas["labels"] = [etiqueta_a_id[e] for e in lote["label"]]
        return entradas

    train = (
        datos["train"]
        .shuffle(seed=SEMILLA)
        .select(range(min(args.ejemplos, len(datos["train"]))))
        .map(preparar, batched=True, remove_columns=datos["train"].column_names)
    )
    test = (
        datos["test"]
        .shuffle(seed=SEMILLA)
        .select(range(min(args.eval_ejemplos, len(datos["test"]))))
        .map(preparar, batched=True, remove_columns=datos["test"].column_names)
    )

    if args.ejemplos_nli > 0 and not args.smoke:
        from datasets import concatenate_datasets

        por_nombre = {n.lower(): i for i, n in modelo.config.id2label.items()}
        mnli = load_dataset("nyu-mll/multi_nli", split="train").shuffle(seed=SEMILLA)
        mnli = mnli.select(range(min(args.ejemplos_nli, len(mnli))))
        # MNLI etiqueta 0/1/2 = entailment/neutral/contradiction
        ids_mnli = {0: por_nombre["entailment"], 1: por_nombre["neutral"], 2: por_nombre["contradiction"]}

        def preparar_mnli(lote):
            entradas = tokenizer(
                lote["premise"], lote["hypothesis"], truncation=True, max_length=MAX_LEN
            )
            entradas["labels"] = [ids_mnli[e] for e in lote["label"]]
            return entradas

        nli = mnli.map(preparar_mnli, batched=True, remove_columns=mnli.column_names)
        train = concatenate_datasets([train, nli]).shuffle(seed=SEMILLA)
        print(f"[entrenar] mezcla: {len(train)} ejemplos (VitaminC + {len(nli)} MNLI)")

    argumentos = TrainingArguments(
        output_dir=str(SALIDA.parent / "checkpoints"),
        num_train_epochs=1,
        max_steps=30 if args.smoke else -1,
        # batch efectivo 32; DeBERTa-v3 no cabe con batch directo de 32 en 12 GB.
        # Sin gradient checkpointing: su backward mostró inestabilidad (colapso
        # a una clase en la corrida v1); batch 8 + acumulación 4 cabe sin él.
        per_device_train_batch_size=8,
        gradient_accumulation_steps=4,
        per_device_eval_batch_size=32,
        learning_rate=1e-5,
        warmup_ratio=0.06,
        bf16=True,  # DeBERTa-v3 produce NaNs con fp16; bf16 es estable
        logging_steps=100,
        # Red de seguridad contra colapso tardío: evalúa periódicamente y
        # recupera el mejor checkpoint del camino, no el último.
        eval_strategy="no" if args.smoke else "steps",
        eval_steps=500,
        save_strategy="no" if args.smoke else "steps",
        save_steps=500,
        save_total_limit=1,
        load_best_model_at_end=not args.smoke,
        metric_for_best_model="eval_exactitud",
        greater_is_better=True,
        report_to="none",
        seed=SEMILLA,
    )
    trainer = Trainer(
        model=modelo,
        args=argumentos,
        train_dataset=train,
        eval_dataset=test,
        processing_class=tokenizer,
        compute_metrics=_metricas,
    )

    resultados = {"checkpoint": args.checkpoint, "dataset": DATASET}
    print("[entrenar] evaluando en VitaminC test…")
    resultados["antes"] = trainer.evaluate()
    print(json.dumps(resultados["antes"], indent=2))

    if not args.solo_evaluar:
        print(f"[entrenar] entrenando con {len(train)} ejemplos…")
        trainer.train()
        resultados["despues"] = trainer.evaluate()
        print(json.dumps(resultados["despues"], indent=2))

        if args.smoke:
            print("[entrenar] smoke: no se guarda el modelo")
            return
        SALIDA.mkdir(parents=True, exist_ok=True)
        trainer.save_model(str(SALIDA))
        tokenizer.save_pretrained(str(SALIDA))
        (SALIDA / "resultados.json").write_text(
            json.dumps(resultados, indent=2, ensure_ascii=False)
        )
        print(f"[entrenar] modelo guardado en {SALIDA}")


if __name__ == "__main__":
    main()

"""Phase 1 (v0): specialize the verifier in comparative logic with VitaminC.

VitaminC (tals/vitaminc) contains ~370k (claim, evidence) pairs built by
contrast: minimal Wikipedia edits that flip the verdict. Training on these
pairs forces the model to focus on the difference that matters, not on
surface similarity — exactly AIDAM's core skill.

We start from the multilingual NLI checkpoint (which already knows Spanish)
and specialize it, reusing its entailment/neutral/contradiction head.

Usage:
  python training/train_verifier.py                  # full training
  python training/train_verifier.py --solo-evaluar   # measure without training
  python training/train_verifier.py --smoke          # 30-step sanity run
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
SALIDA = Path(__file__).resolve().parent.parent / "models" / "verificador-v0"
MAX_LEN = 256  # overridable via --max-len (long-document data needs 512)
SEMILLA = 42

# VitaminC → labels of the checkpoint's NLI head
_MAPA_VITAMINC = {
    "SUPPORTS": "entailment",
    "REFUTES": "contradiction",
    "NOT ENOUGH INFO": "neutral",
}


def _resolver_ids(modelo) -> dict[str, int]:
    """label→id of the checkpoint's head, to reuse it without reinitializing."""
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
    parser.add_argument("--smoke", action="store_true", help="30 steps, to validate the script")
    parser.add_argument("--ejemplos", type=int, default=120_000, help="training examples")
    parser.add_argument(
        "--ejemplos-nli",
        type=int,
        default=60_000,
        help="MNLI examples mixed in to preserve the neutral class. Measured in "
        "production: training on VitaminC alone (contrastive) makes the model "
        "over-refute on related but non-probative passages",
    )
    parser.add_argument("--eval-ejemplos", type=int, default=10_000, help="test examples")
    parser.add_argument(
        "--neutrales-dificiles",
        type=Path,
        default=Path("data/local/hard_neutrals.jsonl"),
        help="hard-neutral pairs (training/generate_neutrals.py); they attack "
        "the measured failure: generic intros judged as contradiction",
    )
    parser.add_argument(
        "--sinteticos",
        type=Path,
        default=Path("data/local/synthetic_llm.jsonl"),
        help="subtle errors generated with a local LLM (training/generate_synthetic_llm.py)",
    )
    parser.add_argument(
        "--averitec",
        type=Path,
        default=Path("data/local/averitec_train_pairs.jsonl"),
        help="in-domain pairs from the AVeriTeC train split "
        "(training/generate_averitec_pairs.py); never touches dev",
    )
    parser.add_argument(
        "--negaciones",
        type=Path,
        default=Path("data/local/denial_pairs.jsonl"),
        help="denial-pattern pairs (training/generate_denial_pairs.py); teach that "
        "'X denied reports that Y' refutes Y — the traced Pogba-case gap where "
        "denial passages all read NEUTRAL. Three-way balanced by construction",
    )
    parser.add_argument(
        "--scifact",
        type=Path,
        default=Path("data/local/scifact_pairs.jsonl"),
        help="scientific-register pairs from SciFact TRAIN "
        "(training/generate_scifact_pairs.py); closes the hedged-language gap "
        "SciFact dev exposed. Never touches dev/test",
    )
    parser.add_argument(
        "--fever",
        type=Path,
        default=Path("data/local/fever_pairs.jsonl"),
        help="FEVER-register pairs from FEVER train (training/generate_fever_pairs.py); "
        "balanced 3-class, targets FEVER headroom and NEI reinforcement. Never touches "
        "the validation split used for evaluation",
    )
    parser.add_argument(
        "--longdoc",
        type=Path,
        default=Path("data/local/longdoc_pairs.jsonl"),
        help="D2C long-document pairs (training/generate_longdoc_pairs.py): "
        "LLM-composed multi-sentence claims over real article chunks -- the "
        "purpose-built MiniCheck-style register, three-way balanced",
    )
    parser.add_argument(
        "--temporales",
        type=Path,
        default=Path("data/local/temporal_pairs.jsonl"),
        help="temporal/quantity-qualification pairs (training/generate_temporal_pairs.py): "
        "a number for a DIFFERENT time doesn't contradict a time-qualified claim — the "
        "biggest v8-500 error signature. Three-way balanced by construction",
    )
    parser.add_argument(
        "--fecha-neutrales",
        type=Path,
        default=Path("data/local/date_neutrals.jsonl"),
        help="same-topic, different-date hard neutrals (training/generate_date_neutrals.py); "
        "targets the traced failure where a close-but-different date on a related event "
        "reads as confident contradiction instead of ambiguity",
    )
    parser.add_argument("--checkpoint", default=CHECKPOINT_BASE)
    parser.add_argument(
        "--salida", type=Path, default=SALIDA,
        help="output dir (default models/verificador-v0)",
    )
    parser.add_argument(
        "--max-len", type=int, default=MAX_LEN,
        help="tokenizer truncation length; 512 for long-document mixes "
        "(batch auto-halves to fit 12 GB)",
    )
    parser.add_argument(
        "--docnli",
        type=Path,
        default=Path("data/local/docnli_pairs.jsonl"),
        help="long-document pairs mined from DocNLI (training/mine_docnli_pairs.py); "
        "the register LLM-AggreFact needs. entailment/not-entailment only, "
        "mapped SUPPORTS/NEI — never REFUTES",
    )
    parser.add_argument(
        "--reanudar", action="store_true",
        help="resume from the last checkpoint in the shared checkpoints dir "
        "(they save every 500 steps; a GPU watchdog kill needn't cost the run)",
    )
    parser.add_argument(
        "--epocas", type=float, default=1.0,
        help="training epochs (v0-v5 all used 1; single-epoch NLI fine-tunes "
        "are typically under-converged)",
    )
    args = parser.parse_args()

    print(f"[entrenar] checkpoint: {args.checkpoint}")
    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    modelo = AutoModelForSequenceClassification.from_pretrained(args.checkpoint)
    etiqueta_a_id = _resolver_ids(modelo)
    print(f"[entrenar] mapa de etiquetas: {etiqueta_a_id}")

    datos = load_dataset(DATASET)

    def preparar(lote):
        # Same order as aidam/verify.py: premise=evidence, hypothesis=claim.
        entradas = tokenizer(
            lote["evidence"], lote["claim"], truncation=True, max_length=args.max_len
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
        # MNLI labels 0/1/2 = entailment/neutral/contradiction
        ids_mnli = {0: por_nombre["entailment"], 1: por_nombre["neutral"], 2: por_nombre["contradiction"]}

        def preparar_mnli(lote):
            entradas = tokenizer(
                lote["premise"], lote["hypothesis"], truncation=True, max_length=args.max_len
            )
            entradas["labels"] = [ids_mnli[e] for e in lote["label"]]
            return entradas

        nli = mnli.map(preparar_mnli, batched=True, remove_columns=mnli.column_names)
        partes = [train, nli]
        etiqueta_mezcla = f"VitaminC + {len(nli)} MNLI"

        for ruta, nombre in (
            (args.neutrales_dificiles, "neutrales-difíciles"),
            (args.sinteticos, "sintéticos-MiMo"),
            (args.averitec, "averitec-train"),
            (args.negaciones, "negaciones"),
            (args.scifact, "scifact"),
            (args.fever, "fever"),
            (args.docnli, "docnli"),
            (args.longdoc, "longdoc-d2c"),
        ):
            if ruta.exists():
                extra = load_dataset("json", data_files=str(ruta), split="train").map(
                    preparar,
                    batched=True,
                    remove_columns=["claim", "evidence", "label", "origen"],
                )
                partes.append(extra)
                etiqueta_mezcla += f" + {len(extra)} {nombre}"

        train = concatenate_datasets(partes).shuffle(seed=SEMILLA)
        print(f"[entrenar] mezcla: {len(train)} ejemplos ({etiqueta_mezcla})")

    argumentos = TrainingArguments(
        output_dir=str(args.salida.parent / "checkpoints"),
        num_train_epochs=args.epocas,
        max_steps=30 if args.smoke else -1,
        # Effective batch 32; DeBERTa-v3 doesn't fit a direct batch of 32 in 12 GB.
        # No gradient checkpointing: its backward showed instability (collapse
        # to one class in the v1 run); batch 8 + accumulation 4 fits without it.
        per_device_train_batch_size=8 if args.max_len <= 256 else 4,
        gradient_accumulation_steps=4 if args.max_len <= 256 else 8,
        per_device_eval_batch_size=32,
        learning_rate=1e-5,
        warmup_ratio=0.06,
        bf16=True,  # DeBERTa-v3 produces NaNs with fp16; bf16 is stable
        logging_steps=100,
        # Safety net against late collapse: evaluate periodically and
        # recover the best checkpoint along the way, not the last one.
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
        trainer.train(resume_from_checkpoint=args.reanudar or None)
        resultados["despues"] = trainer.evaluate()
        print(json.dumps(resultados["despues"], indent=2))

        if args.smoke:
            print("[entrenar] smoke: no se guarda el modelo")
            return
        args.salida.mkdir(parents=True, exist_ok=True)
        trainer.save_model(str(args.salida))
        tokenizer.save_pretrained(str(args.salida))
        (args.salida / "resultados.json").write_text(
            json.dumps(resultados, indent=2, ensure_ascii=False)
        )
        print(f"[entrenar] modelo guardado en {args.salida}")


if __name__ == "__main__":
    main()

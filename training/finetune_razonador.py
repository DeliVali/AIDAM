"""QLoRA fine-tune of the task reasoner for OUR action-JSON format.

Jeffrey's directive (2026-07-17): start fine-tuning the reasoner in
parallel with the loop, on public tool-use data, behind GATE FT
(docs/AGENT.md): the adapter replaces the base ONLY if first-parse action
validity >= base AND T1 pass rate >= base AND no regression on the
existing questions.py roles. A miss is a documented rejection.

Recipe: Glaive function-calling v2 (public, Apache-2.0) reformatted into
AIDAM's exact runtime format — the system prompt from razonador.py with
the sample's own function schemas rendered as registry lines, and the
assistant turn as {"herramienta": ..., "argumentos": {...}}. Target is
FORMAT RELIABILITY and step economy, not knowledge.

QLoRA 4-bit (nf4, bf16 compute), r=16 on attention+MLP projections —
fits an 8B on the 12 GB card with micro-batch 1 + accumulation. After
training: merge the adapter and requantize to GGUF Q4_K_M for the
llm_worker (commands printed at the end).

GPU containment (house rule): this occupies the WHOLE card. Run only in
a window with no app / no 8B worker / no eval active.

Usage:
    .venv/bin/python training/finetune_razonador.py \
        [--base deepseek-ai/DeepSeek-R1-0528-Qwen3-8B] [--muestras 8000] \
        [--salida models/razonador-lora-v1] [--epocas 1]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_PLANTILLA_SISTEMA = (
    "You are AIDAM, a local agent that solves tasks in small, verifiable steps.\n"
    "Each step: think briefly (3 short sentences MAX — never re-examine in "
    "circles), then emit EXACTLY ONE JSON object on its own line, nothing after it:\n"
    '  {{"herramienta": "<tool name>", "argumentos": {{...}}}}\n'
    "To finish, emit:\n"
    '  {{"herramienta": "responder", "argumentos": {{"texto": "<final answer>"}}}}\n\n'
    "Tools:\n{herramientas}\n\n"
    "Hard rules:\n"
    "- Never state a fact you have not seen in an observation.\n"
    "- Prefer quoting observations verbatim in your final answer.\n"
)

_P_FUNCION = re.compile(r"\{.*\}", re.DOTALL)


def _herramientas_de_glaive(sistema: str) -> str:
    """Renders the sample's function schemas as AIDAM registry lines."""
    lineas = []
    for bloque in re.findall(r"\{(?:[^{}]|\{[^{}]*\})*\}", sistema):
        try:
            funcion = json.loads(bloque)
        except ValueError:
            continue
        nombre = funcion.get("name")
        if not nombre:
            continue
        props = ((funcion.get("parameters") or {}).get("properties") or {})
        params = ", ".join(f"{p}: {v.get('type', 'str')}" for p, v in props.items())
        lineas.append(f"- {nombre}({params}): {funcion.get('description', '')}")
    return "\n".join(lineas)


def _convertir(muestra: dict) -> list[dict] | None:
    """One Glaive conversation → ChatML text pairs in OUR runtime format."""
    sistema = muestra.get("system", "")
    herramientas = _herramientas_de_glaive(sistema)
    if not herramientas:
        return None
    charla = muestra.get("chat", "")
    # Glaive v2 chat format: USER: … ASSISTANT: … <functioncall> {...} FUNCTION RESPONSE: {...}
    eventos = re.split(r"(USER:|ASSISTANT:|FUNCTION RESPONSE:)", charla)
    turnos: list[tuple[str, str]] = []
    rol = None
    for trozo in eventos:
        if trozo in ("USER:", "ASSISTANT:", "FUNCTION RESPONSE:"):
            rol = trozo
            continue
        texto = trozo.strip().removesuffix("<|endoftext|>").strip()
        if not texto or rol is None:
            continue
        turnos.append((rol, texto))

    sistema_aidam = _PLANTILLA_SISTEMA.format(herramientas=herramientas)
    ejemplos, historial = [], []
    for rol, texto in turnos:
        if rol == "USER:":
            historial.append(("user", f"Tarea: {texto}" if not historial else texto))
        elif rol == "FUNCTION RESPONSE:":
            historial.append(("user", f"Observación:\n{texto}"))
        elif rol == "ASSISTANT:":
            llamada = re.search(r"<functioncall>\s*(\{.*)", texto, re.DOTALL)
            if llamada:
                try:
                    cruda = json.loads(llamada.group(1).strip().rstrip("<|endoftext|>").strip())
                    accion = {"herramienta": cruda.get("name", ""),
                              "argumentos": cruda.get("arguments") or {}}
                    if isinstance(accion["argumentos"], str):
                        accion["argumentos"] = json.loads(accion["argumentos"])
                except (ValueError, AttributeError):
                    continue
            else:
                accion = {"herramienta": "responder", "argumentos": {"texto": texto}}
            objetivo = json.dumps(accion, ensure_ascii=False)
            prompt = (
                f"<|im_start|>system\n{sistema_aidam}<|im_end|>\n"
                + "".join(f"<|im_start|>{r}\n{c}<|im_end|>\n" for r, c in historial)
                + "<|im_start|>assistant\n"
            )
            ejemplos.append({"prompt": prompt, "respuesta": objetivo + "<|im_end|>"})
            historial.append(("assistant", objetivo))
    return ejemplos or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B")
    parser.add_argument("--muestras", type=int, default=8000)
    parser.add_argument("--salida", default="models/razonador-lora-v1")
    parser.add_argument("--epocas", type=int, default=1)
    parser.add_argument("--solo-datos", action="store_true",
                        help="solo generar y guardar el dataset convertido")
    args = parser.parse_args()

    from datasets import load_dataset

    print("[finetune] descargando Glaive function-calling v2…", file=sys.stderr)
    crudo = load_dataset("glaiveai/glaive-function-calling-v2", split="train")
    ejemplos = []
    for muestra in crudo:
        convertidos = _convertir(muestra)
        if convertidos:
            ejemplos.extend(convertidos)
        if len(ejemplos) >= args.muestras:
            break
    print(f"[finetune] {len(ejemplos)} ejemplos en formato AIDAM", file=sys.stderr)
    ruta_datos = Path("data/local/razonador_sft.jsonl")
    ruta_datos.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_datos, "w", encoding="utf-8") as archivo:
        for e in ejemplos:
            archivo.write(json.dumps(e, ensure_ascii=False) + "\n")
    if args.solo_datos:
        print(f"[finetune] dataset en {ruta_datos}; nada entrenado (--solo-datos)")
        return

    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              BitsAndBytesConfig, Trainer, TrainingArguments)

    tokenizador = AutoTokenizer.from_pretrained(args.base)
    modelo = AutoModelForCausalLM.from_pretrained(
        args.base,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        ),
        device_map="auto",
    )
    # Attempt-3 post-mortem: OOM at loss time with 10.24 GiB already used —
    # consistent with gradient checkpointing never engaging. Belt and
    # braces: configure it HERE (kbit-aware path) and kill the KV cache.
    modelo.config.use_cache = False
    modelo = prepare_model_for_kbit_training(
        modelo, use_gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    # Attention-only adapter: attempt 2 OOMed by 178 MiB on 12 GB even at
    # 1024 tokens with the paged optimizer — MLP adapters cost the margin,
    # and the training objective (action-format reliability) lives mostly
    # in attention. max_length 768 for the same reason.
    modelo = get_peft_model(modelo, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    ))

    def _tokenizar(ejemplo):
        completo = ejemplo["prompt"] + ejemplo["respuesta"]
        # 1024, not 2048: the first run OOMed on 12 GB (activation spike to
        # >11.5 GiB at step 1). Tool-call turns are short; truncation from
        # the LEFT would lose the system prompt, so plain right truncation
        # keeps instructions + drops only overlong middle history.
        ids = tokenizador(completo, truncation=True, max_length=640)
        etiquetas = list(ids["input_ids"])
        n_prompt = len(tokenizador(ejemplo["prompt"])["input_ids"])
        etiquetas[:n_prompt] = [-100] * min(n_prompt, len(etiquetas))
        ids["labels"] = etiquetas
        return ids

    from datasets import Dataset

    datos = Dataset.from_list(ejemplos).map(
        _tokenizar, remove_columns=["prompt", "respuesta"])

    from transformers import DataCollatorForSeq2Seq

    Trainer(
        model=modelo,
        args=TrainingArguments(
            output_dir=args.salida, num_train_epochs=args.epocas,
            per_device_train_batch_size=1, gradient_accumulation_steps=16,
            learning_rate=1e-4, bf16=True, logging_steps=20,
            save_strategy="epoch", report_to=[], gradient_checkpointing=True,
            # OOM fixes after the first run died on 12 GB: paged optimizer
            # states + non-reentrant checkpointing (required for PEFT
            # adapters to actually recompute instead of caching).
            optim="paged_adamw_8bit",
            gradient_checkpointing_kwargs={"use_reentrant": False},
        ),
        train_dataset=datos,
        data_collator=DataCollatorForSeq2Seq(tokenizador, padding=True),
    ).train()
    modelo.save_pretrained(args.salida)
    print(
        f"[finetune] adaptador en {args.salida}. Para servirlo:\n"
        f"  1) fusionar: peft merge → modelo HF completo\n"
        f"  2) recuantizar: llama.cpp convert_hf_to_gguf.py + quantize Q4_K_M\n"
        f"  3) AIDAM_MODELO_PREGUNTAS=<gguf nuevo> y correr GATE FT "
        f"(evaluation/eval_tareas.py) ANTES de promover."
    )


if __name__ == "__main__":
    main()

#!/bin/bash
# BFCL V4 phase 1 — non-live single-turn subset on the base reasoner.
# Requires a llama.cpp OpenAI-compatible server already up on $PORT serving
# the GGUF (see docs; llama_cpp.server needs the venv's nvidia-*-cu12 libs on
# LD_LIBRARY_PATH). BFCL_PROJECT_ROOT keeps result/ and score/ in the repo,
# not inside the installed package.
set -eu
RAIZ=/home/jeffrey/Proyectos/AIDAM
cd "$RAIZ/evaluation/bfcl"
export BFCL_PROJECT_ROOT="$RAIZ/evaluation/bfcl"
export LOCAL_SERVER_ENDPOINT=127.0.0.1 LOCAL_SERVER_PORT=8237 OPENAI_API_KEY=local
MODELO=deepseek-ai/DeepSeek-R1
CATS=simple_python,multiple,parallel,parallel_multiple,irrelevance

echo "=== BFCL FASE 1: generacion ($CATS) ==="
"$RAIZ/.venv/bin/bfcl" generate --model "$MODELO" --test-category "$CATS" \
  --skip-server-setup --allow-overwrite

echo "=== BFCL FASE 1: evaluacion ==="
"$RAIZ/.venv/bin/bfcl" evaluate --model "$MODELO" --test-category "$CATS"

echo "=== BFCL FASE 1 COMPLETA — ver score/data_non_live.csv (Non-Live Overall) ==="

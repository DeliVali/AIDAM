<img src="assets/aidamlogo.svg" alt="AIDAM" width="100%">

# AIDAM

Verificador de hechos abierto. En vez de confiar en lo que un modelo recuerda,
AIDAM busca evidencia en vivo en múltiples fuentes y un modelo pequeño
especializado la compara con la afirmación. Cada veredicto cita sus fuentes.

## Cómo funciona

1. **Descompone** la afirmación en hechos verificables.
2. **Recupera** evidencia en paralelo: Wikipedia (en varios idiomas vía enlaces
   interlingüísticos), web abierta, Wikinews, Stack Overflow, Semantic Scholar,
   OpenAlex, arXiv y Europe PMC, más una búsqueda dirigida a fact-checkers.
   Un router elige las fuentes según el tema de la afirmación.
3. **Juzga** cada par (hecho, pasaje) con un verificador NLI multilingüe de 280M
   parámetros entrenado para esta tarea.
4. **Agrega** con reglas explícitas y auditables: un dominio es una sola voz,
   los fact-checkers y la academia pesan más, repetir la afirmación no cuenta
   como evidencia, y los desmentidos mal leídos se descuentan.
5. Emite el veredicto — **sustentado / refutado / evidencia contradictoria /
   evidencia insuficiente** — con las citas que lo justifican.

Opcional: MiMo-7B-RL (cuantizado, corriendo local en proceso aislado) genera
preguntas de búsqueda para dirigir la recuperación y detecta afirmaciones que
engañan por omisión.

## Uso

```bash
git clone https://github.com/DeliVali/AIDAM.git && cd AIDAM
uv venv --python 3.12
uv pip install -e ".[verificador]"
.venv/bin/aidam verificar "La Torre Eiffel está en París"
```

Corre en GPU, en CPU sin PyTorch (`aidam[verificador-cpu]`, ONNX Runtime) o en
máquinas con poca RAM (modelo cuantizado de 319 MB, `AIDAM_BACKEND=onnx-mini`).
El modelo está publicado en
[HuggingFace](https://huggingface.co/DeliVali/aidam-verificador).

## Tecnologías

- **Verificador**: mDeBERTa-v3 (280M) afinado con VitaminC, MNLI y datos
  sintéticos propios. PyTorch para entrenar; ONNX Runtime para CPU;
  cuantización weight-only (int4 por bloques + embeddings int8) para el mini.
- **LLM local**: MiMo-7B-RL (Xiaomi) en GGUF Q4 vía llama.cpp.
- **Evaluación continua**: AVeriTeC (afirmaciones reales con veredicto anotado);
  cada cambio del sistema se mide antes de integrarse.

## Estado

44% de exactitud en AVeriTeC-500 a 17.9 s por afirmación. Contra el mismo LLM
de razonamiento sin recuperación: +16 puntos de exactitud y 3x más rápido.
Números, arquitectura y roadmap en [docs/](docs/).

## Contribuir

Licencia Apache 2.0. Guía para colaborar en [CONTRIBUTING.md](CONTRIBUTING.md);
código de conducta en [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

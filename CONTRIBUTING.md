# Contribuir a AIDAM

AIDAM es un proyecto abierto: el conocimiento es libre y las herramientas para
verificarlo también deben serlo. Toda contribución es bienvenida — código, datos,
evaluaciones, documentación, traducciones o ideas en los issues.

## Preparar el entorno

Requisitos: Python ≥ 3.10 y [uv](https://docs.astral.sh/uv/) (recomendado).

```bash
git clone https://github.com/DeliVali/AIDAM.git
cd AIDAM
uv venv --python 3.12
uv pip install -e ".[dev]"           # núcleo + tests
uv pip install -e ".[verificador]"   # + modelo verificador (torch, transformers)
```

Correr los tests (no necesitan GPU ni red):

```bash
.venv/bin/python -m pytest
```

Probar el sistema completo (descarga el modelo la primera vez):

```bash
.venv/bin/aidam verificar "La Torre Eiffel está en París"
```

## Dónde ayudar

El [roadmap](docs/ROADMAP.md) manda. Áreas abiertas por dificultad:

| Nivel | Área |
|---|---|
| Fácil | Más fuentes en el recuperador (APIs abiertas, datasets públicos) |
| Fácil | Mejorar la salida de la CLI, traducciones, documentación |
| Medio | Heurísticas del descompositor; tests de casos difíciles |
| Medio | Métricas del agregador (independencia de fuentes, temporalidad) |
| Difícil | Evaluación en AVeriTeC / LLM-AggreFact (Fase 0, criterio de éxito) |
| Difícil | Generación de datos sintéticos y entrenamiento del verificador propio (Fase 1) |

## Reglas del juego

1. **Todo veredicto cita su evidencia.** Ningún cambio puede hacer que el sistema
   afirme algo sin fuente trazable.
2. **El agregador se mantiene auditable.** Lógica explícita y testeada; nada de cajas
   negras en el Módulo 4.
3. **Hardware de consumo primero.** Si tu mejora exige una GPU de datacenter, no es
   para este repo (o va detrás de un flag opcional).
4. **Tests para la lógica.** Los módulos deterministas (descompositor, agregador) llevan
   tests de unidad; los módulos con modelo llevan al menos un smoke test.

## Flujo

1. Abre un issue describiendo el cambio (o toma uno existente).
2. Rama desde `main`, cambios pequeños y enfocados.
3. `pytest` en verde.
4. Pull request explicando *qué* y *por qué*; el CI y la revisión hacen el resto.

## Licencia

Al contribuir aceptas que tu aporte se publique bajo [Apache 2.0](LICENSE), la misma
licencia del proyecto: libre para usar, modificar y redistribuir, con concesión
explícita de patentes. Tu código pertenece a todos, para siempre.

<img src="assets/aidamlogo.svg" alt="AIDAM" width="100%">

# AIDAM — Agente de Inteligencia por Deducción y Análisis Multi-fuente

Un sistema agéntico de **lógica comparativa**: no memoriza el conocimiento del mundo en sus
parámetros — lo **verifica** contrastando evidencia de múltiples fuentes independientes,
como lo haría un científico.

## La tesis

Los LLMs gigantes intentan comprimir todo el conocimiento humano en pesos. AIDAM apuesta
por lo contrario: un modelo pequeño (<1B parámetros) especializado en **una sola habilidad**
— juzgar si una afirmación está sustentada por la evidencia — más un sistema de recuperación,
descomposición y agregación que hace el resto.

Esta tesis **no es una fantasía**; ya tiene pruebas de existencia publicadas:

- **MiniCheck (EMNLP 2024)**: un modelo de 770M parámetros iguala a GPT-4 en fact-checking
  a **400x menos costo**.
- **Distilling Step-by-Step (Google)**: un T5 de 770M supera a PaLM de 540B en tareas
  específicas — una mejora de 700x en tamaño.
- **BitNet b1.58 (Microsoft)**: pesos ternarios {-1, 0, +1} (~1.58 bits/peso) con
  rendimiento competitivo frente a precisión completa, e inferencia en CPU vía `bitnet.cpp`.
- **AVeriTeC 2025**: verificación de afirmaciones del mundo real con LLMs abiertos,
  evidencia web, y veredictos que incluyen *evidencia contradictoria*.
- **Test-time compute (ICLR 2025)**: un modelo pequeño guiado por un **verificador**
  supera a un modelo **14x más grande** con el mismo presupuesto de cómputo.
- **NVIDIA Research (2025)**: *"Small Language Models are the Future of Agentic AI"* —
  SLMs son 10–30x más baratos de servir y más fiables en tareas agénticas repetitivas.

## La verificación como motor de la generación

El núcleo verificador no es solo el producto final — es lo que hace posible **generar
barato con calidad alta**. El patrón: un generador pequeño produce N candidatos
(código, texto, archivos), el verificador los puntúa, y solo sobrevive el que pasa.
Verificar es más fácil que generar; por eso un verificador fuerte convierte a un
generador pequeño en uno grande.

Para código este bucle es *perfecto*, porque la verificación es objetiva: el código o
compila o no, los tests pasan o no, el benchmark da un número. "Código optimizado" deja
de ser una opinión y pasa a ser una medición.

## Lo que AIDAM es (y no es)

| Es | No es |
|---|---|
| Un verificador especializado que supera a los LLMs grandes **en su tarea, por dólar** | Un reemplazo de los LLMs generales |
| Un sistema que cita evidencia para cada veredicto (trazabilidad total) | Un oráculo de la verdad |
| Un agente que dice "no sé" y propone **cómo** averiguarlo | Un modelo que alucina respuestas |
| Un agente que genera código/proyectos/imágenes y **solo entrega lo que pasó verificación** | Un chatbot generalista que compite en todo |
| Software libre, ejecutable en hardware de consumo | Un servicio cerrado en la nube |

## Prueba rápida

```bash
git clone https://github.com/DeliVali/AIDAM.git && cd AIDAM
uv venv --python 3.12
uv pip install -e ".[verificador]"
.venv/bin/aidam verificar "La Torre Eiffel está en París"
```

La primera ejecución descarga el verificador (~1 GB); después todo corre local, en tu
GPU o CPU. Salida: veredicto (**sustentado / refutado / contradictorio / insuficiente**)
con confianza y **citas a la evidencia** de cada fuente consultada.

**Estado actual:** pipeline completo funcionando — descompositor heurístico,
recuperación **multilingüe** (Wikipedia en varios idiomas vía enlaces interlingüísticos
+ búsqueda web), verificador propio entrenado (Fase 1 v0: **88.8% en VitaminC**, desde
73.3% del checkpoint base) que juzga evidencia en cualquier idioma contra afirmaciones
en español, y agregador auditable con independencia de fuentes. Ver el
[roadmap](docs/ROADMAP.md) para lo que viene.

## Documentación

- [Arquitectura del sistema](docs/ARQUITECTURA.md) — los 5 módulos y cómo se conectan
- [Roadmap](docs/ROADMAP.md) — fases con entregables concretos y criterios de éxito
- [Investigación](docs/INVESTIGACION.md) — estado del arte anotado (julio 2026)

## Principios

1. **Parámetros para razonar, no para memorizar.** El conocimiento vive en las fuentes;
   el modelo solo aprende a comparar.
2. **Toda afirmación es descomponible.** Verificamos hechos atómicos, no párrafos.
3. **La verdad no se declara, se mide.** Acuerdo entre fuentes *independientes*, ponderado
   por fiabilidad y frescura.
4. **Saber que no se sabe es una capacidad, no un fallo.** Calibración y abstención son
   métricas de primera clase.
5. **Frontera del conocimiento**: cuando no hay evidencia, el sistema no inventa — genera
   un *plan de verificación* (simulación, cálculo, experimento propuesto).
6. **La eficiencia se mide, no se opina.** Código optimizado = código que pasó tests,
   benchmarks y perfilado. Generación barata = generador pequeño + verificador fuerte,
   nunca un generador grande "porque sí".
7. **La información es libre.** La capacidad de verificar es para todas las personas,
   sin restricciones ni discriminación: el único árbitro aquí es la evidencia, y toda
   evidencia se cita para que cualquiera pueda auditarla. Por eso el proyecto es
   abierto (Apache 2.0), corre en hardware de consumo y no depende de ningún servicio
   cerrado.

## Colaborar

Este proyecto es de todos. Lee la [guía de contribución](CONTRIBUTING.md) — hay tareas
desde fáciles (más fuentes, documentación) hasta investigación (entrenar el verificador
propio). Nos regimos por un [código de conducta](CODE_OF_CONDUCT.md) simple: los
argumentos se pesan por su evidencia, no por quién los dice.

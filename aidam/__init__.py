"""AIDAM — Agente de lógica comparativa.

Verificación de información multi-fuente: descompone afirmaciones en hechos
atómicos, recupera evidencia de fuentes independientes, la juzga con un modelo
pequeño especializado y agrega los veredictos con lógica explícita y auditable.
"""

__version__ = "0.1.0"

from .models import Veredicto, Informe  # noqa: F401

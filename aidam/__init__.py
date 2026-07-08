"""AIDAM — Comparative logic agent.

Multi-source information verification: decomposes claims into atomic facts,
retrieves evidence from independent sources, judges it with a small
specialized model and aggregates the verdicts with explicit, auditable logic.
"""

__version__ = "0.1.0"

from .models import Veredicto, Informe  # noqa: F401

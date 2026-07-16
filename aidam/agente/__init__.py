"""AIDAM agent subsystems.

Modules (all import light — heavy dependencies load lazily inside functions):

- permisos:     deny-first permission engine, four modes, grant asymmetry
- auditoria:    append-only JSONL audit log of every tool call
- sandbox:      bubblewrap-confined command execution (read-only /, no net)
- cola:         resumable SQLite work queue for orchestrated workers
- angulos:      investigation angles (negation, reformulation) — diversity
- orquestador:  investigation-weight cascade (tier-0/1/2, measured signals)
- sintesis:     LLM narrates the aggregated table; it never judges
- herramientas: permission-gated, audited tools for the agent loop
- bucle:        interactive REPL (`aidam agente`)
- voz:          optional local STT/TTS (extra `voz`) — interface only
- vision:       optional OCR + C2PA provenance (extra `imagen`)
- rastreo:      optional tier-2 crawler for JS pages (extra `rastreo`)

Architectural invariants preserved: verdicts come ONLY from the NLI core +
auditable aggregation; LLMs reformulate and narrate, never judge; every
assertion cites evidence; the cascade is NOT the default path (see the
pre-registered gate in docs/AGENT.md).
"""

from __future__ import annotations

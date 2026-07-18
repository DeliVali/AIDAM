"""Test isolation: no test may read or pollute the developer's real agent
memory or data directory.

Found the hard way (2026-07-17): live app use stored Eiffel evidence in
~/.aidam, and tier-0 remembered-evidence investigation started answering the
orquestador tests' claims from it — 3 tests flipped from INSUFICIENTE to
SUSTENTADO depending on what the developer had verified that day. Every test
now gets a throwaway memory and data home.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _memoria_aislada(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDAM_MEMORIA", str(tmp_path / "memoria-prueba.db"))
    monkeypatch.setenv("AIDAM_DATOS", str(tmp_path / "datos-prueba"))

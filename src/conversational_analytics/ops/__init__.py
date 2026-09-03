"""Logica de despliegue/rollback/revert del pipeline de CI/CD (feature 004-ci-cd-pipeline).

Cada modulo es invocable como CLI (`python -m conversational_analytics.ops.<modulo>`) desde los
workflows de `.github/workflows/`, y tambien importable directamente desde los tests (Principio
II de la constitucion: la logica del pipeline se testea igual que la del agente).
"""

from __future__ import annotations

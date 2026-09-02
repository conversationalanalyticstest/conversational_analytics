"""Tests de contrato del agente: no dependen del catálogo de preguntas de referencia.

Cubren FR-002, FR-003, FR-006 y FR-009, según
`specs/003-conversational-agent/contracts/agent-api.md`.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import httpx
import pytest

from conversational_analytics import cortex_analyst
from conversational_analytics.agent import AgentResponse, AgentStatus, ask
from conversational_analytics.telemetry import NullTelemetry


def test_provider_matches_config(agent_answer: Callable[[str], AgentResponse]) -> None:
    """El proveedor y modelo usados coinciden con `LLM_PROVIDER`, sin cruzar credenciales.

    Decision D-08 (revisada): ya no se prohíbe usar OpenAI, se exige que el proveedor
    efectivamente usado coincida con la configuración y quede declarado en la telemetría.
    """
    configured_provider = os.environ.get("LLM_PROVIDER", "openai")
    response = agent_answer("¿Cuáles fueron las ventas netas totales en 2025?")

    assert response.usage.provider == configured_provider
    assert response.usage.model != ""

    if configured_provider == "cortex":
        assert not os.environ.get("OPENAI_API_KEY"), (
            "LLM_PROVIDER=cortex no debe convivir con OPENAI_API_KEY en el entorno "
            "(la credencial del otro proveedor no debe viajar por error, D-08)"
        )


def test_ask_is_stateless() -> None:
    """Dos `ask()` consecutivos no comparten estado (FR-006).

    Se comprueba intercalando una pregunta distinta entre dos invocaciones de la misma
    pregunta: si `ask()` arrastrara memoria entre invocaciones, la segunda podría devolver
    algo distinto por contaminación de la pregunta intercalada.

    La comparación se hace sobre los *valores* de cada fila, no sobre los nombres de
    columna: Cortex Analyst genera SQL libre para esta pregunta (sin verified query que
    la cubra) y puede usar un alias distinto para la misma columna en cada invocación
    (p. ej. `UNITS` vs `UNITS_SOLD`) sin que eso implique contaminación de estado.
    """
    telemetry = NullTelemetry()
    question = "¿Cuál es el país con más unidades vendidas de productos de Animal Health?"

    first = ask(question, telemetry=telemetry, source="test")
    ask(
        "¿Cuáles fueron las ventas netas totales en 2025?",
        telemetry=telemetry,
        source="test",
    )
    second = ask(question, telemetry=telemetry, source="test")

    first_values = [tuple(row.values()) for row in first.rows]
    second_values = [tuple(row.values()) for row in second.rows]
    assert first_values == second_values


def test_no_direct_table_access(agent_answer: Callable[[str], AgentResponse]) -> None:
    """El SQL generado referencia `SV_PHARMA_SALES`, nunca las tablas base (FR-002)."""
    response = agent_answer("¿Cuáles fueron las ventas netas totales en 2025?")
    assert response.sql is not None
    sql_upper = response.sql.upper()

    assert "SV_PHARMA_SALES" in sql_upper or "SEMANTIC_VIEW" in sql_upper
    for forbidden_table in ("DIM_PRODUCT", "DIM_COUNTRY", "FACT_SALES"):
        assert forbidden_table not in sql_upper, (
            f"El SQL generado accede directamente a {forbidden_table}, viola FR-002"
        )


def test_out_of_domain_question() -> None:
    """Una pregunta fuera de dominio da `NO_DATA`, nunca `ERROR` ni una cifra inventada."""
    response = ask(
        "¿Qué tiempo hace hoy?", telemetry=NullTelemetry(), source="test"
    )
    assert response.status == AgentStatus.NO_DATA
    assert response.rows == []


def test_analyst_timeout_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un timeout de Cortex Analyst se traduce en `status == ERROR` (FR-009), no en excepción."""

    def _raise_timeout(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.TimeoutException("timeout forzado por el test")

    monkeypatch.setattr(cortex_analyst.httpx, "post", _raise_timeout)

    response = ask(
        "¿Cuáles fueron las ventas netas totales en 2025?",
        telemetry=NullTelemetry(),
        source="test",
    )

    assert response.status == AgentStatus.ERROR
    assert response.error_message is not None

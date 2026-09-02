"""Verifica que cada invocacion queda registrada en `AGENT_TELEMETRY` (FR-007, Principio IV).

Marcado con `writes_db`: excluir con `-m "not writes_db"` en ejecuciones que no deban escribir
en Snowflake. Usa `SnowflakeTelemetry` real (no `NullTelemetry`), a proposito.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from conversational_analytics.agent import AgentStatus, ask
from conversational_analytics.telemetry import SnowflakeTelemetry

pytestmark = pytest.mark.writes_db


def test_invocation_is_recorded_exactly_once(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Una invocacion inserta exactamente una fila, con los campos minimos de FR-007."""
    telemetry = SnowflakeTelemetry()
    response = ask(
        "¿Cuáles fueron las ventas netas totales en 2025?",
        telemetry=telemetry,
        source="test",
    )

    rows = fetch_all(
        f"""
        SELECT EVENT_ID, QUESTION, ANSWER, GENERATED_SQL, STATUS, ERROR_MESSAGE,
               ROW_COUNT, PROVIDER, MODEL, PROMPT_TOKENS, COMPLETION_TOKENS,
               ESTIMATED_COST, COST_UNIT, LATENCY_MS, FEEDBACK
        FROM CICD_DEMO.DEVOPS.AGENT_TELEMETRY
        WHERE QUESTION = '¿Cuáles fueron las ventas netas totales en 2025?'
        ORDER BY EVENT_TS DESC
        LIMIT 1
        """
    )
    assert len(rows) == 1
    (
        event_id,
        question,
        answer,
        generated_sql,
        status,
        error_message,
        row_count,
        provider,
        model,
        prompt_tokens,
        completion_tokens,
        estimated_cost,
        cost_unit,
        latency_ms,
        feedback,
    ) = rows[0]

    assert event_id is not None
    assert question == "¿Cuáles fueron las ventas netas totales en 2025?"
    assert answer is not None
    assert status == response.status.value

    # Reglas de integridad de data-model.md
    assert status in {"OK", "NO_DATA", "ERROR"}
    assert (error_message is not None) == (status == "ERROR")
    if row_count is not None and row_count > 0:
        assert status == "OK"
    if generated_sql is None:
        assert status != "OK"
    assert feedback in {None, -1, 1}
    assert provider in {"openai", "cortex"}
    assert cost_unit == ("USD" if provider == "openai" else "CREDITS")
    assert prompt_tokens is not None and prompt_tokens >= 0
    assert completion_tokens is not None and completion_tokens >= 0
    assert latency_ms is not None and latency_ms > 0
    assert model


def test_no_data_invocation_is_also_recorded(
    fetch_one: Callable[[str], Any],
) -> None:
    """Un `NO_DATA` (pregunta fuera de rango) tambien se registra, no solo los `OK`."""
    telemetry = SnowflakeTelemetry()
    response = ask("¿Cuánto vendimos en 2021?", telemetry=telemetry, source="test")
    assert response.status == AgentStatus.NO_DATA

    row = fetch_one(
        """
        SELECT STATUS, ROW_COUNT
        FROM CICD_DEMO.DEVOPS.AGENT_TELEMETRY
        WHERE QUESTION = '¿Cuánto vendimos en 2021?'
        ORDER BY EVENT_TS DESC
        LIMIT 1
        """
    )
    assert row is not None
    status, row_count = row
    assert status == "NO_DATA"
    assert not row_count

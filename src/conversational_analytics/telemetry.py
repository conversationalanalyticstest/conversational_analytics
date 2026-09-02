"""Telemetria del agente: protocolo, evento y tarifas de coste.

El registro de cada invocacion va detras de un protocolo (`Telemetry.record`), no con
`INSERT` dispersos por `agent.py` (regla de diseno 3 en plan.md). En tests se inyecta
`NullTelemetry`; la implementacion real contra Snowflake es `SnowflakeTelemetry`
(ver `T026`, mas abajo en este mismo modulo).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelemetryEvent:
    """Una fila de `CICD_DEMO.DEVOPS.AGENT_TELEMETRY`. Ver data-model.md."""

    event_id: str
    source: str
    actor: str
    question: str
    answer: str | None
    generated_sql: str | None
    verified_query_name: str | None
    analyst_request_id: str | None
    sf_query_id: str | None
    row_count: int | None
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: float | None
    cost_unit: str
    latency_ms: int
    status: str
    error_message: str | None
    commit_sha: str | None
    feedback: int | None = None


class Telemetry(Protocol):
    """Protocolo minimo para registrar un evento de invocacion del agente."""

    def record(self, event: TelemetryEvent) -> None: ...


class NullTelemetry:
    """Implementacion no-op. Se usa en tests para no escribir en Snowflake en cada invocacion."""

    def record(self, event: TelemetryEvent) -> None:
        return None


#: Precio por millon de tokens `(entrada, salida)`. Tarifas de referencia, no facturas: no se
#: modela el precio de cache (p.ej. "cached input") por simplicidad (Principio I). Para modelos
#: con un unico precio publicado se repite el mismo valor en ambas posiciones.
OPENAI_PRICE_PER_MTOKEN: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 0.40),
    "gpt-4.1": (2.00, 2.00),
    "gpt-4o-mini": (0.15, 0.15),
    "gpt-4o": (2.50, 2.50),
    "gpt-5.4-mini": (0.75, 4.50),
}

#: Precio en creditos de Snowflake por millon de tokens `(entrada, salida)`. El precio del
#: credito en euros depende del contrato; aqui solo se fija el numero de creditos, no su
#: conversion a moneda.
CORTEX_PRICE_PER_MTOKEN: dict[str, tuple[float, float]] = {
    "openai-gpt-4.1": (4.20, 4.20),
    "openai-gpt-4.1-mini": (0.90, 0.90),
}


def estimated_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> tuple[float | None, str]:
    """Calcula `(coste, unidad)` para un evento de telemetria.

    `coste` es `None` si el modelo no esta en la tabla de tarifas del proveedor: una tarifa
    desconocida no puede tumbar una respuesta correcta (Principio IV).
    """
    if provider == "cortex":
        price_table = CORTEX_PRICE_PER_MTOKEN
        unit = "CREDITS"
    else:
        price_table = OPENAI_PRICE_PER_MTOKEN
        unit = "USD"

    prices = price_table.get(model)
    if prices is None:
        return None, unit

    input_price_per_mtoken, output_price_per_mtoken = prices
    cost = (prompt_tokens / 1_000_000) * input_price_per_mtoken + (
        completion_tokens / 1_000_000
    ) * output_price_per_mtoken
    return cost, unit


class SnowflakeTelemetry:
    """Escribe cada evento en `CICD_DEMO.DEVOPS.AGENT_TELEMETRY`.

    Un fallo al escribir telemetria **no** puede tumbar una respuesta correcta del agente
    (Principio IV): se registra el problema con `logging` y se continua, sin propagar la
    excepcion a quien llamo a `ask()`.
    """

    def record(self, event: TelemetryEvent) -> None:
        # Import local para no obligar a que `db.py` (y por tanto el conector de Snowflake)
        # se cargue solo por importar este modulo, p.ej. desde tests que usan `NullTelemetry`.
        from conversational_analytics.db import get_connection

        try:
            conn = get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO CICD_DEMO.DEVOPS.AGENT_TELEMETRY (
                            EVENT_ID, SOURCE, ACTOR, QUESTION, ANSWER, GENERATED_SQL,
                            VERIFIED_QUERY_NAME, ANALYST_REQUEST_ID, SF_QUERY_ID, ROW_COUNT,
                            PROVIDER, MODEL, PROMPT_TOKENS, COMPLETION_TOKENS,
                            ESTIMATED_COST, COST_UNIT, LATENCY_MS, STATUS, ERROR_MESSAGE,
                            COMMIT_SHA, FEEDBACK
                        ) VALUES (
                            %(event_id)s, %(source)s, %(actor)s, %(question)s, %(answer)s,
                            %(generated_sql)s, %(verified_query_name)s, %(analyst_request_id)s,
                            %(sf_query_id)s, %(row_count)s, %(provider)s, %(model)s,
                            %(prompt_tokens)s, %(completion_tokens)s, %(estimated_cost)s,
                            %(cost_unit)s, %(latency_ms)s, %(status)s, %(error_message)s,
                            %(commit_sha)s, %(feedback)s
                        )
                        """,
                        {
                            "event_id": event.event_id,
                            "source": event.source,
                            "actor": event.actor,
                            "question": event.question,
                            "answer": event.answer,
                            "generated_sql": event.generated_sql,
                            "verified_query_name": event.verified_query_name,
                            "analyst_request_id": event.analyst_request_id,
                            "sf_query_id": event.sf_query_id,
                            "row_count": event.row_count,
                            "provider": event.provider,
                            "model": event.model,
                            "prompt_tokens": event.prompt_tokens,
                            "completion_tokens": event.completion_tokens,
                            "estimated_cost": event.estimated_cost,
                            "cost_unit": event.cost_unit,
                            "latency_ms": event.latency_ms,
                            "status": event.status,
                            "error_message": event.error_message,
                            "commit_sha": event.commit_sha,
                            "feedback": event.feedback,
                        },
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            logger.exception(
                "No se pudo escribir el evento de telemetria %s en Snowflake", event.event_id
            )

"""Agente conversacional sobre `SV_PHARMA_SALES`.

`ask()` es la unica API publica (regla de diseno 1 en plan.md): tests y CLI dependen solo de
su firma, nunca del interior del bucle de tool-calling. Ver
`specs/003-conversational-agent/contracts/agent-api.md` para el contrato completo.
"""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from . import cortex_analyst, llm_provider
from .db import get_connection
from .prompts import SYSTEM_PROMPT
from .telemetry import SnowflakeTelemetry, Telemetry, TelemetryEvent, estimated_cost

#: Limite de filas devueltas al modelo. Q-06 y Q-11 devuelven 12 filas cada una, muy por
#: debajo del limite: no restringe el catalogo, solo evita que una pregunta abierta dispare
#: el consumo de tokens (Principio IV).
MAX_ROWS_TO_MODEL = 100

#: Limite de vueltas del bucle de tool-calling, para no ciclar si el modelo insiste en llamar
#: a la herramienta indefinidamente.
MAX_TOOL_ITERATIONS = 5

#: Schema de la unica herramienta expuesta al modelo. Constante aparte de la funcion (regla
#: de diseno 2 en plan.md): migrar a `openai-agents` (D-02) es anadir `@function_tool` encima
#: de `query_semantic_view` y borrar esta constante.
QUERY_SEMANTIC_VIEW_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "query_semantic_view",
        "description": (
            "Consulta los datos de ventas farmaceuticas (ventas netas y brutas, unidades, "
            "descuentos) por producto, marca, area terapeutica, unidad de negocio, pais, "
            "region, canal y mes. Historico disponible: 2023-2025."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "La pregunta de negocio, autocontenida y en lenguaje natural.",
                }
            },
            "required": ["question"],
        },
    },
}


class AgentStatus(str, Enum):
    """Estados terminales de una invocacion. Ver data-model.md, maquina de estados."""

    OK = "OK"
    NO_DATA = "NO_DATA"
    ERROR = "ERROR"


@dataclass(frozen=True)
class TokenUsage:
    """Tokens consumidos por una invocacion, acumulados en todas las llamadas del bucle."""

    prompt_tokens: int
    completion_tokens: int
    provider: str
    model: str


@dataclass(frozen=True)
class AgentResponse:
    """Valor devuelto por `ask()`."""

    answer: str
    rows: list[dict]
    sql: str | None
    status: AgentStatus
    verified_query_name: str | None
    usage: TokenUsage
    latency_ms: int
    error_message: str | None = None


def query_semantic_view(question: str) -> dict[str, Any]:
    """Herramienta expuesta al modelo: traduce a SQL con Cortex Analyst y lo ejecuta.

    Cortex Analyst genera el SQL pero no lo ejecuta (ver contracts/cortex-endpoints.md); esta
    funcion hace las dos llamadas a Snowflake que hacen falta, en ese orden, para poder
    registrar el SQL antes de ejecutarlo (Principio IV).

    No captura `CortexAnalystError`: un fallo tecnico de Cortex Analyst (timeout, `401`,
    `403`, ...) se deja propagar para que `ask()` lo traduzca en `status=ERROR` (FR-009). Solo
    se trata como "sin datos" el caso en que Cortex Analyst responde con exito pero no genera
    ninguna sentencia SQL (`statement is None`, p.ej. `suggestions`), que no es un fallo.
    """
    analyst_result = cortex_analyst.generate_sql(question)

    if analyst_result.statement is None:
        return {
            "rows": [],
            "sql": None,
            "verified_query_name": analyst_result.verified_query_name,
            "request_id": analyst_result.request_id,
            "sf_query_id": None,
            "note": analyst_result.note
            or "No se pudo generar una consulta SQL para esta pregunta.",
        }

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(analyst_result.statement)
            columns = [col[0] for col in cur.description]
            raw_rows = cur.fetchmany(MAX_ROWS_TO_MODEL)
            sf_query_id = cur.sfqid
    finally:
        conn.close()

    rows = [dict(zip(columns, row, strict=True)) for row in raw_rows]

    # Una consulta agregada sin GROUP BY (SUM/AVG/...) sobre un filtro que no casa ninguna fila
    # sigue devolviendo una fila, con NULL — no cero filas. Sin este chequeo, ask() la marcaria
    # como OK en vez de NO_DATA (FR-005/FR-009).
    if rows and all(value is None for row in rows for value in row.values()):
        rows = []

    note = None
    if not rows:
        note = "La consulta se ejecuto correctamente pero no devolvio filas: no hay datos para esos criterios."

    return {
        "rows": rows,
        "sql": analyst_result.statement,
        "verified_query_name": analyst_result.verified_query_name,
        "request_id": analyst_result.request_id,
        "sf_query_id": sf_query_id,
        "note": note,
    }


def _resolve_actor() -> str:
    """Usuario que dispara la invocacion. En CI, `GITHUB_ACTOR`; en local, el del sistema."""
    return os.environ.get("GITHUB_ACTOR") or getpass.getuser()


def _resolve_commit_sha() -> str | None:
    """Commit del agente que respondio. En CI, `GITHUB_SHA`; en local, `git rev-parse HEAD`."""
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha

    repo_root = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def ask(
    question: str,
    *,
    telemetry: Telemetry | None = None,
    source: str = "cli",
) -> AgentResponse:
    """Responde una pregunta de negocio en lenguaje natural.

    No lanza excepciones por fallos operativos (timeout, `401`, SQL invalido): se traducen en
    `AgentResponse(status=ERROR, ...)`. Si lanza cuando falta configuracion (variables de
    entorno ausentes): eso es un error del programador, no del sistema.

    Es *stateless* (FR-006): dos llamadas consecutivas no comparten nada entre si.
    """
    start = time.perf_counter()
    if telemetry is None:
        telemetry = SnowflakeTelemetry()

    client, provider, model = llm_provider.build_llm_client()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    prompt_tokens = 0
    completion_tokens = 0
    tool_results: list[dict[str, Any]] = []
    final_answer = ""
    error_message: str | None = None

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=[QUERY_SEMANTIC_VIEW_SCHEMA],
            )
            usage = completion.usage
            if usage is not None:
                prompt_tokens += usage.prompt_tokens
                completion_tokens += usage.completion_tokens

            message = completion.choices[0].message
            messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                final_answer = message.content or ""
                break

            for tool_call in message.tool_calls:
                arguments = json.loads(tool_call.function.arguments or "{}")
                tool_result = query_semantic_view(arguments.get("question", question))
                tool_results.append(tool_result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result, default=str),
                    }
                )
        else:
            error_message = "Se alcanzo el limite de iteraciones del bucle de tool-calling"
    except Exception as exc:  # noqa: BLE001 - ask() no propaga fallos operativos al llamante
        error_message = str(exc)

    latency_ms = int((time.perf_counter() - start) * 1000)
    usage_obj = TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        provider=provider,
        model=model,
    )

    # Preguntas comparativas ("compara X e Y") pueden resolverse en varias llamadas a la tool,
    # una por termino de la comparacion: se acumulan las filas de todas, no solo la ultima. Se
    # deduplican filas identicas (mismo contenido exacto) para no contar dos veces cuando el
    # modelo repite la misma consulta en una segunda llamada (autocorreccion/verificacion).
    rows: list[dict[str, Any]] = []
    for tr in tool_results:
        for row in tr.get("rows", []):
            if row not in rows:
                rows.append(row)
    last_result = tool_results[-1] if tool_results else None
    sql = last_result.get("sql") if last_result else None
    verified_query_name = last_result.get("verified_query_name") if last_result else None

    if error_message is not None:
        status = AgentStatus.ERROR
        if not final_answer:
            final_answer = "No se ha podido responder por un fallo tecnico del servicio."
    elif rows:
        status = AgentStatus.OK
    else:
        status = AgentStatus.NO_DATA
        if not final_answer:
            final_answer = "No tengo datos para responder a esa pregunta."

    response = AgentResponse(
        answer=final_answer,
        rows=rows,
        sql=sql,
        status=status,
        verified_query_name=verified_query_name,
        usage=usage_obj,
        latency_ms=latency_ms,
        error_message=error_message,
    )

    cost, cost_unit = estimated_cost(provider, model, prompt_tokens, completion_tokens)
    telemetry.record(
        TelemetryEvent(
            event_id=str(uuid.uuid4()),
            source=source,
            actor=_resolve_actor(),
            question=question,
            answer=response.answer,
            generated_sql=response.sql,
            verified_query_name=response.verified_query_name,
            analyst_request_id=last_result.get("request_id") if last_result else None,
            sf_query_id=last_result.get("sf_query_id") if last_result else None,
            row_count=len(response.rows) or None,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost=cost,
            cost_unit=cost_unit,
            latency_ms=latency_ms,
            status=response.status.value,
            error_message=response.error_message,
            commit_sha=_resolve_commit_sha(),
        )
    )

    return response

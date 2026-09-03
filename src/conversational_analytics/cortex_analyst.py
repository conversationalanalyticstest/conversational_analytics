"""Cliente HTTP de Cortex Analyst.

Traductor de lenguaje natural a SQL sobre la semantic view. Cortex Analyst **no** ejecuta el
SQL que genera: eso es responsabilidad de quien llama (ver `agent.query_semantic_view`).

Es la unica llamada HTTP a mano del proyecto (justificada en la tabla de *Complexity Tracking*
de `specs/003-conversational-agent/plan.md`): el endpoint `/api/v2/cortex/analyst/message` usa
un formato propietario de Snowflake que el SDK de `openai` no puede emitir ni parsear.

Se autentica **siempre** con `SNOWFLAKE_PAT` (sea cual sea `LLM_PROVIDER`, D-03 en
research.md): Cortex Analyst es la unica pieza no negociable de la arquitectura.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

DEFAULT_SEMANTIC_VIEW = "CICD_DEMO.DATA.SV_PHARMA_SALES"
DEFAULT_TIMEOUT = 60.0


class CortexAnalystError(Exception):
    """Fallo tecnico al invocar Cortex Analyst (timeout, 401, 403, 400, servicio caido).

    No se lanza cuando el Analyst no pudo generar SQL para una pregunta ambigua o fuera de
    dominio: ese caso es `AnalystResult` con `statement=None` y `note` relleno, no un error
    (ver data-model.md, maquina de estados de `AgentStatus`).
    """


@dataclass(frozen=True)
class AnalystResult:
    """Resultado de `generate_sql`. El SQL, si lo hay, no esta ejecutado."""

    statement: str | None
    verified_query_name: str | None
    request_id: str | None
    warnings: list[str]
    note: str | None = None


def _account_host() -> str:
    account = os.environ["SNOWFLAKE_ACCOUNT"]
    return f"https://{account}.snowflakecomputing.com"


def _resolve_semantic_view() -> str:
    """Resuelve la semantic view a consultar.

    Precedencia (ver contracts/semantic-view-versioning.md, ADR-003):
    1. `SNOWFLAKE_SEMANTIC_VIEW` en el entorno, si esta definida (override explicito para
       desarrollo local y tests).
    2. Si no: `DEFAULT_SEMANTIC_VIEW`. La semantic view es un unico objeto fisico, actualizado
       siempre in place (`CREATE OR ALTER SEMANTIC VIEW`), sin mecanismo de versionado propio
       en Snowflake.
    """
    return os.environ.get("SNOWFLAKE_SEMANTIC_VIEW") or DEFAULT_SEMANTIC_VIEW


def generate_sql(question: str, *, timeout: float = DEFAULT_TIMEOUT) -> AnalystResult:
    """Traduce una pregunta en lenguaje natural a SQL usando Cortex Analyst.

    Args:
        question: pregunta autocontenida, en lenguaje natural.
        timeout: segundos antes de abortar la peticion. Configurable para poder forzar un
            timeout en tests (ver `test_analyst_timeout_returns_error`).

    Returns:
        `AnalystResult` con el SQL generado (sin ejecutar), o con `statement=None` y `note`
        relleno si el Analyst no pudo generar SQL (pregunta ambigua o fuera de dominio).

    Raises:
        CortexAnalystError: timeout, o la API REST devuelve 401/403/400/otro fallo de servicio.
    """
    semantic_view = _resolve_semantic_view()
    url = f"{_account_host()}/api/v2/cortex/analyst/message"
    headers = {
        "Authorization": f"Bearer {os.environ['SNOWFLAKE_PAT']}",
        "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
        "Content-Type": "application/json",
    }
    payload = {
        "semantic_view": semantic_view,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": question}]},
        ],
    }

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise CortexAnalystError(
            f"timeout: Cortex Analyst no respondio en {timeout}s"
        ) from exc

    if response.status_code == 401:
        raise CortexAnalystError("401: SNOWFLAKE_PAT invalido o caducado")
    if response.status_code == 403:
        raise CortexAnalystError(
            "403: falta SNOWFLAKE.CORTEX_USER en el rol por defecto del usuario "
            "(ver specs/003-conversational-agent/research.md, D-04)"
        )
    if response.status_code == 400:
        raise CortexAnalystError(
            "400: semantic view inexistente, mal formada o sin permisos"
        )
    if response.status_code >= 400:
        raise CortexAnalystError(
            f"{response.status_code}: fallo de servicio de Cortex Analyst"
        )

    body = response.json()
    request_id = body.get("request_id")
    warnings = list(body.get("warnings") or [])

    statement: str | None = None
    verified_query_name: str | None = None
    note: str | None = None

    for block in body.get("message", {}).get("content", []):
        block_type = block.get("type")
        if block_type == "sql":
            statement = block.get("statement")
            confidence = block.get("confidence") or {}
            verified_query = confidence.get("verified_query_used") or {}
            verified_query_name = verified_query.get("name")
        elif block_type == "suggestions":
            note = (
                "Cortex Analyst no pudo generar una consulta SQL para esta pregunta: "
                "es ambigua o esta fuera del dominio de datos disponible."
            )

    return AnalystResult(
        statement=statement,
        verified_query_name=verified_query_name,
        request_id=request_id,
        warnings=warnings,
        note=note,
    )

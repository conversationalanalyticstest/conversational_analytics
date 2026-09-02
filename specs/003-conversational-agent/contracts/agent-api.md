# Contrato: API pública del agente

**Feature**: `003-conversational-agent` | **Fecha**: 2026-09-01 | **Fase**: 1

Este fichero fija **la única frontera pública** de la feature. Tests, CLI y cualquier consumidor
futuro dependen exclusivamente de lo que hay aquí, nunca del interior del bucle de tool-calling.
Es lo que hace que una migración futura a `openai-agents` (D-02) sea local.

## Superficie pública

```python
# src/conversational_analytics/agent.py

def ask(
    question: str,
    *,
    telemetry: Telemetry | None = None,
    source: str = "cli",
) -> AgentResponse: ...
```

| Parámetro | Obligatorio | Descripción |
|---|---|---|
| `question` | sí | Pregunta en lenguaje natural (español o inglés, FR-001) |
| `telemetry` | no | Implementación de `Telemetry`. Por defecto `SnowflakeTelemetry`; en tests se inyecta `NullTelemetry` |
| `source` | no | Se registra en `AGENT_TELEMETRY.SOURCE`: `cli` / `test` / `ci` |

**`ask()` no lanza excepciones por fallos operativos.** Un timeout, un `401` o un SQL inválido se
traducen en `AgentResponse(status=ERROR, ...)`. Sí lanza si falta configuración (variables de
entorno ausentes), porque eso es un error del programador, no del sistema.

**`ask()` es *stateless*** (FR-006): dos llamadas consecutivas no comparten absolutamente nada. No
hay parámetro `session_id` y no debe añadirse en esta feature.

## Tipos devueltos

```python
class AgentStatus(str, Enum):
    OK = "OK"
    NO_DATA = "NO_DATA"
    ERROR = "ERROR"


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    provider: str
    model: str


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    rows: list[dict]
    sql: str | None
    status: AgentStatus
    verified_query_name: str | None
    usage: TokenUsage
    latency_ms: int
    error_message: str | None = None
```

Campos y reglas de validación: ver [data-model.md](../data-model.md).

## Contrato de la herramienta expuesta al modelo

Regla de diseño vinculante: **la tool es una función Python normal**, sin decoradores, y su schema
vive en una constante aparte.

```python
# src/conversational_analytics/agent.py

QUERY_SEMANTIC_VIEW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "query_semantic_view",
        "description": (
            "Consulta los datos de ventas farmacéuticas (ventas netas y brutas, unidades, "
            "descuentos) por producto, marca, área terapéutica, unidad de negocio, país, "
            "región, canal y mes. Histórico disponible: 2023-2025."
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


def query_semantic_view(question: str) -> dict: ...
```

Valor devuelto por la función (lo que se serializa como mensaje `role="tool"`):

| Clave | Tipo | Descripción |
|---|---|---|
| `rows` | `list[dict]` | Filas del SQL ya ejecutado. Vacía si no hay datos |
| `sql` | `str \| None` | SQL generado por Cortex Analyst |
| `verified_query_name` | `str \| None` | `AI_VERIFIED_QUERY` usada, si la hubo |
| `request_id` | `str \| None` | Id de la petición al Analyst |
| `sf_query_id` | `str \| None` | `sfqid` de la ejecución en Snowflake |
| `note` | `str \| None` | Texto para el modelo cuando no hay datos o la pregunta es ambigua |

**Se limita el número de filas devueltas al modelo** (constante `MAX_ROWS_TO_MODEL = 100`). Q-11
devuelve 12 filas y Q-06 otras 12, así que el límite no afecta al catálogo, pero evita que una
pregunta abierta dispare el consumo de tokens (Principio IV).

## Contrato del CLI

```text
python -m conversational_analytics.cli "¿Cuáles fueron las ventas netas totales en 2025?"
python -m conversational_analytics.cli --verbose "..."
```

| | |
|---|---|
| Salida estándar | La respuesta en lenguaje natural |
| Con `--verbose` | Añade SQL generado, estado, verified query usada, tokens y latencia |
| Código de salida `0` | `status` es `OK` o `NO_DATA` |
| Código de salida `1` | `status` es `ERROR` |

`NO_DATA` sale con código `0` a propósito: "no hay datos para 2021" es una respuesta correcta del
sistema, no un fallo.

## Suite de evaluación (Principio II)

`tests/test_agent_evaluation.py` — se escribe **antes** que `agent.py` (FR-010).

Fuente de verdad de las preguntas:
[reference-questions.md](../../001-mock-sales-dataset/contracts/reference-questions.md).
Esta feature **no añade preguntas nuevas**.

Los asserts van sobre `AgentResponse.rows`, comparando **contra el valor exacto de la consulta
baseline determinista** ya existente en `tests/test_reference_questions.py` (feature 001), no un
umbral débil ni la prosa de `answer` (decisión D-07 revisada — resuelve el hallazgo de que "un
número positivo cualquiera" pasaba el test).

| # | `status` esperado | Assert sobre `rows` | Assert sobre `answer` |
|---|---|---|---|
| Q-01 | `OK` | 1 fila, valor == baseline (ventas netas 2025) | no vacía |
| Q-02 | `OK` | 1 fila, valor == baseline (unidades Respiralia Alemania 2024) | no vacía |
| Q-03 | `OK` | 5 filas == top-5 baseline, mismo orden descendente | no vacía |
| Q-04 | `OK` | 2 filas, valores == baseline por unidad de negocio | no vacía |
| Q-05 | `OK` | filas == baseline (área terapéutica de mayor crecimiento) | no vacía |
| Q-06 | `OK` | 12 filas, una por mes, cada valor == baseline mensual | no vacía |
| Q-07 | `OK` | filas == baseline (ratio descuento/bruto) | no vacía |
| Q-08 | `OK` | 4 filas, valores == baseline por región | no vacía |
| Q-09 | `OK` | filas == baseline (unidades por canal) | no vacía |
| Q-10 | `OK` | 1 fila, valor == baseline | no vacía |
| Q-11 | `OK` | 12 filas == baseline mensual, todas presentes | no vacía |
| Q-12 | `NO_DATA` | vacía | contiene expresión de ausencia de datos; `rows == []` es la comprobación real de "sin cifra inventada" (no un regex sobre el texto) |

Asserts transversales, aplicables a todos los casos:

- `status != ERROR`;
- ningún valor numérico es `NaN` ni `None`;
- si `status == OK`, entonces `sql is not None` y el SQL es ejecutable (lo demuestra el hecho de
  que hay filas);
- `usage.prompt_tokens > 0` y `latency_ms > 0`;
- `usage.provider` coincide con `LLM_PROVIDER` configurado en el entorno de test.

## Tests de contrato

`tests/test_agent_contract.py` — no dependen del catálogo de preguntas.

| Test | Qué verifica | Requisito |
|---|---|---|
| `test_provider_matches_config` | El proveedor y modelo usados coinciden con `LLM_PROVIDER`, y no viaja al proveedor equivocado la credencial del otro (D-08) | FR-003, Restricción Tecnológica |
| `test_ask_is_stateless` | Dos `ask()` seguidos: el segundo no resuelve una referencia al primero | FR-006 |
| `test_out_of_domain_question` | "¿Qué tiempo hace hoy?" → `NO_DATA`, no `ERROR` ni cifra inventada | Edge case, SC-002 |
| `test_analyst_timeout_returns_error` | Con timeout forzado a 0 → `status == ERROR` y mensaje de fallo de servicio | FR-009 |
| `test_no_direct_table_access` | El SQL generado referencia `SV_PHARMA_SALES`, no las tablas base | FR-002 |

## Trazabilidad

| Requisito | Cubierto por |
|---|---|
| FR-001 | `ask()` + CLI |
| FR-002 | `test_no_direct_table_access` |
| FR-003 | `test_provider_matches_config` + `llm_provider.build_llm_client()` |
| FR-004 | Q-01..Q-11 de la suite de evaluación, contra baseline exacto |
| FR-005 | Q-12 + `test_out_of_domain_question` |
| FR-006 | `test_ask_is_stateless` |
| FR-007 | `test_telemetry.py` |
| FR-008 | Reutilización de `db.py`; credenciales por proveedor vía `llm_provider.py` |
| FR-009 | `test_analyst_timeout_returns_error` |
| FR-010 | Orden de tareas en `tasks.md` |

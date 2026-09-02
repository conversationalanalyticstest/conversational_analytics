# Data Model: Agente conversacional

**Feature**: `003-conversational-agent` | **Fecha**: 2026-09-01 | **Fase**: 1

Entidades derivadas de la sección *Key Entities* de [spec.md](./spec.md). Esta feature **no crea
ni modifica ninguna tabla de negocio**: `DIM_PRODUCT`, `DIM_COUNTRY`, `FACT_SALES` y
`SV_PHARMA_SALES` se consumen tal cual. La única entidad persistida es el registro de invocación.

## Vista general

```text
Question (entrada, transitoria)
   │
   ▼
AgentResponse (salida en memoria)
   ├── answer      texto redactado
   ├── rows        filas del SQL ejecutado   ← sobre esto asertan los tests
   ├── sql         SQL generado por Analyst
   └── status      OK | NO_DATA | ERROR
   │
   ▼
TelemetryEvent (persistido)  ──> CICD_DEMO.DEVOPS.AGENT_TELEMETRY
```

## Entidades en memoria

### `Question`

No es una clase: es el `str` que recibe `ask()`. No lleva estado de conversaciones anteriores
(FR-006). Se documenta aquí sólo para dejar constancia de que **no** hay entidad `Conversation`
ni `Session` en esta feature (ver D-09).

### `AgentResponse`

Valor devuelto por `ask()`. Estructura inmutable (`dataclass(frozen=True)`).

| Campo | Tipo | Descripción | Regla de validación |
|---|---|---|---|
| `answer` | `str` | Respuesta en lenguaje natural | No vacía cuando `status != ERROR` |
| `rows` | `list[dict]` | Filas devueltas al ejecutar `sql` | Vacía si y sólo si `status != OK` |
| `sql` | `str \| None` | SQL generado por Cortex Analyst | `None` sólo si Analyst no llegó a generar SQL |
| `status` | `AgentStatus` | `OK` / `NO_DATA` / `ERROR` | Ver máquina de estados |
| `verified_query_name` | `str \| None` | Nombre de la `AI_VERIFIED_QUERY` usada, si la hubo | `None` = el Analyst improvisó el SQL |
| `usage` | `TokenUsage` | Tokens de entrada y salida | Ambos `>= 0` |
| `latency_ms` | `int` | Duración total de `ask()` | `> 0` |
| `error_message` | `str \| None` | Detalle técnico | No `None` si y sólo si `status == ERROR` |

### `AgentStatus` — máquina de estados

Estados terminales; una invocación acaba siempre en exactamente uno.

| Estado | Cuándo | Origen de la señal |
|---|---|---|
| `OK` | Se generó SQL, se ejecutó y devolvió ≥ 1 fila | ejecución del SQL |
| `NO_DATA` | La pregunta es válida pero no hay datos, o el Analyst la considera ambigua / fuera de dominio | 0 filas, o `content[].type == "suggestions"` |
| `ERROR` | Fallo técnico: timeout, `401`, `403`, SQL inválido, servicio caído | excepción capturada |

Reglas:

- `NO_DATA` **no** es un error: cubre US2 / FR-005 y es el estado esperado de Q-12.
- El caso "pregunta fuera de dominio" (p. ej. "¿qué tiempo hace?") cae en `NO_DATA`, no en
  `ERROR`, porque el sistema funcionó correctamente: simplemente no aplica.
- Ninguna ruta puede terminar sin registrar telemetría, tampoco `ERROR` (US3, escenario 2).

### `TokenUsage`

| Campo | Tipo | Origen |
|---|---|---|
| `prompt_tokens` | `int` | `usage.prompt_tokens` de la respuesta de chat completions |
| `completion_tokens` | `int` | `usage.completion_tokens` |
| `provider` | `str` | valor efectivo de `LLM_PROVIDER` (`openai` \| `cortex`) |
| `model` | `str` | valor efectivo de `OPENAI_MODEL` o `CORTEX_MODEL`, según `provider` |

Se acumula a lo largo de **todas** las llamadas al modelo de una misma invocación (el bucle de
tool-calling hace al menos dos), no sólo de la última. Registrar sólo la última infravaloraría el
coste, que es justo lo que el Principio IV quiere evitar.

## Entidad persistida

### `TelemetryEvent` → `CICD_DEMO.DEVOPS.AGENT_TELEMETRY`

Una fila por invocación de `ask()`. DDL completo en
[contracts/telemetry-table.md](./contracts/telemetry-table.md).

| Columna | Tipo | Obligatorio | Origen | Principio IV |
|---|---|---|---|---|
| `EVENT_ID` | `STRING` | sí | UUID generado en cliente | — |
| `EVENT_TS` | `TIMESTAMP_NTZ` | sí | `CURRENT_TIMESTAMP()` al insertar | timestamp |
| `SOURCE` | `STRING` | sí | `cli` / `test` / `ci` | origen |
| `ACTOR` | `STRING` | sí | usuario del sistema o `CURRENT_USER()` | origen |
| `QUESTION` | `STRING` | sí | input de `ask()` | pregunta |
| `ANSWER` | `STRING` | no | `AgentResponse.answer` | respuesta |
| `GENERATED_SQL` | `STRING` | no | `AgentResponse.sql` | SQL generado |
| `VERIFIED_QUERY_NAME` | `STRING` | no | `confidence.verified_query_used.name` | corrección |
| `ANALYST_REQUEST_ID` | `STRING` | no | `request_id` de Cortex Analyst | trazabilidad |
| `SF_QUERY_ID` | `STRING` | no | `cursor.sfqid` | trazabilidad |
| `ROW_COUNT` | `NUMBER` | no | `len(rows)` | — |
| `PROVIDER` | `STRING` | sí | `LLM_PROVIDER` efectivo (`openai` \| `cortex`) | proveedor |
| `MODEL` | `STRING` | sí | `TokenUsage.model` efectivo | — |
| `PROMPT_TOKENS` | `NUMBER` | sí | `TokenUsage.prompt_tokens` | tokens entrada |
| `COMPLETION_TOKENS` | `NUMBER` | sí | `TokenUsage.completion_tokens` | tokens salida |
| `ESTIMATED_COST` | `FLOAT` | no | calculado (ver abajo) | coste estimado |
| `COST_UNIT` | `STRING` | sí | `'USD'` si `PROVIDER='openai'`, `'CREDITS'` si `PROVIDER='cortex'` | unidad del coste |
| `LATENCY_MS` | `NUMBER` | sí | cronómetro alrededor de `ask()` | latencia |
| `STATUS` | `STRING` | sí | `AgentStatus` | estado |
| `ERROR_MESSAGE` | `STRING` | no | `AgentResponse.error_message` | estado |
| `COMMIT_SHA` | `STRING` | no | `GITHUB_SHA`, o `git rev-parse HEAD` en local | versión del agente |
| `FEEDBACK` | `NUMBER` | no | `+1` / `-1`, se rellena después | corrección |

**Reglas de integridad** (validadas en `test_telemetry.py`, no por constraints de Snowflake):

- `STATUS ∈ {'OK','NO_DATA','ERROR'}`.
- `ERROR_MESSAGE IS NOT NULL` ⟺ `STATUS = 'ERROR'`.
- `ROW_COUNT > 0` ⟹ `STATUS = 'OK'`.
- `GENERATED_SQL IS NULL` ⟹ `STATUS ≠ 'OK'`.
- `FEEDBACK ∈ {-1, 1, NULL}`.
- `PROVIDER ∈ {'openai','cortex'}` y `COST_UNIT` es coherente con `PROVIDER` (`'USD'` ⟺ `'openai'`,
  `'CREDITS'` ⟺ `'cortex'`).

**Sin claves foráneas.** Es una tabla de eventos, append-only; no se actualiza salvo la columna
`FEEDBACK`.

### Cálculo de `ESTIMATED_COST`

Se calcula en Python, no en SQL, y se guarda ya resuelto en la fila. Motivo: el precio depende del
modelo y del proveedor, y guardar el coste congelado al momento de la invocación evita que un
cambio futuro de tarifas reescriba la historia.

```text
ESTIMATED_COST = (PROMPT_TOKENS + COMPLETION_TOKENS) / 1_000_000 * PRICE_PER_MTOKEN[PROVIDER][MODEL]
```

`PRICE_PER_MTOKEN` es una constante en `telemetry.py`, con dos tablas de tarifas separadas: una en
**USD** (precios públicos de OpenAI por modelo) y otra en **créditos de Snowflake** (para cuando
`LLM_PROVIDER=cortex`; el precio del crédito en euros depende del contrato). `COST_UNIT` deja
explícito con cuál se calculó cada fila, para que no se sumen valores en unidades distintas por
error. Si el modelo no está en la tabla correspondiente, se registra `NULL` en vez de fallar la
invocación — una tarifa desconocida no puede tumbar una respuesta correcta.

### Vista `V_AGENT_ACTIVITY`

Responde a las tres preguntas que exige el Principio IV. Definición en
[contracts/telemetry-table.md](./contracts/telemetry-table.md).

| Pregunta del Principio IV | Columnas que la responden |
|---|---|
| ¿Qué se ha preguntado? | `EVENT_TS`, `ACTOR`, `QUESTION`, `ANSWER` |
| ¿Cuánto ha costado? | `PROVIDER`, `MODEL`, `PROMPT_TOKENS`, `COMPLETION_TOKENS`, `ESTIMATED_COST`, `COST_UNIT`, `LATENCY_MS` |
| ¿Fue correcta la respuesta? | `STATUS`, `USED_VERIFIED_QUERY`, `FEEDBACK` |

Donde `USED_VERIFIED_QUERY := VERIFIED_QUERY_NAME IS NOT NULL`. Es un *proxy* de calidad, no una
prueba: significa que Cortex Analyst resolvió la pregunta con una de las consultas verificadas de
la feature 002. **Hoy siempre es `FALSE`** por un defecto conocido de esas verified queries (ver
research.md D-06); no indica que las respuestas sean incorrectas.

## Trazabilidad con la spec

| Entidad de la spec | Realización |
|---|---|
| Pregunta | parámetro `str` de `ask()` |
| Respuesta | `AgentResponse` (`answer` + `rows`) |
| Registro de invocación | `TelemetryEvent` → `AGENT_TELEMETRY` |

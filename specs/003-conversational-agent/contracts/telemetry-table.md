# Contrato: tabla de telemetría

**Feature**: `003-conversational-agent` | **Fecha**: 2026-09-01 | **Fase**: 1

DDL de destino para `snowflake/005_telemetry.sql`. Cubre el Principio IV y FR-007.

Sigue el patrón de las features 001 y 002: script numerado, idempotente, desplegable desde Git,
nada creado a mano en la consola (Principio III).

## Prerrequisito: grants que faltan

El esquema `CICD_DEMO.DEVOPS` ya existe desde `001_bootstrap.sql` y `CICD_DEMO_ROLE` tiene `USAGE`
sobre él, pero **no puede crear objetos dentro**. Hay que añadir a `001_bootstrap.sql`, en la
sección 6:

```sql
GRANT CREATE TABLE, CREATE VIEW
ON SCHEMA CICD_DEMO.DEVOPS
TO ROLE CICD_DEMO_ROLE;
```

Sin esto, `005_telemetry.sql` falla en el primer despliegue limpio.

## `AGENT_TELEMETRY`

Tabla de eventos, append-only. Una fila por invocación de `ask()`, incluidas las que terminan en
`NO_DATA` o `ERROR`.

```sql
USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DEVOPS;

CREATE TABLE IF NOT EXISTS AGENT_TELEMETRY (
    EVENT_ID             STRING        NOT NULL,
    EVENT_TS             TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    SOURCE               STRING        NOT NULL,
    ACTOR                STRING        NOT NULL,
    QUESTION             STRING        NOT NULL,
    ANSWER               STRING,
    GENERATED_SQL        STRING,
    VERIFIED_QUERY_NAME  STRING,
    ANALYST_REQUEST_ID   STRING,
    SF_QUERY_ID          STRING,
    ROW_COUNT            NUMBER,
    PROVIDER              STRING        NOT NULL,
    MODEL                 STRING        NOT NULL,
    PROMPT_TOKENS         NUMBER        NOT NULL,
    COMPLETION_TOKENS     NUMBER        NOT NULL,
    ESTIMATED_COST        FLOAT,
    COST_UNIT             STRING        NOT NULL,
    LATENCY_MS           NUMBER        NOT NULL,
    STATUS               STRING        NOT NULL,
    ERROR_MESSAGE        STRING,
    COMMIT_SHA           STRING,
    FEEDBACK             NUMBER
)
COMMENT = 'Un evento por invocacion del agente conversacional. Principio IV de la constitucion.';
```

Decisiones de diseño:

- **`CREATE TABLE IF NOT EXISTS`**, no `CREATE OR REPLACE`: el histórico de telemetría no se puede
  perder en cada despliegue. Es la misma lógica de idempotencia que llevó a `CREATE OR ALTER` en la
  semantic view, aplicada a una tabla con datos.
- **Sin constraints ni claves foráneas.** Snowflake no los impone de todas formas; las reglas de
  integridad se validan en `tests/test_telemetry.py` (listadas en
  [data-model.md](../data-model.md)).
- **`ESTIMATED_COST` admite `NULL`**: si el modelo no está en la tabla de tarifas, se registra
  `NULL`. Una tarifa desconocida no puede tumbar una respuesta correcta.
- **`FEEDBACK` es la única columna que se actualiza** después de la inserción.

## `V_AGENT_ACTIVITY`

Responde a las tres preguntas que el Principio IV exige que sean respondibles.

```sql
CREATE OR REPLACE VIEW V_AGENT_ACTIVITY
COMMENT = 'Que se ha preguntado, cuanto ha costado y si la respuesta fue correcta.'
AS
SELECT
    EVENT_TS,
    SOURCE,
    ACTOR,
    QUESTION,
    ANSWER,
    STATUS,
    VERIFIED_QUERY_NAME IS NOT NULL  AS USED_VERIFIED_QUERY,
    FEEDBACK,
    PROMPT_TOKENS,
    COMPLETION_TOKENS,
    PROMPT_TOKENS + COMPLETION_TOKENS AS TOTAL_TOKENS,
    ESTIMATED_COST,
    COST_UNIT,
    LATENCY_MS,
    PROVIDER,
    MODEL,
    COMMIT_SHA,
    GENERATED_SQL,
    SF_QUERY_ID
FROM AGENT_TELEMETRY;
```

`CREATE OR REPLACE` aquí sí, porque una vista no tiene datos que perder.

## Consultas de demostración

Van al `README.md` de `snowflake/`: son lo que se enseña en directo para probar que el Principio IV
no es una promesa.

**Qué se ha preguntado hoy**

```sql
SELECT EVENT_TS, ACTOR, QUESTION, STATUS, USED_VERIFIED_QUERY
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
WHERE EVENT_TS >= DATEADD(day, -1, CURRENT_TIMESTAMP())
ORDER BY EVENT_TS DESC;
```

**Cuánto ha costado, por proveedor y modelo**

```sql
SELECT PROVIDER,
       MODEL,
       COST_UNIT,
       COUNT(*)              AS INVOCATIONS,
       SUM(TOTAL_TOKENS)     AS TOKENS,
       ROUND(SUM(ESTIMATED_COST), 4) AS COST,
       ROUND(AVG(LATENCY_MS))        AS AVG_LATENCY_MS
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
GROUP BY PROVIDER, MODEL, COST_UNIT;
```

**Señal de calidad: porcentaje resuelto con consultas verificadas** — hoy siempre `0%` hasta que se
corrijan las `AI_VERIFIED_QUERIES` de la feature 002 (ver research.md D-06); no indica respuestas
incorrectas.

```sql
SELECT STATUS,
       COUNT(*) AS N,
       ROUND(100.0 * SUM(IFF(USED_VERIFIED_QUERY, 1, 0)) / COUNT(*), 1) AS PCT_VERIFIED
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
GROUP BY STATUS;
```

**Delta de coste entre dos versiones del agente** — es lo que exige el Principio IV antes de
fusionar un cambio que suba el consumo de tokens.

```sql
SELECT COMMIT_SHA,
       COUNT(*)          AS INVOCATIONS,
       AVG(TOTAL_TOKENS) AS AVG_TOKENS
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
WHERE SOURCE IN ('ci', 'test')
GROUP BY COMMIT_SHA
ORDER BY MIN(EVENT_TS) DESC;
```

## Complemento nativo, no sustituto

`SNOWFLAKE.ACCOUNT_USAGE` ofrece consumo agregado de Cortex a nivel de cuenta. Es útil para
contrastar que `ESTIMATED_COST` no se desvía de la realidad, pero **no sustituye a esta tabla**:
tiene latencia de actualización y no contiene la pregunta, la respuesta ni el commit SHA. Se
menciona aquí para que nadie proponga eliminar `AGENT_TELEMETRY` por duplicidad.

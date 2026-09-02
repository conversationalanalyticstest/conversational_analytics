# SQL de Snowflake

Todo el estado de Snowflake vive aquí y se versiona en Git (Principio III de la
[constitución](../.specify/memory/constitution.md): nada se aplica a mano en la consola).

## Scripts numerados

Se ejecutan en orden. Deben ser **idempotentes** y no contener datos de una cuenta concreta.

| Fichero | Qué hace |
|---|---|
| [001_bootstrap.sql](001_bootstrap.sql) | Rol, base de datos, schemas y grants base |
| [002_tables.sql](002_tables.sql) | Estructura del dataset mock: `DIM_PRODUCT`, `DIM_COUNTRY` y `FACT_SALES` |
| [003_seed.sql](003_seed.sql) | Carga del dataset mock: 12 productos, 10 países y 12.960 ventas mensuales, generadas de forma determinista |
| [004_semantic_view.sql](004_semantic_view.sql) | Semantic view `SV_PHARMA_SALES` para Cortex Analyst (`CREATE OR ALTER SEMANTIC VIEW`) |
| [005_telemetry.sql](005_telemetry.sql) | Tabla `AGENT_TELEMETRY` y vista `V_AGENT_ACTIVITY` para el agente conversacional (feature 003) |

## Scripts manuales (`manual/`)

Fuera de la secuencia numerada porque **dependen del entorno o de la persona**. No los ejecuta
el pipeline.

| Fichero | Qué hace |
|---|---|
| [manual/grant_user.sql](manual/grant_user.sql) | Da `CICD_DEMO_ROLE` a un usuario y fija su contexto por defecto |

## Orden de puesta en marcha

1. Ejecutar `001_bootstrap.sql` como `ACCOUNTADMIN`.
2. Editar `manual/grant_user.sql` con tu usuario y ejecutarlo.
3. Crear un PAT restringido al rol de la demo y rellenar `.env` a partir de `.env.example`
   (`SNOWFLAKE_PAT`, `SNOWFLAKE_ROLE=CICD_DEMO_ROLE`, `SNOWFLAKE_DATABASE=CICD_DEMO`).
4. Guardar **el mismo** PAT en `pat.txt` en la raíz del repositorio y registrar la conexión
   `cicd_demo` de la CLI apuntando a ese fichero (ver
   [quickstart.md](../specs/001-mock-sales-dataset/quickstart.md)).
5. Desplegar el dataset y la semantic view:
   ```powershell
   snow sql --connection cicd_demo -f snowflake/002_tables.sql
   snow sql --connection cicd_demo -f snowflake/003_seed.sql
   snow sql --connection cicd_demo -f snowflake/004_semantic_view.sql
   ```
6. Feature 003 (agente conversacional) añadió un `GRANT` nuevo en la sección 6 de
   `001_bootstrap.sql` (`CREATE TABLE, CREATE VIEW` sobre el schema `DEVOPS`). **Hay que
   volver a ejecutar `001_bootstrap.sql` como `ACCOUNTADMIN`** antes de desplegar
   `005_telemetry.sql`; el PAT restringido a `CICD_DEMO_ROLE` no puede hacer
   `USE ROLE ACCOUNTADMIN` y por tanto no vale para este paso. Después:
   ```powershell
   snow sql --connection cicd_demo -f snowflake/005_telemetry.sql
   ```

> ⚠️ **El PAT vive en dos ficheros**: `.env` (lo lee `pytest`) y `pat.txt` (lo lee `snow`). Los
> dos están en `.gitignore` y contienen el secreto en texto plano. **Al rotarlo, actualiza los
> dos.** Es una excepción consciente al Principio V de la constitución, justificada en
> [plan.md](../specs/001-mock-sales-dataset/plan.md#complexity-tracking).

## Validar

```powershell
poetry run pytest -v
```

Los tests marcados con `writes_db` **recargan datos** en Snowflake (comprueban que el seed es
idempotente). Para dejarlos fuera:

```powershell
poetry run pytest -v -m "not writes_db"
```

Guía completa en
[specs/001-mock-sales-dataset/quickstart.md](../specs/001-mock-sales-dataset/quickstart.md).

## Telemetría del agente conversacional

`005_telemetry.sql` crea `AGENT_TELEMETRY` (append-only, una fila por invocación de `ask()`,
incluidas las de `NO_DATA`/`ERROR`) y la vista `V_AGENT_ACTIVITY`. Detalle del contrato en
[contracts/telemetry-table.md](../specs/003-conversational-agent/contracts/telemetry-table.md).

**Qué se ha preguntado hoy**

```sql
SELECT EVENT_TS, ACTOR, QUESTION, STATUS, USED_VERIFIED_QUERY
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
WHERE EVENT_TS >= DATEADD(day, -1, CURRENT_TIMESTAMP())
ORDER BY EVENT_TS DESC;
```

**Cuánto ha costado, por proveedor y modelo** — agrupar siempre por `COST_UNIT`: OpenAI factura
en USD y Cortex en créditos, y sumarlos sin distinguir la unidad daría un número sin sentido.

```sql
SELECT PROVIDER,
       MODEL,
       COST_UNIT,
       COUNT(*)                      AS INVOCATIONS,
       SUM(TOTAL_TOKENS)             AS TOKENS,
       ROUND(SUM(ESTIMATED_COST), 4) AS COST,
       ROUND(AVG(LATENCY_MS))        AS AVG_LATENCY_MS
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
GROUP BY PROVIDER, MODEL, COST_UNIT;
```

**Señal de calidad: porcentaje resuelto con consultas verificadas**

```sql
SELECT STATUS,
       COUNT(*) AS N,
       ROUND(100.0 * SUM(IFF(USED_VERIFIED_QUERY, 1, 0)) / COUNT(*), 1) AS PCT_VERIFIED
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
GROUP BY STATUS;
```

**Delta de coste entre dos versiones del agente**

```sql
SELECT COMMIT_SHA,
       COUNT(*)          AS INVOCATIONS,
       AVG(TOTAL_TOKENS) AS AVG_TOKENS
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
WHERE SOURCE IN ('ci', 'test')
GROUP BY COMMIT_SHA
ORDER BY MIN(EVENT_TS) DESC;
```

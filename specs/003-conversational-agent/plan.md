# Implementation Plan: Agente conversacional sobre la semantic view de ventas

**Branch**: `003-conversational-agent` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-conversational-agent/spec.md`

## Summary

Un agente de un solo turno que recibe una pregunta en español, la responde en lenguaje natural
y deja rastro de lo que ha hecho.

El punto no obvio de esta feature es que **Snowflake expone dos endpoints de Cortex distintos y
hacen falta los dos**:

| Endpoint | Formato | Rol en esta feature |
|---|---|---|
| `/api/v2/cortex/v1/chat/completions` | compatible OpenAI | **orquestador**: decide llamar a la herramienta y redacta la respuesta final |
| `/api/v2/cortex/analyst/message` | propietario Snowflake | **traductor**: pregunta → SQL sobre `SV_PHARMA_SALES` |

El SDK de OpenAI sólo puede hablar con el primero, y el primero no conoce la semantic view. El
puente es una función Python `query_semantic_view(question)` que se expone al modelo como
*tool*: cuando el modelo la invoca, la función llama a Cortex Analyst por HTTP, obtiene el SQL
generado, lo **ejecuta** con `db.py` (Cortex Analyst genera SQL pero no lo ejecuta) y devuelve
las filas al modelo, que redacta la respuesta.

Se implementa con el SDK **`openai`** y un bucle de *tool-calling* escrito a mano (~40 líneas
visibles en el repo), no con el framework `openai-agents`. Ver [research.md](./research.md),
decisión D-02.

Flujo completo:

```text
pregunta
  └─> agent.ask()
        └─> openai SDK ──> /cortex/v1/chat/completions   (modelo decide)
              └─> tool query_semantic_view()
                    ├─> POST /cortex/analyst/message      (genera SQL)
                    └─> db.py execute(sql)                (ejecuta SQL)
              └─> openai SDK ──> /cortex/v1/chat/completions (redacta)
        └─> telemetry.record()  ──> CICD_DEMO.DEVOPS.AGENT_TELEMETRY
  respuesta
```

## Technical Context

**Language/Version**: Python (`>=3.11,<3.15`; el venv local es 3.14.6). Sin cambios en el rango
declarado en `pyproject.toml`.

**Primary Dependencies**:

- `openai` (**nueva**) — cliente del endpoint de chat completions de Cortex. Obligatoria por la
  Restricción Tecnológica de la constitución ("SDK de OpenAI apuntando al endpoint de Cortex").
- `httpx` (**nueva, declarada explícitamente**) — cliente HTTP para el endpoint de Cortex
  Analyst, que el SDK de OpenAI no sabe consumir. Ya entra como dependencia transitiva de
  `openai`; se declara para no depender del árbol de otro paquete.
- `snowflake-connector-python`, `python-dotenv` — ya presentes, sin cambios.
- **NO** se añade `openai-agents`. Ver decisión D-02.

**Storage**: Snowflake. Tabla nueva `CICD_DEMO.DEVOPS.AGENT_TELEMETRY` más la vista
`V_AGENT_ACTIVITY` (Principio IV). El esquema `DEVOPS` ya existe desde `001_bootstrap.sql`,
pero **no tiene `GRANT CREATE TABLE`**: hay que añadirlo.

**Testing**: `pytest` contra la cuenta real de Snowflake, extendiendo las fixtures de
`tests/conftest.py`. Los asserts de evaluación van contra **las filas devueltas por el SQL**, no
contra la prosa del modelo (ver decisión D-07).

**Target Platform**: Snowflake (cuenta `GNTUAOQ-YO01002`, rol `CICD_DEMO_ROLE`, warehouse
`COMPUTE_WH`, base `CICD_DEMO`).

**Project Type**: Single project — librería Python en `src/conversational_analytics/` más un CLI
mínimo como canal de invocación (FR-001).

**Performance Goals**: No hay objetivo duro de latencia; sí un **timeout explícito** por llamada
(60 s a Cortex Analyst, 60 s al modelo) para cubrir el edge case de "Cortex no responde"
(FR-009). La latencia se **mide y registra**, no se optimiza.

**Constraints**:

- `OPENAI_API_KEY` MUST NOT ser necesaria ni utilizada. Hay un test que lo verifica.
- Stateless de un solo turno: sin historial entre invocaciones (FR-006, Principio I).
- Acceso a datos **exclusivamente** vía `SV_PHARMA_SALES`; el agente no construye SQL a mano ni
  toca `DIM_PRODUCT` / `DIM_COUNTRY` / `FACT_SALES` directamente (FR-002).
- El flujo completo debe poder explicarse en menos de cinco minutos (SC-004, Principio I).

**Scale/Scope**: 5 módulos Python nuevos (~350 líneas en total), 1 herramienta expuesta al
modelo, 1 tabla y 1 vista de telemetría, 12 casos de evaluación.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principio I — Simplicidad Orientada a la Demo (NON-NEGOTIABLE)

**PASA, con justificación escrita** (exigida por el propio principio para toda dependencia nueva):

| Elemento | Justificación |
|---|---|
| Dependencia `openai` | La impone la Restricción Tecnológica de la constitución. No es una elección. |
| Dependencia `httpx` | El SDK de OpenAI no puede consumir el endpoint de Cortex Analyst. Sin un cliente HTTP no hay acceso a la semantic view, que es el valor entero de la feature 002. Alternativa rechazada: `requests` (añadiría un árbol de dependencias que `openai` no trae ya). |
| `openai-agents` **rechazada** | Aporta un `Runner` que sustituye ~40 líneas de bucle, pero las oculta justo en el punto que la demo tiene que enseñar, y sus *defaults* apuntan a OpenAI (riesgo de fuga). Ver D-02. |
| 5 módulos en vez de 1 fichero | Cada módulo mapea 1:1 con una caja del diagrama de flujo. Un único fichero sería más corto pero mezclaría cuatro responsabilidades y haría la migración futura a `openai-agents` global en vez de local. |

Stateless de un solo turno: cumplido (FR-006). El multi-turno queda documentado como evolución
en [research.md](./research.md) (D-09), **no se implementa**.

### Principio II — Evaluación del Agente como Test (NON-NEGOTIABLE)

**PASA**. Las 12 preguntas de
[reference-questions.md](../001-mock-sales-dataset/contracts/reference-questions.md) son la
suite. Los tests se escriben **antes** que `agent.py` (FR-010), y el orden queda fijado en
`tasks.md`. Los asserts son explícitos por pregunta y se aplican sobre las filas del SQL
ejecutado, que son deterministas, en vez de sobre el texto redactado, que no lo es (D-07).

### Principio III — CI/CD Es el Producto

**PASA con alcance limitado, sin violación**. Esta feature **no** monta el pipeline de GitHub
Actions (queda para una feature posterior). Lo que sí cumple aquí y ahora:

- El *system prompt* vive en `src/conversational_analytics/prompts.py`, versionado en Git. Es un
  artefacto desplegable, no una cadena incrustada en medio de la lógica.
- La tabla de telemetría se despliega con `snowflake/005_telemetry.sql`, siguiendo el patrón
  numerado e idempotente de las features 001 y 002. Nada se crea a mano en la consola.
- Cada registro de telemetría lleva el **commit SHA** (`COMMIT_SHA`), que es lo que ata la
  respuesta del agente a la versión desplegada.

### Principio IV — Observabilidad y Control de Coste

**PASA**. `AGENT_TELEMETRY` cubre los campos mínimos del principio (timestamp, origen, pregunta,
SQL, respuesta, tokens in/out, coste estimado, latencia, estado, commit SHA) y la vista
`V_AGENT_ACTIVITY` responde a las tres preguntas que exige: qué se ha preguntado, cuánto ha
costado y si la respuesta fue correcta. Para la tercera se usan dos señales:
`VERIFIED_QUERY_NAME` (gratis, la devuelve Cortex Analyst en runtime) y `FEEDBACK` (manual).
Ver [data-model.md](./data-model.md) y D-06.

### Principio V — Reproducibilidad y Gestión de Secretos

**PASA**. Dos variables de entorno nuevas (`CORTEX_MODEL`, `SNOWFLAKE_SEMANTIC_VIEW`), ambas con
valor por defecto y documentadas en `.env.example`. **Sin credenciales nuevas**: el mismo
`SNOWFLAKE_PAT` que ya usa `db.py` autentica los dos endpoints de Cortex. No hay ningún secreto
de OpenAI que gestionar, que es precisamente lo que verifica el test anti-fuga.

### Re-check post-diseño (Fase 1)

Reevaluado tras generar `research.md`, `data-model.md`, `contracts/` y `quickstart.md`.

| Principio | Antes | Después | Comentario |
|---|---|---|---|
| I Simplicidad | PASA | **PASA** | El diseño no ha crecido: siguen siendo 5 módulos, 1 tool y 1 tabla. El guion de demo de [quickstart.md](./quickstart.md) recorre el flujo con un fichero por paso, que es la prueba de SC-004. |
| II Evaluación como test | PASA | **PASA** | La matriz de asserts por pregunta está fijada en [contracts/agent-api.md](./contracts/agent-api.md), y con ella la tabla de trazabilidad FR → test. |
| III CI/CD | PASA (alcance limitado) | **PASA** | Sin cambios. `005_telemetry.sql` sigue el patrón numerado idempotente; `COMMIT_SHA` queda en cada fila. |
| IV Observabilidad | PASA | **PASA** | El diseño añade dos señales que no estaban previstas y salen gratis: `VERIFIED_QUERY_NAME` (¿acertó una consulta verificada de la 002?) y `SF_QUERY_ID` (cruce con `QUERY_HISTORY`). |
| V Reproducibilidad | PASA | **PASA** | Confirmado: cero credenciales nuevas. |

Sin violaciones nuevas. La tabla de *Complexity Tracking* no cambia.

**Un riesgo de despliegue detectado durante el diseño** (no es una violación, pero sí un fallo
seguro si se ignora): `CICD_DEMO_ROLE` tiene `USAGE` sobre el esquema `DEVOPS` pero **no
`CREATE TABLE`**. Hay que ampliar `001_bootstrap.sql` antes de desplegar `005_telemetry.sql`.
Detalle en [research.md](./research.md), D-04.

## Project Structure

### Documentation (this feature)

```text
specs/003-conversational-agent/
├── plan.md              # Este fichero
├── research.md          # Fase 0 — decisiones D-01..D-10
├── data-model.md        # Fase 1 — entidades y esquema de telemetría
├── quickstart.md        # Fase 1 — cómo ejecutarlo y validarlo
├── contracts/
│   ├── agent-api.md         # ask() / AgentResponse / suite de evaluación
│   ├── cortex-endpoints.md  # request/response de los dos endpoints de Cortex
│   └── telemetry-table.md   # DDL de AGENT_TELEMETRY y V_AGENT_ACTIVITY
├── checklists/
│   └── requirements.md  # Fase 1 (ya existente)
└── tasks.md             # Fase 3 — NO lo genera speckit-plan
```

### Source Code (repository root)

```text
src/conversational_analytics/
├── __init__.py           # existente
├── db.py                 # existente — sin cambios
├── prompts.py            # NUEVO — system prompt versionado
├── cortex_analyst.py     # NUEVO — cliente HTTP de /cortex/analyst/message
├── agent.py              # NUEVO — ask(), bucle de tool-calling, tool query_semantic_view
├── telemetry.py          # NUEVO — protocolo Telemetry + SnowflakeTelemetry + NullTelemetry
└── cli.py                # NUEVO — canal de invocación (FR-001)

tests/
├── conftest.py               # existente — se añaden fixtures del agente
├── test_connection.py        # existente
├── test_dataset.py           # existente
├── test_reference_questions.py  # existente
├── test_semantic_view.py     # existente
├── test_agent_evaluation.py  # NUEVO — Q-01..Q-12 (Principio II)
├── test_agent_contract.py    # NUEVO — stateless, anti-fuga OPENAI_API_KEY, errores
└── test_telemetry.py         # NUEVO — el registro se escribe y tiene los campos mínimos

snowflake/
├── 001_bootstrap.sql     # MODIFICAR — GRANT CREATE TABLE, CREATE VIEW ON SCHEMA DEVOPS
└── 005_telemetry.sql     # NUEVO — AGENT_TELEMETRY + V_AGENT_ACTIVITY
```

**Structure Decision**: Single project. Se mantiene el paquete `src/conversational_analytics/`
que ya existe y se le añaden cuatro módulos más el CLI. Cada módulo corresponde a una caja del
diagrama del *Summary*, para que la explicación de cinco minutos (SC-004) sea "un fichero por
paso". `db.py` no se toca: la ejecución del SQL generado reutiliza `get_connection()` tal cual.

### Reglas de diseño (frontera de migración)

Estas tres reglas no cuestan nada hoy y hacen que un cambio futuro a `openai-agents` (D-02) sea
local en vez de global. Son **vinculantes** para la implementación:

1. **`ask()` es la única API pública.** Tests y CLI dependen sólo de su firma, nunca del interior
   del bucle.
2. **La *tool* es una función Python normal**, sin decoradores propios; su JSON schema vive en
   una constante aparte. Migrar significa añadir `@function_tool` y borrar la constante.
3. **La telemetría va detrás de un protocolo** (`Telemetry.record(event)`), no con `INSERT`
   dispersos. En tests se inyecta `NullTelemetry`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Llamada HTTP directa a Cortex Analyst, fuera del SDK de OpenAI | `/api/v2/cortex/analyst/message` usa un formato propietario que el SDK de OpenAI no puede emitir ni parsear, y es el único endpoint que consume `SV_PHARMA_SALES`. Sin él, la feature 002 no aporta nada al agente. | Usar sólo `/cortex/v1/chat/completions` obligaría al modelo a escribir SQL a mano contra las tablas base, lo que viola FR-002 y desperdicia las `AI_VERIFIED_QUERIES`. |
| Dos llamadas a Snowflake por invocación (generar SQL + ejecutarlo) | Cortex Analyst devuelve el `statement` pero no lo ejecuta. La ejecución es responsabilidad del cliente. | No hay alternativa: no existe un modo "genera y ejecuta" en el endpoint. Y separarlo es lo que permite registrar el SQL antes de ejecutarlo (Principio IV). |

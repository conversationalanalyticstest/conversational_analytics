---

description: "Task list template for feature implementation"
---

# Tasks: Agente conversacional sobre la semantic view de ventas

**Input**: Documentos de diseño de `specs/003-conversational-agent/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Incluidos y **obligatorios**. FR-010 exige que la suite de evaluación se escriba
**antes** de la implementación, y el Principio II de la constitución lo eleva a innegociable. El
orden tests → implementación está impuesto dentro de cada fase de historia de usuario, no es una
recomendación.

**Organization**: Agrupadas por historia de usuario para poder entregar cada una de forma
independiente. US1 es el MVP: con las fases 1-3 hay un agente que responde preguntas. US2 añade
el comportamiento ante ausencia de datos y US3 la telemetría, sin tocar la API pública.

**Arquitectura (constitución v2.0.0, decisión D-11)**: el orquestador es *proveedor-agnóstico* —
`llm_provider.build_llm_client()` decide entre la API pública de OpenAI (`LLM_PROVIDER=openai`,
valor por defecto porque la cuenta Snowflake de esta demo es trial sin inferencia Cortex) y el
endpoint de chat completions de Cortex (`LLM_PROVIDER=cortex`, alternativa para cuando una cuenta
de pago lo habilite). Cortex Analyst traduce siempre la pregunta a SQL, sin excepción, sea cual
sea `LLM_PROVIDER`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: A qué historia de usuario pertenece (US1, US2, US3)
- Cada tarea incluye la ruta de fichero exacta

## Path Conventions

Proyecto único (ver "Project Structure" en [plan.md](./plan.md)):

- `src/conversational_analytics/` — código del agente, incluido el nuevo `llm_provider.py`
- `tests/` — suite de evaluación y de contrato
- `snowflake/` — DDL desplegable
- `db.py` **no se modifica**: se reutiliza `get_connection()` tal cual

---

## Phase 1: Setup

**Purpose**: Dejar el entorno en condiciones y **verificar empíricamente** que el proveedor por
defecto (OpenAI público) funciona de punta a punta, antes de escribir una sola línea de agente.

- [X] T001 Añadir `openai` y `httpx` a `pyproject.toml` con `poetry add openai httpx` y regenerar
      `poetry.lock`. Verificar que instalan en el venv de Python 3.14 (esta máquina no tiene
      compilador C: si alguna dependencia transitiva no trae wheel, recrear el venv con
      `poetry env use 3.12`, que sigue dentro de `requires-python`). Hecho cuando
      `.venv\Scripts\python.exe -c "import openai, httpx"` no falla.
- [X] T002 [P] Documentar en `.env.example` las variables nuevas: `LLM_PROVIDER` (opcional,
      defecto `openai`), `OPENAI_API_KEY` (obligatoria si `LLM_PROVIDER=openai`, el caso por
      defecto), `OPENAI_MODEL` (opcional, defecto `gpt-4.1-mini`), `CORTEX_MODEL` (opcional, se
      fija tras verificar en T004) y `SNOWFLAKE_SEMANTIC_VIEW` (opcional, defecto
      `CICD_DEMO.DATA.SV_PHARMA_SALES`). Comentario explícito de que `OPENAI_API_KEY` sólo se lee
      con `LLM_PROVIDER=openai` (Restricción Tecnológica de la constitución, v2.0.0).
- [X] T003 Verificar el rol por defecto del usuario (D-04): ejecutar
      `SHOW USERS LIKE 'CONVERSATIONALANALYTICSTEST';` y comprobar que `default_role` es
      `CICD_DEMO_ROLE`. Si no lo es, añadir
      `ALTER USER CONVERSATIONALANALYTICSTEST SET DEFAULT_ROLE = CICD_DEMO_ROLE;` a
      `snowflake/manual/grant_user.sql` y ejecutarlo. Hecho cuando el rol por defecto tiene
      `SNOWFLAKE.CORTEX_USER` por herencia. Bloquea Cortex Analyst (siempre necesario) y, si se
      usa `LLM_PROVIDER=cortex`, también al orquestador: sin esto la API REST devuelve `403`
      aunque el conector funcione.
- [X] T004 Verificar el proveedor por defecto (`LLM_PROVIDER=openai`, D-11): con una
      `OPENAI_API_KEY` real, confirmar mediante una llamada mínima a
      `client.chat.completions.create(...)` (SDK `openai`, sin `base_url` propio) que
      `OPENAI_MODEL=gpt-4.1-mini` responde y que **devuelve `tool_calls`** al pasarle un `tools`
      de prueba. De paso, intentar la misma prueba contra
      `/api/v2/cortex/v1/chat/completions` para un modelo candidato (D-05): si la cuenta no tiene
      entitlement (caso conocido en esta cuenta trial), documentarlo y dejar `CORTEX_MODEL` sin
      fijar. Hecho cuando D-05 y D-11 en [research.md](./research.md) quedan actualizadas con la
      evidencia y la fecha.

**Checkpoint**: dependencias instaladas, permisos correctos y el proveedor por defecto (OpenAI)
confirmado que soporta *function calling*.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Las piezas que todas las historias necesitan: el prompt, el cliente de Cortex Analyst,
la abstracción de proveedor, los tipos públicos y la telemetría *nula*. La implementación real de
telemetría es de US3; aquí sólo se crea la interfaz para que `ask()` tenga su firma definitiva
desde el principio.

**⚠️ CRITICAL**: Ninguna tarea de las fases 3-5 puede empezar hasta completar esta fase.

- [X] T005 [P] Crear `src/conversational_analytics/prompts.py` con la constante `SYSTEM_PROMPT`:
      el agente responde en español, usa **siempre** la herramienta para obtener datos, no inventa
      cifras nunca, y si la herramienta no devuelve filas lo dice explícitamente. Docstring de
      módulo indicando que es un artefacto desplegable versionado (Principio III), no una cadena
      auxiliar.
- [X] T006 [P] Crear `src/conversational_analytics/cortex_analyst.py`: cliente `httpx` de
      `/api/v2/cortex/analyst/message` según
      [contracts/cortex-endpoints.md](./contracts/cortex-endpoints.md). Función
      `generate_sql(question: str) -> AnalystResult` con las cabeceras `Authorization: Bearer` y
      `X-Snowflake-Authorization-Token-Type: PROGRAMMATIC_ACCESS_TOKEN`, autenticando **siempre**
      con `SNOWFLAKE_PAT` (sea cual sea `LLM_PROVIDER`), `timeout=60`, y el parseo de
      `message.content[]` extrayendo `statement`, `confidence.verified_query_used.name`,
      `request_id` y `warnings`. En esta fase sólo la ruta feliz; el mapa de errores es T020.
- [X] T007 [P] Crear `src/conversational_analytics/llm_provider.py` con `build_llm_client() ->
      tuple[OpenAI, str, str]` (D-11): lee `LLM_PROVIDER` (defecto `openai`); si `openai`,
      construye `OpenAI(api_key=OPENAI_API_KEY)` y usa `OPENAI_MODEL` (defecto `gpt-4.1-mini`); si
      `cortex`, construye `OpenAI(api_key=SNOWFLAKE_PAT, base_url=".../api/v2/cortex/v1")` y usa
      `CORTEX_MODEL`. Es el **único** punto del código que decide el proveedor — `agent.py` sólo
      consume la tupla devuelta, según [contracts/cortex-endpoints.md](./contracts/cortex-endpoints.md).
- [X] T008 [P] Crear `src/conversational_analytics/telemetry.py` con el `Protocol` `Telemetry`
      (método `record(event: TelemetryEvent) -> None`), la dataclass `TelemetryEvent` con las 21
      columnas de [data-model.md](./data-model.md) (incluidas `PROVIDER` y `COST_UNIT`),
      `NullTelemetry` (no-op, para tests) y dos diccionarios de tarifas —
      `OPENAI_PRICE_PER_MTOKEN` (USD) y `CORTEX_PRICE_PER_MTOKEN` (créditos) — más la función
      `estimated_cost(provider, model, prompt_tokens, completion_tokens) -> tuple[float | None,
      str]` que devuelve `(coste, unidad)`, con coste `None` si el modelo no está en la tabla
      correspondiente, sin lanzar. `SnowflakeTelemetry` **no** se implementa aquí: es T027.
- [X] T009 Crear `src/conversational_analytics/agent.py` con **sólo** los tipos públicos del
      contrato: `AgentStatus` (`OK`/`NO_DATA`/`ERROR`), `TokenUsage` (con el campo `provider`) y
      `AgentResponse` (`@dataclass(frozen=True)`), tal y como los fija
      [contracts/agent-api.md](./contracts/agent-api.md). Sin lógica todavía.
- [X] T010 Añadir a `tests/conftest.py` las fixtures del agente, reutilizando las existentes sin
      modificarlas: `null_telemetry` (devuelve `NullTelemetry()`) y `agent_answer`, una fixture de
      ámbito sesión que invoca `ask(question, telemetry=NullTelemetry(), source="test")` y
      **cachea la respuesta por pregunta** para no pagar dos veces la misma invocación entre
      módulos de test (control de coste, Principio IV).

**Checkpoint**: existen los tipos, el prompt, el cliente del Analyst y la abstracción de
proveedor. `ask()` todavía no.

---

## Phase 3: User Story 1 - Responder una pregunta de negocio en lenguaje natural (Priority: P1) 🎯 MVP

**Goal**: Que una pregunta en español devuelva una respuesta en lenguaje natural con el dato
correcto, obtenido de `SV_PHARMA_SALES`.

**Independent Test**: Invocar el agente con Q-01..Q-11 y comprobar que las filas devueltas cumplen
la aserción del catálogo de referencia. No requiere telemetría ni manejo de ausencia de datos.

### Tests (ANTES de la implementación — FR-010, Principio II)

- [X] T011 [US1] Crear `tests/test_agent_evaluation.py` con los casos Q-01 a Q-11 según la matriz
      de [contracts/agent-api.md](./contracts/agent-api.md). Asserts sobre `AgentResponse.rows`
      comparados contra el valor exacto de la consulta baseline ya existente en
      `tests/test_reference_questions.py` (decision D-07 revisada, no un umbral debil ni la
      prosa de `answer`); mas los asserts transversales
      (`status != ERROR`, sin `NaN`/`None`, `sql is not None`, `usage.prompt_tokens > 0`,
      `latency_ms > 0`, `usage.provider` coincide con `LLM_PROVIDER` configurado). Las
      preguntas se toman literalmente de
      [reference-questions.md](../001-mock-sales-dataset/contracts/reference-questions.md). Hecho
      cuando los 11 tests **fallan** por `ImportError`/`AttributeError` de `ask`.
- [X] T012 [P] [US1] Crear `tests/test_agent_contract.py` con `test_provider_matches_config`
      (verifica que el proveedor y modelo usados coinciden con `LLM_PROVIDER`, sin cruzar la
      credencial del otro proveedor, D-08),
      `test_ask_is_stateless` (dos `ask()` seguidos; el segundo no resuelve una referencia al
      primero — FR-006) y `test_no_direct_table_access` (el SQL generado referencia
      `SV_PHARMA_SALES` y no `DIM_PRODUCT`/`DIM_COUNTRY`/`FACT_SALES` — FR-002). Deben fallar.

### Implementación

- [X] T013 [US1] En `src/conversational_analytics/agent.py`: constante
      `QUERY_SEMANTIC_VIEW_SCHEMA` (JSON schema, en una constante aparte por la regla de diseño 2
      del plan) y función `query_semantic_view(question: str) -> dict` — función Python normal,
      **sin decoradores**. Llama a `cortex_analyst.generate_sql()`, ejecuta el `statement` con
      `db.get_connection()`, devuelve `rows` (como `list[dict]`, truncado a
      `MAX_ROWS_TO_MODEL = 100`), `sql`, `verified_query_name`, `request_id` y `sf_query_id`
      (`cursor.sfqid`).
- [X] T014 [US1] En `src/conversational_analytics/agent.py`: obtener `(client, provider, model)`
      de `llm_provider.build_llm_client()` (T007) e implementar
      `ask(question, *, telemetry=None, source="cli") -> AgentResponse` con el bucle de
      *tool-calling* explícito (límite de iteraciones para no ciclar), **acumulando `usage` de
      todas las llamadas al modelo**, no sólo de la última, guardando `provider`/`model` en el
      `TokenUsage` devuelto. Devuelve `status=OK` cuando hay filas. El bucle debe quedar legible:
      es lo que se enseña en la demo (SC-004).
- [X] T015 [US1] Crear `src/conversational_analytics/cli.py` con `argparse`: pregunta posicional,
      `--verbose` (SQL generado, verified query, estado, tokens, latencia, proveedor y modelo) y
      `--check` (verifica el proveedor configurado y el endpoint de Cortex Analyst, paso 4 de
      [quickstart.md](./quickstart.md)). Códigos de
      salida `0` para `OK`/`NO_DATA` y `1` para `ERROR`, según
      [contracts/agent-api.md](./contracts/agent-api.md).
- [ ] T016 [US1] Ejecutar `.venv\Scripts\python.exe -m pytest tests/test_agent_evaluation.py -v`
      y dejar Q-01..Q-11 en verde, más los tres tests de T012. Hecho cuando `--check` responde OK
      y el CLI contesta Q-01 con un número igual al baseline.

**Checkpoint**: MVP entregable. El agente responde preguntas de negocio de punta a punta.

---

## Phase 4: User Story 2 - Recibir un aviso claro cuando no hay datos (Priority: P2)

**Goal**: Que una pregunta fuera de rango, ambigua o fuera de dominio produzca un mensaje explícito
de ausencia de datos, y que un fallo de servicio produzca un error controlado.

**Independent Test**: Enviar Q-12 y comprobar `status == NO_DATA`, `rows` vacío y una respuesta sin
ninguna cifra inventada.

### Tests (ANTES de la implementación)

- [X] T017 [US2] Añadir el caso Q-12 a `tests/test_agent_evaluation.py`: `status == NO_DATA`,
      `rows` vacía (comprobación real de "sin cifra inventada", no un regex sobre `answer`), y
      `answer` expresa ausencia de datos. Debe fallar mientras `ask()` no distinga `NO_DATA`.
- [X] T018 [P] [US2] Añadir a `tests/test_agent_contract.py`: `test_out_of_domain_question`
      ("¿Qué tiempo hace hoy?" → `NO_DATA`, no `ERROR` ni cifra inventada) y
      `test_analyst_timeout_returns_error` (timeout forzado → `status == ERROR` con mensaje de
      fallo de servicio, FR-009).

### Implementación

- [X] T019 [US2] En `src/conversational_analytics/cortex_analyst.py`: implementar el mapa de
      errores completo de [contracts/cortex-endpoints.md](./contracts/cortex-endpoints.md) —
      `timeout`, `401`, `403`, `400`, y el bloque `content[].type == "suggestions"` como señal de
      "no se pudo generar SQL", que **no** es un error. Registrar `warnings[]` cuando no esté
      vacío. Hacer el timeout configurable para que T018 pueda forzarlo.
- [X] T020 [US2] En `src/conversational_analytics/agent.py`: derivar `AgentStatus` según la
      máquina de estados de [data-model.md](./data-model.md) (`NO_DATA` para cero filas o
      `suggestions`; `ERROR` sólo para fallos técnicos, sea cual sea el proveedor — un `401` de
      `OPENAI_API_KEY` inválida o un `403` de entitlement de Cortex son igual de `ERROR`),
      devolver la clave `note` a la herramienta
      para que el modelo redacte la ausencia de datos, y capturar toda excepción operativa dentro
      de `ask()` — no se propaga ninguna al llamante. Reforzar en `prompts.py` la instrucción de
      no inventar cifras cuando la herramienta no devuelva filas.
- [ ] T021 [US2] Ejecutar Q-12 y los dos tests de contrato nuevos, y dejarlos en verde sin haber
      roto Q-01..Q-11.

**Checkpoint**: el agente ya no alucina ni revienta. US1 + US2 son la demo defendible.

---

## Phase 5: User Story 3 - Trazar cada pregunta para poder auditarla (Priority: P3)

**Goal**: Que toda invocación quede registrada en Snowflake, incluidas las de `NO_DATA` y `ERROR`.

**Independent Test**: Invocar el agente una vez y comprobar por SQL que existe la fila
correspondiente con los campos mínimos de FR-007.

### Tests (ANTES de la implementación)

- [X] T022 [US3] Crear `tests/test_telemetry.py`, marcado con `writes_db` (marker ya existente en
      `pyproject.toml`): verifica que una invocación inserta exactamente una fila; que están los
      campos mínimos de FR-007; y las reglas de integridad de
      [data-model.md](./data-model.md) (`STATUS` en el enum, `ERROR_MESSAGE` no nulo ⟺ `ERROR`,
      `ROW_COUNT > 0` ⟹ `OK`, `GENERATED_SQL` nulo ⟹ no `OK`, `FEEDBACK` en `{-1,1,NULL}`,
      `PROVIDER` en `{'openai','cortex'}` y `COST_UNIT` coherente con `PROVIDER`).
      Incluye un caso `NO_DATA` para comprobar que también se registra.

### Implementación

- [X] T023 [US3] Modificar `snowflake/001_bootstrap.sql`, sección 6: añadir
      `GRANT CREATE TABLE, CREATE VIEW ON SCHEMA CICD_DEMO.DEVOPS TO ROLE CICD_DEMO_ROLE;`.
      Sin esto T025 falla (D-04).
- [X] T024 [US3] Crear `snowflake/005_telemetry.sql` con `AGENT_TELEMETRY`
      (`CREATE TABLE IF NOT EXISTS`, **nunca** `CREATE OR REPLACE`: el histórico no se puede
      perder, incluidas las columnas `PROVIDER` y `COST_UNIT`) y `V_AGENT_ACTIVITY`
      (`CREATE OR REPLACE`), copiando el DDL de
      [contracts/telemetry-table.md](./contracts/telemetry-table.md) y siguiendo la cabecera de
      estilo de `snowflake/004_semantic_view.sql`.
- [X] T025 [US3] Desplegar `001_bootstrap.sql` (requiere `ACCOUNTADMIN`) y `005_telemetry.sql` con
      `snow sql -f ... -c cicd_demo` desde la raíz del repo. Verificar con
      `SELECT COUNT(*) FROM CICD_DEMO.DEVOPS.AGENT_TELEMETRY;` y que `V_AGENT_ACTIVITY` resuelve.
      (2026-09-02: ambos desplegados, `V_AGENT_ACTIVITY` resuelve.)
- [X] T026 [US3] En `src/conversational_analytics/telemetry.py`: implementar `SnowflakeTelemetry`
      con el `INSERT` parametrizado en `CICD_DEMO.DEVOPS.AGENT_TELEMETRY`, resolviendo
      `COMMIT_SHA` desde `GITHUB_SHA` o `git rev-parse HEAD`, `ACTOR` desde el usuario del sistema,
      y `ESTIMATED_COST`/`COST_UNIT` con `estimated_cost()` de T008 (usa
      `OPENAI_PRICE_PER_MTOKEN` o `CORTEX_PRICE_PER_MTOKEN` según `PROVIDER`). Un fallo al
      escribir telemetría **no** puede tumbar una respuesta correcta: se registra el problema y
      se sigue.
- [X] T027 [US3] En `src/conversational_analytics/agent.py`: instrumentar `ask()` para construir
      el `TelemetryEvent` (incluidos `PROVIDER` y `COST_UNIT`) y llamar a `telemetry.record()` en
      **todas** las rutas de salida, también en `ERROR` (US3, escenario 2). Poner
      `SnowflakeTelemetry` como valor por defecto cuando el parámetro `telemetry` es `None`.
- [X] T028 [US3] Ejecutar `tests/test_telemetry.py` en verde y validar SC-003 con la consulta del
      paso 7 de [quickstart.md](./quickstart.md): tras la suite de evaluación debe haber una fila
      por invocación, incluidas las `NO_DATA`.
      (2026-09-02: `tests/test_telemetry.py` — 2 passed. `V_AGENT_ACTIVITY` muestra una fila `OK`
      y una `NO_DATA`, ambas con `USED_VERIFIED_QUERY`, tokens y latencia.)

**Checkpoint**: las tres historias completas. El Principio IV deja de ser una promesa.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T029 [P] Añadir a `snowflake/README.md` la sección de telemetría con las consultas de
      demostración de [contracts/telemetry-table.md](./contracts/telemetry-table.md), incluida la
      agrupación por `PROVIDER`/`COST_UNIT` para no sumar USD y créditos.
- [X] T030 [P] Añadir al `README.md` raíz la sección del agente: cómo invocarlo, el diagrama de
      flujo del plan (incluido `llm_provider.py`) y el guion de demo de siete pasos del paso 8 de
      [quickstart.md](./quickstart.md) (SC-004).
- [ ] T031 Medir el coste de una ejecución completa de la suite de evaluación con
      `LLM_PROVIDER=openai` y anotarlo en [research.md](./research.md) como línea base
      (Principio IV: "medir antes de escalar"), con la consulta de coste en USD por modelo.
- [ ] T032 Ejecutar la suite completa (`.venv\Scripts\python.exe -m pytest -q`) y confirmar que no
      se ha roto ningún test de las features 001 y 002.

---

## Dependencies

### Entre fases

```text
Phase 1 (Setup)
   └──> Phase 2 (Foundational)   ← BLOQUEANTE
          ├──> Phase 3 (US1, P1)  🎯 MVP
          │       └──> Phase 4 (US2, P2)   ← necesita ask() existente
          │               └──> Phase 5 (US3, P3)
          └──> Phase 6 (Polish)   ← al final
```

### Entre historias

- **US1** no depende de nada más allá de la fase 2. Es entregable por sí sola.
- **US2** depende de US1: extiende `ask()`, no lo sustituye. Sin `ask()` no hay nada que ajustar.
- **US3** depende de que existan invocaciones que registrar (US1) y estados que distinguir (US2).
  Su API pública no cambia: `ask()` ya acepta `telemetry` desde T009.

### Dependencias críticas concretas

- **T003 bloquea T004** y todo lo demás: sin el rol por defecto correcto, la API REST de Cortex
  Analyst (y la del orquestador si `LLM_PROVIDER=cortex`) devuelve `403`.
- **T004 bloquea T014**: sin el proveedor por defecto confirmado con `tools`, el bucle no puede
  funcionar.
- **T011/T012 bloquean T013** — FR-010 y Principio II: los tests van primero. No es negociable.
- **T017/T018 bloquean T019** por el mismo motivo.
- **T022 bloquea T023** por el mismo motivo.
- **T023 bloquea T025**: sin el grant, el despliegue de la tabla falla.

## Parallel Execution Examples

**Fase 1** — tras T001:

```text
T002 (.env.example)  ‖  T003 (grants en Snowflake)
```

**Fase 2** — los cuatro módulos son independientes entre sí:

```text
T005 (prompts.py)  ‖  T006 (cortex_analyst.py)  ‖  T007 (llm_provider.py)  ‖  T008 (telemetry.py)
```

T009 y T010 van después, porque T010 importa `NullTelemetry` de T008.

**Fase 3** — los dos módulos de test son ficheros distintos:

```text
T011 (test_agent_evaluation.py)  ‖  T012 (test_agent_contract.py)
```

**Fase 6**:

```text
T029 (snowflake/README.md)  ‖  T030 (README.md)
```

**No paralelizable**: T013, T014, T020 y T027 tocan todas `agent.py`.

## Implementation Strategy

### MVP: fases 1 + 2 + 3

Al terminar la fase 3 hay un agente que responde las 11 preguntas del catálogo. Es demostrable en
directo y valida el mayor riesgo de la feature: que la unión SDK de OpenAI → Cortex Analyst →
semantic view funciona de verdad.

**Recomendación**: parar en el checkpoint de la fase 3 y ejecutar el CLI con `--verbose` delante
del equipo antes de seguir. Si la unión no funciona, el problema estará en T003/T004 y es mejor
descubrirlo con 6 tareas hechas que con 28.

### Incrementos

| Incremento | Fases | Qué añade |
|---|---|---|
| 1 — MVP | 1-3 | El agente responde (US1) |
| 2 — Confiable | 4 | No alucina ni revienta (US2) |
| 3 — Auditable | 5 | Telemetría en Snowflake (US3) |
| 4 — Explicable | 6 | Documentación y guion de demo |

### Nota de coste

Cada ejecución de la suite consume tokens reales del proveedor configurado (OpenAI por defecto;
Cortex si `LLM_PROVIDER=cortex`): 12 invocaciones con al menos dos llamadas al modelo cada una. La
fixture cacheada de T010 evita repetir la misma pregunta entre módulos. Durante el desarrollo,
iterar con `-k` sobre una sola pregunta antes de lanzar la suite entera.

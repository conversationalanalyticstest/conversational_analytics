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

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: A qué historia de usuario pertenece (US1, US2, US3)
- Cada tarea incluye la ruta de fichero exacta

## Path Conventions

Proyecto único (ver "Project Structure" en [plan.md](./plan.md)):

- `src/conversational_analytics/` — código del agente
- `tests/` — suite de evaluación y de contrato
- `snowflake/` — DDL desplegable
- `db.py` **no se modifica**: se reutiliza `get_connection()` tal cual

---

## Phase 1: Setup

**Purpose**: Dejar el entorno en condiciones y **verificar empíricamente** las dos incógnitas que
[research.md](./research.md) dejó abiertas, antes de escribir una sola línea de agente.

- [ ] T001 Añadir `openai` y `httpx` a `pyproject.toml` con `poetry add openai httpx` y regenerar
      `poetry.lock`. Verificar que instalan en el venv de Python 3.14 (esta máquina no tiene
      compilador C: si alguna dependencia transitiva no trae wheel, recrear el venv con
      `poetry env use 3.12`, que sigue dentro de `requires-python`). Hecho cuando
      `.venv\Scripts\python.exe -c "import openai, httpx"` no falla.
- [ ] T002 [P] Documentar en `.env.example` las dos variables nuevas, ambas opcionales:
      `CORTEX_MODEL` y `SNOWFLAKE_SEMANTIC_VIEW` (defecto `CICD_DEMO.DATA.SV_PHARMA_SALES`), con
      un comentario explícito de que `OPENAI_API_KEY` **no** se usa ni debe declararse
      (Restricción Tecnológica de la constitución).
- [ ] T003 Verificar el rol por defecto del usuario (D-04): ejecutar
      `SHOW USERS LIKE 'CONVERSATIONALANALYTICSTEST';` y comprobar que `default_role` es
      `CICD_DEMO_ROLE`. Si no lo es, añadir
      `ALTER USER CONVERSATIONALANALYTICSTEST SET DEFAULT_ROLE = CICD_DEMO_ROLE;` a
      `snowflake/manual/grant_user.sql` y ejecutarlo. Hecho cuando el rol por defecto tiene
      `SNOWFLAKE.CORTEX_USER` por herencia. Bloquea todo lo demás: sin esto la API REST devuelve
      `403` aunque el conector funcione.
- [ ] T004 Determinar el modelo efectivo (D-05): probar contra
      `/api/v2/cortex/v1/chat/completions` con el SDK `openai` que el modelo candidato responde y
      que **devuelve `tool_calls`** al pasarle un `tools` de prueba. Si no está disponible en la
      región, probar otro modelo o documentar la activación de *cross-region inference* en
      `snowflake/manual/`. Hecho cuando se actualiza D-05 en
      [research.md](./research.md) con el identificador de modelo elegido y la evidencia.

**Checkpoint**: dependencias instaladas, permisos correctos y un modelo confirmado que soporta
*function calling*.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Las piezas que todas las historias necesitan: el prompt, el cliente de Cortex Analyst,
los tipos públicos y la telemetría *nula*. La implementación real de telemetría es de US3; aquí
sólo se crea la interfaz para que `ask()` tenga su firma definitiva desde el principio.

**⚠️ CRITICAL**: Ninguna tarea de las fases 3-5 puede empezar hasta completar esta fase.

- [ ] T005 [P] Crear `src/conversational_analytics/prompts.py` con la constante `SYSTEM_PROMPT`:
      el agente responde en español, usa **siempre** la herramienta para obtener datos, no inventa
      cifras nunca, y si la herramienta no devuelve filas lo dice explícitamente. Docstring de
      módulo indicando que es un artefacto desplegable versionado (Principio III), no una cadena
      auxiliar.
- [ ] T006 [P] Crear `src/conversational_analytics/cortex_analyst.py`: cliente `httpx` de
      `/api/v2/cortex/analyst/message` según
      [contracts/cortex-endpoints.md](./contracts/cortex-endpoints.md). Función
      `generate_sql(question: str) -> AnalystResult` con las cabeceras `Authorization: Bearer` y
      `X-Snowflake-Authorization-Token-Type: PROGRAMMATIC_ACCESS_TOKEN`, `timeout=60`, y el
      parseo de `message.content[]` extrayendo `statement`, `confidence.verified_query_used.name`,
      `request_id` y `warnings`. En esta fase sólo la ruta feliz; el mapa de errores es T018.
- [ ] T007 [P] Crear `src/conversational_analytics/telemetry.py` con el `Protocol` `Telemetry`
      (método `record(event: TelemetryEvent) -> None`), la dataclass `TelemetryEvent` con las 20
      columnas de [data-model.md](./data-model.md), `NullTelemetry` (no-op, para tests) y la
      constante `CREDITS_PER_MTOKEN` más el cálculo de `estimated_cost` (devuelve `None` si el
      modelo no está en el diccionario, sin lanzar). `SnowflakeTelemetry` **no** se implementa
      aquí: es T025.
- [ ] T008 Crear `src/conversational_analytics/agent.py` con **sólo** los tipos públicos del
      contrato: `AgentStatus` (`OK`/`NO_DATA`/`ERROR`), `TokenUsage` y `AgentResponse`
      (`@dataclass(frozen=True)`), tal y como los fija
      [contracts/agent-api.md](./contracts/agent-api.md). Sin lógica todavía.
- [ ] T009 Añadir a `tests/conftest.py` las fixtures del agente, reutilizando las existentes sin
      modificarlas: `null_telemetry` (devuelve `NullTelemetry()`) y `agent_answer`, una fixture de
      ámbito sesión que invoca `ask(question, telemetry=NullTelemetry(), source="test")` y
      **cachea la respuesta por pregunta** para no pagar dos veces la misma invocación entre
      módulos de test (control de coste, Principio IV).

**Checkpoint**: existen los tipos, el prompt y el cliente del Analyst. `ask()` todavía no.

---

## Phase 3: User Story 1 - Responder una pregunta de negocio en lenguaje natural (Priority: P1) 🎯 MVP

**Goal**: Que una pregunta en español devuelva una respuesta en lenguaje natural con el dato
correcto, obtenido de `SV_PHARMA_SALES`.

**Independent Test**: Invocar el agente con Q-01..Q-11 y comprobar que las filas devueltas cumplen
la aserción del catálogo de referencia. No requiere telemetría ni manejo de ausencia de datos.

### Tests (ANTES de la implementación — FR-010, Principio II)

- [ ] T010 [US1] Crear `tests/test_agent_evaluation.py` con los casos Q-01 a Q-11 según la matriz
      de [contracts/agent-api.md](./contracts/agent-api.md). Asserts sobre `AgentResponse.rows`,
      no sobre `answer` (decisión D-07); más los asserts transversales
      (`status != ERROR`, sin `NaN`/`None`, `sql is not None`, `usage.prompt_tokens > 0`,
      `latency_ms > 0`). Las preguntas se toman literalmente de
      [reference-questions.md](../001-mock-sales-dataset/contracts/reference-questions.md). Hecho
      cuando los 11 tests **fallan** por `ImportError`/`AttributeError` de `ask`.
- [ ] T011 [P] [US1] Crear `tests/test_agent_contract.py` con `test_no_openai_api_key_needed`
      (verifica que `OPENAI_API_KEY` no está en el entorno y que `ask()` funciona igual — D-08),
      `test_ask_is_stateless` (dos `ask()` seguidos; el segundo no resuelve una referencia al
      primero — FR-006) y `test_no_direct_table_access` (el SQL generado referencia
      `SV_PHARMA_SALES` y no `DIM_PRODUCT`/`DIM_COUNTRY`/`FACT_SALES` — FR-002). Deben fallar.

### Implementación

- [ ] T012 [US1] En `src/conversational_analytics/agent.py`: constante
      `QUERY_SEMANTIC_VIEW_SCHEMA` (JSON schema, en una constante aparte por la regla de diseño 2
      del plan) y función `query_semantic_view(question: str) -> dict` — función Python normal,
      **sin decoradores**. Llama a `cortex_analyst.generate_sql()`, ejecuta el `statement` con
      `db.get_connection()`, devuelve `rows` (como `list[dict]`, truncado a
      `MAX_ROWS_TO_MODEL = 100`), `sql`, `verified_query_name`, `request_id` y `sf_query_id`
      (`cursor.sfqid`).
- [ ] T013 [US1] En `src/conversational_analytics/agent.py`: construir el cliente
      `OpenAI(api_key=SNOWFLAKE_PAT, base_url=".../api/v2/cortex/v1", timeout=60)` e implementar
      `ask(question, *, telemetry=None, source="cli") -> AgentResponse` con el bucle de
      *tool-calling* explícito (límite de iteraciones para no ciclar), **acumulando `usage` de
      todas las llamadas al modelo**, no sólo de la última. Devuelve `status=OK` cuando hay filas.
      El bucle debe quedar legible: es lo que se enseña en la demo (SC-004).
- [ ] T014 [US1] Crear `src/conversational_analytics/cli.py` con `argparse`: pregunta posicional,
      `--verbose` (SQL generado, verified query, estado, tokens, latencia) y `--check`
      (verifica modelo y ambos endpoints, paso 4 de [quickstart.md](./quickstart.md)). Códigos de
      salida `0` para `OK`/`NO_DATA` y `1` para `ERROR`, según
      [contracts/agent-api.md](./contracts/agent-api.md).
- [ ] T015 [US1] Ejecutar `.venv\Scripts\python.exe -m pytest tests/test_agent_evaluation.py -v`
      y dejar Q-01..Q-11 en verde, más los tres tests de T011. Hecho cuando `--check` responde OK
      y el CLI contesta Q-01 con un número positivo.

**Checkpoint**: MVP entregable. El agente responde preguntas de negocio de punta a punta.

---

## Phase 4: User Story 2 - Recibir un aviso claro cuando no hay datos (Priority: P2)

**Goal**: Que una pregunta fuera de rango, ambigua o fuera de dominio produzca un mensaje explícito
de ausencia de datos, y que un fallo de servicio produzca un error controlado.

**Independent Test**: Enviar Q-12 y comprobar `status == NO_DATA`, `rows` vacío y una respuesta sin
ninguna cifra inventada.

### Tests (ANTES de la implementación)

- [ ] T016 [US2] Añadir el caso Q-12 a `tests/test_agent_evaluation.py`: `status == NO_DATA`,
      `rows` vacía, `answer` expresa ausencia de datos y **no contiene ninguna cifra de ventas**.
      Debe fallar mientras `ask()` no distinga `NO_DATA`.
- [ ] T017 [P] [US2] Añadir a `tests/test_agent_contract.py`: `test_out_of_domain_question`
      ("¿Qué tiempo hace hoy?" → `NO_DATA`, no `ERROR` ni cifra inventada) y
      `test_analyst_timeout_returns_error` (timeout forzado → `status == ERROR` con mensaje de
      fallo de servicio, FR-009).

### Implementación

- [ ] T018 [US2] En `src/conversational_analytics/cortex_analyst.py`: implementar el mapa de
      errores completo de [contracts/cortex-endpoints.md](./contracts/cortex-endpoints.md) —
      `timeout`, `401`, `403`, `400`, y el bloque `content[].type == "suggestions"` como señal de
      "no se pudo generar SQL", que **no** es un error. Registrar `warnings[]` cuando no esté
      vacío. Hacer el timeout configurable para que T017 pueda forzarlo.
- [ ] T019 [US2] En `src/conversational_analytics/agent.py`: derivar `AgentStatus` según la
      máquina de estados de [data-model.md](./data-model.md) (`NO_DATA` para cero filas o
      `suggestions`; `ERROR` sólo para fallos técnicos), devolver la clave `note` a la herramienta
      para que el modelo redacte la ausencia de datos, y capturar toda excepción operativa dentro
      de `ask()` — no se propaga ninguna al llamante. Reforzar en `prompts.py` la instrucción de
      no inventar cifras cuando la herramienta no devuelva filas.
- [ ] T020 [US2] Ejecutar Q-12 y los dos tests de contrato nuevos, y dejarlos en verde sin haber
      roto Q-01..Q-11.

**Checkpoint**: el agente ya no alucina ni revienta. US1 + US2 son la demo defendible.

---

## Phase 5: User Story 3 - Trazar cada pregunta para poder auditarla (Priority: P3)

**Goal**: Que toda invocación quede registrada en Snowflake, incluidas las de `NO_DATA` y `ERROR`.

**Independent Test**: Invocar el agente una vez y comprobar por SQL que existe la fila
correspondiente con los campos mínimos de FR-007.

### Tests (ANTES de la implementación)

- [ ] T021 [US3] Crear `tests/test_telemetry.py`, marcado con `writes_db` (marker ya existente en
      `pyproject.toml`): verifica que una invocación inserta exactamente una fila; que están los
      campos mínimos de FR-007; y las reglas de integridad de
      [data-model.md](./data-model.md) (`STATUS` en el enum, `ERROR_MESSAGE` no nulo ⟺ `ERROR`,
      `ROW_COUNT > 0` ⟹ `OK`, `GENERATED_SQL` nulo ⟹ no `OK`, `FEEDBACK` en `{-1,1,NULL}`).
      Incluye un caso `NO_DATA` para comprobar que también se registra.

### Implementación

- [ ] T022 [US3] Modificar `snowflake/001_bootstrap.sql`, sección 6: añadir
      `GRANT CREATE TABLE, CREATE VIEW ON SCHEMA CICD_DEMO.DEVOPS TO ROLE CICD_DEMO_ROLE;`.
      Sin esto T024 falla (D-04).
- [ ] T023 [US3] Crear `snowflake/005_telemetry.sql` con `AGENT_TELEMETRY`
      (`CREATE TABLE IF NOT EXISTS`, **nunca** `CREATE OR REPLACE`: el histórico no se puede
      perder) y `V_AGENT_ACTIVITY` (`CREATE OR REPLACE`), copiando el DDL de
      [contracts/telemetry-table.md](./contracts/telemetry-table.md) y siguiendo la cabecera de
      estilo de `snowflake/004_semantic_view.sql`.
- [ ] T024 [US3] Desplegar `001_bootstrap.sql` (requiere `ACCOUNTADMIN`) y `005_telemetry.sql` con
      `snow sql -f ... -c cicd_demo` desde la raíz del repo. Verificar con
      `SELECT COUNT(*) FROM CICD_DEMO.DEVOPS.AGENT_TELEMETRY;` y que `V_AGENT_ACTIVITY` resuelve.
- [ ] T025 [US3] En `src/conversational_analytics/telemetry.py`: implementar `SnowflakeTelemetry`
      con el `INSERT` parametrizado en `CICD_DEMO.DEVOPS.AGENT_TELEMETRY`, resolviendo
      `COMMIT_SHA` desde `GITHUB_SHA` o `git rev-parse HEAD`, `ACTOR` desde el usuario del sistema
      y `ESTIMATED_COST` con `CREDITS_PER_MTOKEN`. Un fallo al escribir telemetría **no** puede
      tumbar una respuesta correcta: se registra el problema y se sigue.
- [ ] T026 [US3] En `src/conversational_analytics/agent.py`: instrumentar `ask()` para construir
      el `TelemetryEvent` y llamar a `telemetry.record()` en **todas** las rutas de salida,
      también en `ERROR` (US3, escenario 2). Poner `SnowflakeTelemetry` como valor por defecto
      cuando el parámetro `telemetry` es `None`.
- [ ] T027 [US3] Ejecutar `tests/test_telemetry.py` en verde y validar SC-003 con la consulta del
      paso 7 de [quickstart.md](./quickstart.md): tras la suite de evaluación debe haber una fila
      por invocación, incluidas las `NO_DATA`.

**Checkpoint**: las tres historias completas. El Principio IV deja de ser una promesa.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T028 [P] Añadir a `snowflake/README.md` la sección de telemetría con las cuatro consultas de
      demostración de [contracts/telemetry-table.md](./contracts/telemetry-table.md).
- [ ] T029 [P] Añadir al `README.md` raíz la sección del agente: cómo invocarlo, el diagrama de
      flujo del plan y el guion de demo de seis pasos del paso 8 de
      [quickstart.md](./quickstart.md) (SC-004).
- [ ] T030 Medir el coste de una ejecución completa de la suite de evaluación y anotarlo en
      [research.md](./research.md) como línea base (Principio IV: "medir antes de escalar"), con
      la consulta de créditos por modelo.
- [ ] T031 Ejecutar la suite completa (`.venv\Scripts\python.exe -m pytest -q`) y confirmar que no
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
  Su API pública no cambia: `ask()` ya acepta `telemetry` desde T008.

### Dependencias críticas concretas

- **T003 bloquea T004** y todo lo demás: sin el rol por defecto correcto, la API REST devuelve
  `403`.
- **T004 bloquea T013**: sin un modelo confirmado con `tools`, el bucle no puede funcionar.
- **T010/T011 bloquean T012** — FR-010 y Principio II: los tests van primero. No es negociable.
- **T016/T017 bloquean T018** por el mismo motivo.
- **T021 bloquea T022** por el mismo motivo.
- **T022 bloquea T024**: sin el grant, el despliegue de la tabla falla.

## Parallel Execution Examples

**Fase 1** — tras T001:

```text
T002 (.env.example)  ‖  T003 (grants en Snowflake)
```

**Fase 2** — los tres módulos son independientes entre sí:

```text
T005 (prompts.py)  ‖  T006 (cortex_analyst.py)  ‖  T007 (telemetry.py)
```

T008 y T009 van después, porque T009 importa `NullTelemetry` de T007.

**Fase 3** — los dos módulos de test son ficheros distintos:

```text
T010 (test_agent_evaluation.py)  ‖  T011 (test_agent_contract.py)
```

**Fase 6**:

```text
T028 (snowflake/README.md)  ‖  T029 (README.md)
```

**No paralelizable**: T012, T013, T019 y T026 tocan todas `agent.py`.

## Implementation Strategy

### MVP: fases 1 + 2 + 3

Al terminar la fase 3 hay un agente que responde las 11 preguntas del catálogo. Es demostrable en
directo y valida el mayor riesgo de la feature: que la unión SDK de OpenAI → Cortex Analyst →
semantic view funciona de verdad.

**Recomendación**: parar en el checkpoint de la fase 3 y ejecutar el CLI con `--verbose` delante
del equipo antes de seguir. Si la unión no funciona, el problema estará en T003/T004 y es mejor
descubrirlo con 5 tareas hechas que con 27.

### Incrementos

| Incremento | Fases | Qué añade |
|---|---|---|
| 1 — MVP | 1-3 | El agente responde (US1) |
| 2 — Confiable | 4 | No alucina ni revienta (US2) |
| 3 — Auditable | 5 | Telemetría en Snowflake (US3) |
| 4 — Explicable | 6 | Documentación y guion de demo |

### Nota de coste

Cada ejecución de la suite consume tokens de Cortex reales: 12 invocaciones con al menos dos
llamadas al modelo cada una. La fixture cacheada de T009 evita repetir la misma pregunta entre
módulos. Durante el desarrollo, iterar con `-k` sobre una sola pregunta antes de lanzar la suite
entera.

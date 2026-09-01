# Research: Agente conversacional sobre la semantic view de ventas

**Feature**: `003-conversational-agent` | **Fecha**: 2026-09-01 | **Fase**: 0

Decisiones tomadas antes de diseñar. Cada una lleva qué se eligió, por qué, y qué se descartó.

---

## D-01 — Arquitectura general: orquestador OpenAI + Cortex Analyst como herramienta

**Decisión**: el SDK de OpenAI apunta a `/api/v2/cortex/v1/chat/completions` y actúa de
orquestador. La semantic view se alcanza a través de una **herramienta** Python
(`query_semantic_view`) que llama por HTTP a `/api/v2/cortex/analyst/message`.

**Rationale**: Snowflake expone tres endpoints de Cortex y sólo uno es compatible con el SDK de
OpenAI, pero ese precisamente **no** conoce las semantic views:

| Endpoint | Formato | ¿Consume `SV_PHARMA_SALES`? |
|---|---|---|
| `/api/v2/cortex/v1/chat/completions` | compatible OpenAI, soporta `tools` | No |
| `/api/v2/cortex/analyst/message` | propietario Snowflake | Sí |
| `/api/v2/cortex/agent:run` | propietario Snowflake | Sí (Analyst como tool nativa) |

Cumplir la Restricción Tecnológica de la constitución ("SDK de OpenAI apuntando al endpoint de
Cortex") y a la vez FR-002 ("consultar exclusivamente `SV_PHARMA_SALES`") obliga a usar los dos
primeros. El *function calling* es el mecanismo estándar para unirlos.

**Alternativas consideradas**:

- **Cortex Agents API** (`/agent:run`): Snowflake orquesta, con Analyst como herramienta nativa y
  `Threads` para el estado. Descartada porque no usa el SDK de OpenAI (incumple la Restricción
  Tecnológica), porque la orquestación es opaca y eso degrada el Principio IV, y porque tiene un
  límite documentado relevante a futuro: *"Cortex Agents APIs are not supported from within a
  Streamlit in Snowflake (SiS) application using a warehouse runtime"*.
- **Sin orquestador** (pregunta → Analyst → SQL → ejecutar → devolver filas): son ~10 líneas y
  responde 11 de las 12 preguntas. Descartada porque devuelve una tabla, no una respuesta en
  lenguaje natural (FR-001), y porque no usa el SDK de OpenAI. Se documenta aquí como línea base
  de comparación: es la referencia contra la que medir si el orquestador aporta algo.
- **Que el modelo escriba el SQL** contra las tablas base: viola FR-002 y tira a la basura las
  `AI_VERIFIED_QUERIES` de la feature 002.

---

## D-02 — SDK: `openai` a pelo, no `openai-agents`

**Decisión**: dependencia `openai` con bucle de *tool-calling* escrito a mano. **No** se añade
`openai-agents`.

**Rationale**:

| | `openai` | `openai-agents` |
|---|---|---|
| Bucle de tool-calling | ~40 líneas propias | oculto en `Runner` |
| Dependencia nueva | ya obligatoria por constitución | una más |
| Superficie hacia OpenAI | un único `base_url` | *defaults* que apuntan a OpenAI |
| Instrumentación | inline, visible | `RunHooks` / `TracingProcessor` |

Tres razones, por orden de peso:

1. **El repo es material didáctico** (Principio I, SC-004). El bucle de tool-calling es
   exactamente lo que hay que enseñar; esconderlo dentro de un `Runner` va en contra del objetivo
   del proyecto.
2. **Riesgo de fuga.** `openai-agents` tiene varios caminos que salen hacia OpenAI si se despistan:
   el *tracing* integrado sube trazas a `platform.openai.com`, `Agent(model="gpt-4o")` sin
   `openai_client` usa la API pública, y las tools alojadas (`WebSearchTool`, `FileSearchTool`,
   `CodeInterpreterTool`) se ejecutan en OpenAI. Con `openai` a pelo sólo hay un cliente y un
   `base_url`.
3. **La observabilidad hay que escribirla igual.** Los hooks de `openai-agents` no regalan la
   telemetría del Principio IV; sólo cambian dónde se engancha.

**Alternativa considerada**: `openai-agents`, elegida en el documento de arquitectura del equipo.
Es una opción defendible y **sigue siendo compatible con este diseño** — de hecho usa `openai` por
debajo, con el mismo `base_url`, PAT y endpoint. Se descarta *ahora* porque su ventaja real
(`Session` multi-turno, handoffs, guardrails) no se cobra en una feature que la constitución
obliga a que sea *stateless* de un solo turno.

**Si se adopta más adelante**, la migración es local gracias a las tres reglas de diseño del
[plan](./plan.md#reglas-de-diseño-frontera-de-migración). Lo que cambiaría:

- se conserva: `db.py`, `cortex_analyst.py`, la función de la tool, la tabla de telemetría y **los
  tests de evaluación**;
- se reescribe: el bucle → `Runner.run()`, el cliente → `AsyncOpenAI` +
  `OpenAIChatCompletionsModel`, la instrumentación inline → `RunHooks`.

Y haría falta obligatoriamente `set_tracing_disabled(True)`, porque el *tracing* integrado da 401
sin clave de OpenAI.

---

## D-03 — Autenticación: el mismo PAT para los dos endpoints

**Decisión**: `SNOWFLAKE_PAT` autentica las tres cosas: el conector de Snowflake, el endpoint de
chat completions y el de Cortex Analyst. **No se introduce ninguna credencial nueva.**

- SDK de OpenAI: `OpenAI(api_key=SNOWFLAKE_PAT, base_url="https://<account>.snowflakecomputing.com/api/v2/cortex/v1")`
- Cortex Analyst: cabeceras `Authorization: Bearer <PAT>` y
  `X-Snowflake-Authorization-Token-Type: PROGRAMMATIC_ACCESS_TOKEN`

**Rationale**: Principio V pide el mínimo de secretos. Y `OPENAI_API_KEY` no sólo es innecesaria:
su ausencia es una **garantía verificable** de que no se está llamando a la API pública de OpenAI.
De ahí el test anti-fuga (D-08).

**Riesgo**: los PAT caducan. Un PAT expirado se manifiesta como `401` en los tres sitios a la vez;
el mensaje de error del agente debe distinguirlo de "Cortex no responde" (FR-009).

---

## D-04 — Grants: `CORTEX_USER` sobre el rol por defecto y `CREATE TABLE` en `DEVOPS`

**Decisión**: dos ajustes en `snowflake/001_bootstrap.sql`.

1. `GRANT CREATE TABLE, CREATE VIEW ON SCHEMA CICD_DEMO.DEVOPS TO ROLE CICD_DEMO_ROLE` —
   ahora mismo el rol tiene `USAGE` sobre `DEVOPS` pero **no puede crear nada dentro**. Sin esto,
   `005_telemetry.sql` falla.
2. Verificar que `SNOWFLAKE.CORTEX_USER` llega por el camino correcto. Ya está concedido a
   `CICD_DEMO_ROLE`, pero la API REST de chat completions resuelve permisos contra el **rol por
   defecto del usuario**, no contra el rol de la sesión del conector. Si el rol por defecto de
   `CONVERSATIONALANALYTICSTEST` no es `CICD_DEMO_ROLE`, hay que fijarlo con
   `ALTER USER ... SET DEFAULT_ROLE = CICD_DEMO_ROLE` en `snowflake/manual/grant_user.sql`.

**Rationale**: son dos fallos de despliegue previsibles y baratos de evitar. El segundo es
especialmente traicionero porque el conector funcionará perfectamente mientras la llamada REST
devuelve `403`.

**Verificación**: primera tarea de la fase de implementación, antes de escribir código.

---

## D-05 — Modelo: configurable, con verificación de disponibilidad

**Decisión**: variable de entorno `CORTEX_MODEL`, con un valor por defecto en el código. La
elección concreta se **verifica empíricamente** en la primera tarea de implementación, contra dos
requisitos: que el modelo esté disponible en la región de la cuenta y que soporte `tools`.

**Rationale**: no todos los modelos de Cortex soportan *function calling* (según la documentación,
sí lo hacen las familias `openai-gpt-*` y Claude), y la disponibilidad depende de la región. Fijar
un identificador de modelo en el plan sin haberlo probado es una vía directa a un `400` en
implementación.

**Contingencia**: si el modelo elegido no está disponible en la región de `GNTUAOQ-YO01002`, se
activa *cross-region inference* a nivel de cuenta. Es un cambio de parámetro de cuenta, no de
código, y hay que documentarlo en `snowflake/manual/`.

---

## D-06 — Telemetría: tabla propia en `DEVOPS`, escrita por el agente

**Decisión**: `CICD_DEMO.DEVOPS.AGENT_TELEMETRY` (una fila por invocación) más la vista
`V_AGENT_ACTIVITY`. La escribe el propio agente vía un protocolo `Telemetry`.

**Rationale**: el Principio IV exige que la telemetría viva en Snowflake y sea consultable con SQL.
Ninguna de las capas de la cadena da la foto completa por sí sola:

| Dato | De dónde sale |
|---|---|
| quién pregunta | de la aplicación — nadie más lo sabe |
| pregunta | input de `ask()` |
| SQL generado | `content[].statement` de Cortex Analyst |
| **si usó una verified query** | `confidence.verified_query_used.name` |
| id de petición del Analyst | `request_id` |
| tokens in/out | `usage` del chat completions |
| id de la query SQL | `cursor.sfqid`, cruzable con `QUERY_HISTORY` |
| respuesta, latencia, estado | de la aplicación, envolviendo la llamada |
| commit SHA | `GITHUB_SHA` en CI |

El hallazgo aprovechable es **`verified_query_used`**: Cortex Analyst informa de si la pregunta se
resolvió con una de las `AI_VERIFIED_QUERIES` definidas en la feature 002. Es una señal de calidad
gratis, en runtime, sin LLM juez ni etiquetado manual, y da la métrica `% de preguntas resueltas
por verified query`.

**Alternativas consideradas**:

- Vistas nativas de `SNOWFLAKE.ACCOUNT_USAGE`: útiles para coste agregado, pero tienen latencia de
  actualización y no contienen la pregunta ni la respuesta. Se documentan como complemento, no
  como sustituto.
- Log a fichero: incumple el Principio IV explícitamente.

**Consecuencia para los tests**: escribir telemetría es un `INSERT`, y eso ensuciaría la suite. Por
eso `Telemetry` es un protocolo con implementación `NullTelemetry` para tests, y los tests que sí
escriben van marcados con `writes_db` (marker ya existente en `pyproject.toml`).

---

## D-07 — Los asserts de evaluación van sobre las filas, no sobre la prosa

**Decisión**: `test_agent_evaluation.py` valida `AgentResponse.rows` (el resultado del SQL
ejecutado) contra las aserciones del catálogo de referencia. El texto redactado por el modelo se
comprueba sólo de forma débil: que no esté vacío y, en el caso de Q-12, que exprese ausencia de
datos.

**Rationale**: el texto del modelo varía entre ejecuciones aunque la respuesta sea correcta.
Aserciones sobre prosa producen tests intermitentes, y un test intermitente en un gate de CI acaba
desactivado — que es justo lo que prohíbe el Flujo de Desarrollo de la constitución. Las filas del
SQL son deterministas.

**Alternativas consideradas**:

- *LLM as a judge*: más fiel a la experiencia real, pero introduce no determinismo, coste por
  ejecución y un segundo modelo que explicar. Contra el Principio I.
- `assert "4.200.000" in respuesta`: frágil ante formatos de número, redondeos e idioma.

**Cómo se valida Q-12 entonces**: `status == NO_DATA` y `rows` vacío, más una comprobación de que
la respuesta **no** contiene ninguna cifra inventada.

---

## D-08 — Test anti-fuga de `OPENAI_API_KEY`

**Decisión**: un test que verifica que `OPENAI_API_KEY` no está en el entorno y que el agente
funciona igualmente.

**Rationale**: la Restricción Tecnológica de la constitución ("NO se usa la API pública de OpenAI")
es hoy una afirmación en un documento. Este test la convierte en un invariante ejecutable, y es lo
único que impide que una futura línea de código empiece a llamar a `api.openai.com` sin que nadie
se entere. Cuesta dos líneas.

---

## D-09 — Multi-turno: fuera de alcance, con el punto de extensión identificado

**Decisión**: no se implementa. Cada invocación es independiente (FR-006).

**Rationale**: lo exige el Principio I como primera arquitectura.

**Nota para el futuro** (para no redescubrirlo): el trabajo real del multi-turno no es guardar el
historial — eso son ~5 líneas, porque el historial *es* la lista `messages`. El trabajo está en que
**hay dos historiales**: el del orquestador (para redactar con contexto) y el de Cortex Analyst
(que tiene su propio multi-turno y resuelve él las referencias del tipo "¿y en 2024?" al generar el
SQL). Decidir qué se le pasa al Analyst — la pregunta cruda, una reescrita por el orquestador, o el
hilo entero — es el 80% del esfuerzo, y es idéntico con `openai` y con `openai-agents`. Ningún
framework lo resuelve.

---

## D-10 — Canal de invocación: CLI

**Decisión**: `python -m conversational_analytics.cli "¿pregunta?"`, que imprime la respuesta y,
con `--verbose`, el SQL generado.

**Rationale**: FR-001 pide "una forma de invocar al agente" sin fijar cuál. Un CLI es lo más simple
que existe, no añade dependencias (`argparse` es estándar), es lo que usará la demo en directo y es
trivialmente automatizable desde CI. La interfaz gráfica quedó explícitamente fuera de alcance de
esta feature.

**Alternativas consideradas**: endpoint HTTP (añade framework web sin aportar a la demo);
Streamlit in Snowflake (interesante para el futuro, pero es despliegue de app, otra feature).

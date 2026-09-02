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
debajo, con el mismo cliente y proveedor configurados en `llm_provider.py`. Se descarta *ahora*
porque su ventaja real (`Session` multi-turno, handoffs, guardrails) no se cobra en una feature
que la constitución obliga a que sea *stateless* de un solo turno.

**Si se adopta más adelante**, la migración es local gracias a las cuatro reglas de diseño del
[plan](./plan.md#reglas-de-diseño-frontera-de-migración). Lo que cambiaría:

- se conserva: `db.py`, `cortex_analyst.py`, `llm_provider.py`, la función de la tool, la tabla de
  telemetría y **los tests de evaluación**;
- se reescribe: el bucle → `Runner.run()`, el cliente → `AsyncOpenAI` +
  `OpenAIChatCompletionsModel`, la instrumentación inline → `RunHooks`.

Y haría falta obligatoriamente `set_tracing_disabled(True)`, porque el *tracing* integrado sube
trazas a `platform.openai.com` salvo que se desactive expresamente — esto aplica
independientemente de qué proveedor de inferencia se use (D-11).

---

## D-03 — Autenticación: por proveedor, sin credenciales de más

**Decisión**: la autenticación del orquestador depende de `LLM_PROVIDER` (ver D-11):

- `LLM_PROVIDER=openai` (por defecto hoy): `OpenAI(api_key=OPENAI_API_KEY)` — la API pública de
  OpenAI, `base_url` por defecto del SDK.
- `LLM_PROVIDER=cortex` (cuando la cuenta lo permita): `OpenAI(api_key=SNOWFLAKE_PAT,
  base_url="https://<account>.snowflakecomputing.com/api/v2/cortex/v1")` — sin credencial nueva.

Cortex Analyst se autentica **siempre** con `SNOWFLAKE_PAT`, sea cual sea `LLM_PROVIDER`:
cabeceras `Authorization: Bearer <PAT>` y
`X-Snowflake-Authorization-Token-Type: PROGRAMMATIC_ACCESS_TOKEN`.

**Rationale**: Principio V pide el mínimo de secretos, no *cero* secretos — pedía cero mientras la
Restricción Tecnológica prohibía la API pública (v1.0.0). Con la enmienda v2.0.0, `OPENAI_API_KEY`
es un secreto legítimo y necesario mientras la cuenta Snowflake de la demo sea trial. El diseño
sigue minimizando: Cortex Analyst nunca necesita una credencial nueva, y si mañana `LLM_PROVIDER`
vuelve a `cortex`, `OPENAI_API_KEY` deja de leerse sin cambiar código.

**Riesgo**: los PAT caducan. Un PAT expirado se manifiesta como `401` en Cortex Analyst y (si
`LLM_PROVIDER=cortex`) también en el orquestador; el mensaje de error del agente debe distinguirlo
de "el servicio no responde" (FR-009). Una `OPENAI_API_KEY` inválida da también `401`, pero sólo en
el orquestador — permite diagnosticar cuál de los dos proveedores falla.

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

## D-05 — Modelo: por proveedor, configurable, con verificación de disponibilidad

**Decisión**: `OPENAI_MODEL` (cuando `LLM_PROVIDER=openai`) o `CORTEX_MODEL` (cuando
`LLM_PROVIDER=cortex`), cada una con un valor por defecto en el código. La elección concreta se
**verifica empíricamente** en la primera tarea de implementación: que el modelo esté disponible y
que soporte `tools`.

**Rationale**: con `LLM_PROVIDER=openai` cualquier modelo de la familia GPT-4 en adelante soporta
*function calling*; se fija un valor barato por defecto (p. ej. `gpt-4.1-mini`) y se deja
configurable. Con `LLM_PROVIDER=cortex`, no todos los modelos de Cortex soportan *function
calling* (según la documentación, sí las familias `openai-gpt-*` y Claude) y la disponibilidad
depende de la región — verificado empíricamente el 2026-09-02 que, además, esta cuenta concreta no
tiene ninguno habilitado (D-11).

**Contingencia** (sólo aplica a `LLM_PROVIDER=cortex`): si el modelo elegido no está disponible en
la región de `GNTUAOQ-YO01002`, se activa *cross-region inference* a nivel de cuenta. Es un cambio
de parámetro de cuenta, no de código, y hay que documentarlo en `snowflake/manual/`.

**Evidencia de verificación (T004, 2026-09-02)**: el modelo configurado en `AZURE_OPENAI_DEPLOYMENT`
(`gpt-5.4-mini`, vía Azure OpenAI Service — ver D-11) soporta `tools`/*function calling*; confirmado
end-to-end en la suite de tests del agente. Nota aparte: este modelo requiere `max_completion_tokens`
en la llamada de comprobación de `cli.py --check`, no `max_tokens` (los modelos más antiguos de la
familia GPT-4 aceptan ambos, los más recientes solo el primero).

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
gratis, en runtime, sin LLM juez ni etiquetado manual, y daría la métrica `% de preguntas resueltas
por verified query`.

**Limitación conocida — RESUELTA (2026-09-02)**: las `AI_VERIFIED_QUERIES` de `SV_PHARMA_SALES`
(feature 002) referenciaban nombres físicos de tabla. Cortex Analyst las descartaba con un
warning por cada una (*"Verified query 'Q01_...' referred to physical tables. The sql query was
transformed to use logical table names"*) y generaba él mismo el SQL correcto con nombres
lógicos, dejando `verified_query_used` siempre `NULL`. Se reescribieron las 11 verified queries
de la feature 002 para usar `SEMANTIC_VIEW(CICD_DEMO.DATA.SV_PHARMA_SALES ...)` con el nombre
completamente cualificado (ver D-11 en `specs/002-cortex-semantic-view/research.md` — reabre y
corrige D-08 de esa feature). Verificado empíricamente con dos preguntas reales (incluida la de
"qué área terapéutica creció más", la misma que causaba la variabilidad documentada más abajo en
esta sección): `verified_query_used` ya se rellena y no hay warnings. `USED_VERIFIED_QUERY` y
`PCT_VERIFIED` en la telemetría dejan de estar siempre en `0%`.

**Nueva columna por la constitución v2.0.0**: `PROVIDER` (`openai` | `cortex`) y `COST_UNIT`
(`USD` | `CREDITS`), porque el Principio IV exige declarar proveedor, modelo y unidad del coste.
Ver [data-model.md](./data-model.md).

**Alternativas consideradas**:

- Vistas nativas de `SNOWFLAKE.ACCOUNT_USAGE`: útiles para coste agregado, pero tienen latencia de
  actualización y no contienen la pregunta ni la respuesta. Se documentan como complemento, no
  como sustituto.
- Log a fichero: incumple el Principio IV explícitamente.

**Consecuencia para los tests**: escribir telemetría es un `INSERT`, y eso ensuciaría la suite. Por
eso `Telemetry` es un protocolo con implementación `NullTelemetry` para tests, y los tests que sí
escriben van marcados con `writes_db` (marker ya existente en `pyproject.toml`).

---

## D-07 — Los asserts de evaluación comparan contra un valor baseline exacto, no un umbral

**Decisión**: `test_agent_evaluation.py` valida `AgentResponse.rows` (el resultado del SQL
ejecutado) comparando cada valor numérico contra el resultado de una **consulta baseline
determinista** sobre las tablas base (`DIM_PRODUCT`, `DIM_COUNTRY`, `FACT_SALES`), no contra un
umbral genérico como "`> 0`". El texto redactado por el modelo se comprueba sólo de forma débil:
que no esté vacío y, en el caso de Q-12, que no contenga ninguna cifra de ventas.

**Rationale**: el Principio II (NON-NEGOTIABLE) exige preguntas de referencia "con su respuesta
esperada". Un umbral como `total > 0` lo incumple en la práctica: un agente que alucine cualquier
número positivo pasaría Q-01 igual. La corrección no cuesta nada de más: el SQL baseline por
pregunta **ya existía** en `tests/test_reference_questions.py` (de la feature 001) para verificar el
dataset; esta feature lo reutiliza como oro de referencia en vez de escribirlo de nuevo. Verificado
empíricamente el 2026-09-02: para Q-01, Cortex Analyst devolvió `281521882.71` y el SQL baseline
sobre tablas base da exactamente el mismo valor.

**Alternativas consideradas**:

- *LLM as a judge*: más fiel a la experiencia real, pero introduce no determinismo, coste por
  ejecución y un segundo modelo que explicar. Contra el Principio I.
- `assert "4.200.000" in respuesta`: frágil ante formatos de número, redondeos e idioma.
- `assert total is not None and total > 0` (descartada, era la versión inicial de este documento):
  no cumple "con su respuesta esperada" del Principio II; un valor positivo cualquiera pasa el test
  aunque sea erróneo.

**Cómo se valida Q-12 entonces**: `status == NO_DATA` y `rows` vacío, más una comprobación de que
la respuesta **no** contiene ninguna cifra de ventas — comprobando `rows == []`, no inspeccionando
la prosa con una expresión regular (un año como "2023" en el texto no debe contar como cifra
inventada).

---

## D-08 — Test de coherencia de proveedor

**Decisión**: un test que verifica que el proveedor y el modelo efectivamente usados coinciden con
`LLM_PROVIDER` y quedan reflejados en `PROVIDER`/`MODEL` de la telemetría, y que ninguna credencial
del otro proveedor viaja por error (si `LLM_PROVIDER=cortex`, `OPENAI_API_KEY` no se lee aunque
exista en el entorno; si `LLM_PROVIDER=openai`, `SNOWFLAKE_PAT` no se envía a `api.openai.com`).

**Rationale**: con la constitución v1.0.0 este test verificaba la ausencia de `OPENAI_API_KEY` como
invariante — la enmienda v2.0.0 invierte esa premisa: hoy `OPENAI_API_KEY` **sí** se usa por
defecto. Lo que hay que garantizar ya no es "nunca se llama a OpenAI", sino "se llama exactamente
al proveedor configurado, y de forma transparente en la telemetría" — que sigue siendo un
invariante barato de comprobar y sigue impidiendo una fuga de credenciales entre proveedores.

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

---

## D-11 — Proveedor del orquestador: OpenAI público por defecto, Cortex como alternativa configurable

**Decisión**: variable de entorno `LLM_PROVIDER` (`openai` por defecto, `cortex` como alternativa),
consumida por una única función `build_llm_client()` en `llm_provider.py` que devuelve el cliente
`openai.OpenAI` ya configurado (API key, `base_url`, modelo por defecto) según el valor.

**Rationale — por qué esto no estaba en el plan original**: la constitución v1.0.0 obligaba a usar
únicamente el endpoint de Cortex. Verificación empírica el 2026-09-02 contra la cuenta real
(`GNTUAOQ-YO01002`, trial, región `AWS_EU_WEST_3`) mostró que **ninguna vía de inferencia LLM de
Cortex está habilitada**:

| Vía probada | Resultado |
|---|---|
| `SNOWFLAKE.CORTEX.COMPLETE(...)` por SQL, 2 modelos | `399258 (0A000): AI function COMPLETE is not available for trial accounts` |
| `POST /api/v2/cortex/inference:complete` | `403 003001: This account is not allowed to access this endpoint` |
| `POST /api/v2/cortex/v1/chat/completions`, 6 modelos | `403 003001`, idéntico en los seis |

No es un problema de grants (`SNOWFLAKE.CORTEX_USER` ya concedido) ni de rol por defecto: es una
entitlement de cuenta. La constitución se enmendó a **v2.0.0** para permitir la API pública de
OpenAI como salida (ver Sync Impact Report en
[constitution.md](../../.specify/memory/constitution.md)). Cortex Analyst, que sí funciona en esta
cuenta (verificado: HTTP 200, SQL válido, `request_id`), se mantiene como único traductor NL→SQL.

**Por qué es configurable y no un cambio directo de `agent.py` a OpenAI**: la limitación es de la
*cuenta*, no del *diseño*. Si mañana se pasa a una cuenta de Snowflake de pago con Cortex habilitado,
la arquitectura correcta vuelve a ser "todo dentro de Snowflake" (más alineada con Principio I y el
mensaje pedagógico del repo). Fijar `agent.py` a OpenAI público sin capa de configuración
convertiría ese cambio futuro en una reescritura; con `LLM_PROVIDER`, es una variable de entorno.

**Coste de la abstracción**: una función y un `if`/`else` en `llm_provider.py` (~15 líneas). No
introduce un patrón *strategy* con clases ni un registro de proveedores — eso sería
sobre-ingeniería para dos casos (Principio I).

**Consecuencias documentadas en otras decisiones**: D-03 (autenticación), D-05 (modelo), D-06
(columnas `PROVIDER`/`COST_UNIT` en telemetría), D-08 (test de coherencia en vez de anti-fuga).

**Evidencia de verificación (T004, 2026-09-02)**: con `LLM_PROVIDER=openai` y una credencial real
(en este caso una key de **Azure OpenAI Service**, no la API pública de `api.openai.com`),
`client.chat.completions.create(...)` responde y **devuelve `tool_calls`** al pasarle el `tools`
de `query_semantic_view`; confirmado tanto con `cli.py --check` como con la suite completa de
`test_agent_evaluation.py`/`test_agent_contract.py` (14-17 de 17 tests en verde según la corrida,
ver notas de implementación). Azure se trata como un *backend* dentro de `LLM_PROVIDER=openai`
(detectado por la presencia de `AZURE_OPENAI_ENDPOINT`; usa `AzureOpenAI(...)` del SDK `openai` en
vez de `OpenAI(...)`, con `model=<AZURE_OPENAI_DEPLOYMENT>`), no un tercer valor de `LLM_PROVIDER`:
el `provider` reportado en telemetría sigue siendo `"openai"`. No se repitió la prueba contra
`/api/v2/cortex/v1/chat/completions` en esta fecha — la entitlement de cuenta documentada arriba
(403 en las 6 pruebas del 2026-09-02) no ha cambiado y no hay motivo para asumir que sí.

---

## Línea base de coste (T031, 2026-09-02)

**Medición**: ejecución completa de las 12 preguntas de referencia (Q-01..Q-12) contra `ask()`
con `LLM_PROVIDER=openai` (backend Azure OpenAI Service, modelo `gpt-5.4-mini`) y telemetría real
(`SnowflakeTelemetry`, no `NullTelemetry` — los tests de la suite usan `NullTelemetry` para no
ensuciar la tabla en cada corrida, ver D-06, así que esta medición se hizo con un script aparte
que invoca `ask()` directamente). Consulta de coste (ver paso 7 de
[quickstart.md](./quickstart.md)):

```sql
SELECT PROVIDER, MODEL, COST_UNIT,
       COUNT(*) AS INVOCATIONS,
       SUM(TOTAL_TOKENS) AS TOKENS,
       ROUND(SUM(ESTIMATED_COST), 6) AS COST,
       ROUND(100.0 * SUM(IFF(USED_VERIFIED_QUERY, 1, 0)) / COUNT(*), 1) AS PCT_VERIFIED
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
GROUP BY PROVIDER, MODEL, COST_UNIT;
```

**Resultado**:

| PROVIDER | MODEL | COST_UNIT | INVOCATIONS | TOKENS | COST | PCT_VERIFIED |
|---|---|---|---|---|---|---|
| openai | gpt-5.4-mini | USD | 12 | 14 918 | 0.016544 | 0.0 |

**Lectura**: ~0.0017 USD por pregunta de media (12 preguntas ≈ 14.9k tokens totales, entrada+salida,
dos llamadas al modelo por pregunta como mínimo). Para la demo completa (5-7 preguntas en vivo) el
coste es de céntimos de dólar — irrelevante operativamente, coherente con el Principio IV
("observar y controlar", no "el coste bloquea la demo").

**Hallazgo colateral, no bloqueante**: `PCT_VERIFIED = 0.0` en esta corrida — ninguna de las 12
preguntas en **español** usó una `AI_VERIFIED_QUERY` de la feature 002, pese a que D-11 (ver
`specs/002-cortex-semantic-view/research.md`) documenta el fix de las verified queries como
resuelto y verificado con `generate_sql()` directo. Hipótesis más probable: las verified queries
tienen su campo `QUESTION` en **inglés** (p. ej. *"Which therapeutic area grew the most..."*) y el
matching semántico de Cortex Analyst pondera la similitud de idioma/frase, no solo la intención;
las 12 preguntas de referencia están en español. No se investiga más a fondo aquí (fuera de
alcance de T031, que solo pide medir el coste) — queda anotado como posible mejora futura de la
feature 002: traducir o duplicar el campo `QUESTION` de las verified queries al español, o
verificar empíricamente si el idioma realmente afecta el matching.


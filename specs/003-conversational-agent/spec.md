# Feature Specification: Agente conversacional sobre la semantic view de ventas

**Feature Branch**: `003-conversational-agent`

**Created**: 2026-09-01

**Status**: Draft

**Input**: User description: "Crear el agente conversacional utilizando el SDK de OpenAI y
Cortex para llamar a la base de datos usando la semantic view."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Responder una pregunta de negocio en lenguaje natural (Priority: P1)

Una persona del equipo comercial escribe una pregunta en lenguaje natural sobre las ventas
(p. ej. "¿Cuáles fueron las ventas netas totales en 2025?") y el agente devuelve una respuesta
en lenguaje natural con el dato correcto, obtenido consultando la semantic view
`SV_PHARMA_SALES` a través de Cortex Analyst.

**Why this priority**: Es la funcionalidad mínima que hace que el proyecto deje de ser "una
base de datos con una vista" y pase a ser "un agente conversacional". Sin esto no hay demo.

**Independent Test**: Se puede probar de forma aislada invocando el agente con una de las
preguntas del catálogo de referencia ([reference-questions.md](../001-mock-sales-dataset/contracts/reference-questions.md))
y comprobando que la respuesta contiene el valor numérico esperado.

**Acceptance Scenarios**:

1. **Given** el agente está configurado con acceso a la semantic view, **When** se le pregunta
   "¿Cuáles fueron las ventas netas totales en 2025?", **Then** responde con un único número
   positivo en lenguaje natural, coherente con la aserción de Q-01.
2. **Given** una pregunta con varias dimensiones (marca, país, año), **When** se envía al
   agente, **Then** la respuesta refleja el filtro combinado y no un subconjunto de él.
3. **Given** una pregunta cuya respuesta es una lista (top-N, comparativa), **When** se envía
   al agente, **Then** la respuesta enumera todos los elementos con su valor, sin truncar.

---

### User Story 2 - Recibir un aviso claro cuando no hay datos (Priority: P2)

Cuando la pregunta cae fuera del histórico disponible (2023-2025) o no puede resolverse contra
la semantic view, el agente MUST decir explícitamente que no hay datos, en vez de inventar una
cifra o devolver un error técnico.

**Why this priority**: Es el requisito de confianza del Principio II de la constitución
("Evaluación del Agente como Test"): un agente que alucina cifras es peor que no tener agente.
Depende de que US1 ya funcione, por eso es P2.

**Independent Test**: Se puede probar de forma aislada enviando Q-12 ("¿Cuánto vendimos en
2021?") y comprobando que la respuesta indica ausencia de datos, sin lanzar una excepción sin
capturar ni devolver un número.

**Acceptance Scenarios**:

1. **Given** una pregunta sobre un año fuera de 2023-2025, **When** se envía al agente,
   **Then** la respuesta indica explícitamente que no hay datos para ese periodo.
2. **Given** una pregunta ambigua o no resoluble contra las dimensiones/métricas de la semantic
   view, **When** se envía al agente, **Then** la respuesta lo comunica de forma clara en vez
   de devolver un error crudo del SDK o de Snowflake.

---

### User Story 3 - Trazar cada pregunta para poder auditarla (Priority: P3)

Cada invocación del agente queda registrada (pregunta, SQL generado, respuesta, éxito/error,
latencia) para poder revisar después qué se preguntó y si la respuesta fue correcta.

**Why this priority**: Es un requisito de la constitución (Principio IV, Observabilidad y
Control de Coste) pero no bloquea la demo básica de preguntar-y-responder; se apoya en que
US1 y US2 ya generen el evento a registrar.

**Independent Test**: Se puede probar de forma aislada invocando el agente una vez y
comprobando que queda un registro correspondiente con los campos mínimos, independientemente
de si la pregunta tuvo o no datos.

**Acceptance Scenarios**:

1. **Given** el agente responde una pregunta con datos, **When** termina la invocación,
   **Then** existe un registro con pregunta, SQL generado, respuesta, estado "éxito" y latencia.
2. **Given** el agente responde una pregunta sin datos (US2) o falla, **When** termina la
   invocación, **Then** existe igualmente un registro, con estado "sin datos" o "error" según
   corresponda.

### Edge Cases

- ¿Qué pasa si Cortex Analyst tarda demasiado o el servicio no responde? El agente MUST
  comunicar un fallo de servicio, no quedarse colgado indefinidamente ni devolver una respuesta
  inventada.
- ¿Qué pasa si la pregunta no tiene relación alguna con ventas (p. ej. "¿qué tiempo hace hoy?")?
  El agente MUST reconocer que está fuera de su dominio y decirlo, no intentar forzar una
  consulta SQL sin sentido.
- ¿Qué pasa si dos preguntas consecutivas no están relacionadas entre sí? El agente MUST
  tratarlas de forma independiente: la primera arquitectura es de un solo turno, sin memoria de
  conversación previa (Principio I de la constitución).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST exponer una forma de invocar al agente con una pregunta en
  lenguaje natural en español o inglés y obtener una respuesta en lenguaje natural.
- **FR-002**: El sistema MUST resolver la pregunta consultando exclusivamente la semantic view
  `SV_PHARMA_SALES` (feature 002), sin acceder a las tablas base directamente ni construir SQL
  a mano fuera de lo que genera Cortex Analyst.
- **FR-003**: El sistema MUST usar el SDK de OpenAI configurado contra el endpoint de Cortex de
  Snowflake para la generación de la consulta y la respuesta en lenguaje natural (Restricción
  Tecnológica de la constitución) — NO la API pública de OpenAI.
- **FR-004**: El sistema MUST responder correctamente, con el valor esperado, a cada una de las
  11 preguntas satisfacibles del catálogo de referencia (Q-01 a Q-11).
- **FR-005**: El sistema MUST responder a preguntas fuera de rango (Q-12 y equivalentes)
  indicando explícitamente la ausencia de datos, sin inventar una cifra y sin propagar un error
  no controlado.
- **FR-006**: El sistema MUST tratar cada invocación como un turno independiente, sin conservar
  ni usar contexto de preguntas anteriores (arquitectura stateless de la constitución).
- **FR-007**: El sistema MUST registrar cada invocación con, como mínimo: timestamp, pregunta,
  SQL generado, respuesta, tokens de entrada/salida, coste estimado, latencia y estado
  (éxito/sin datos/error).
- **FR-008**: El sistema MUST leer las credenciales de Snowflake y del endpoint de Cortex desde
  variables de entorno, reutilizando el mecanismo ya existente en `src/conversational_analytics/db.py`
  (Principio V), sin credenciales embebidas en código.
- **FR-009**: El sistema MUST devolver un mensaje de fallo de servicio, no una respuesta
  inventada, cuando Cortex Analyst no responde o responde con error.
- **FR-010**: El conjunto de tests de evaluación del agente (Principio II) MUST cubrir las 12
  preguntas del catálogo de referencia con asserts explícitos por pregunta, y MUST escribirse
  antes de la implementación del agente.

### Key Entities

- **Pregunta**: texto en lenguaje natural recibido por el agente. No lleva estado de
  conversaciones anteriores.
- **Respuesta**: texto en lenguaje natural devuelto al usuario, más los datos subyacentes
  (valor(es) numérico(s), filas) usados para construirla.
- **Registro de invocación**: evento de telemetría de una pregunta-respuesta: pregunta, SQL
  generado, respuesta, tokens, coste, latencia, estado, timestamp. Es la base del Principio IV;
  el destino final (tabla de Snowflake) y su modelo de datos se definen en el plan.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El agente responde correctamente (valor coincide con la aserción del catálogo) a
  las 11 preguntas satisfacibles del catálogo de referencia (Q-01 a Q-11).
- **SC-002**: El agente indica ausencia de datos, y no un error ni una cifra inventada, para
  Q-12 y para al menos un caso adicional de pregunta fuera de dominio.
- **SC-003**: El 100% de las invocaciones del agente en la suite de evaluación quedan
  registradas con los campos mínimos de FR-007, verificable por consulta SQL directa.
- **SC-004**: Una persona sin conocimientos previos del repositorio puede explicar el flujo
  completo de una pregunta (entrada → semantic view → respuesta) en menos de cinco minutos,
  usando únicamente el código y el plan de esta feature (Principio I).

## Assumptions

- El "agente" de esta feature es un **agente de un solo turno, sin memoria de conversación**,
  tal y como exige el Principio I de la constitución como primera arquitectura; no se
  implementa gestión de sesión ni historial multi-turno.
- El canal de invocación concreto (CLI, función Python, endpoint HTTP) se decide en el plan;
  esta spec no lo fija porque no cambia el valor de negocio ni los criterios de aceptación.
- El destino de la telemetría (FR-007) es una tabla en Snowflake, coherente con el Principio IV
  ("la telemetría MUST almacenarse en Snowflake"); su esquema exacto se define en el plan.
- Las 12 preguntas de [reference-questions.md](../001-mock-sales-dataset/contracts/reference-questions.md)
  siguen siendo el catálogo de evaluación vigente; esta feature no añade preguntas nuevas al
  catálogo, solo lo usa para validar el agente.
- El idioma de entrada esperado es español (equipo y demo son en español), aunque la semantic
  view expone metadatos en inglés (decisión D-09 de la feature 002); Cortex Analyst se encarga
  de esa traducción implícita.

# Research: Semantic View de ventas para Cortex Analyst

**Feature**: `002-cortex-semantic-view` | **Fecha**: 2026-09-01 | **Fase**: 0

Fuente primaria: documentación oficial de Snowflake sobre `CREATE SEMANTIC VIEW` y semantic
views ([sql-reference/sql/create-semantic-view](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view),
[user-guide/views-semantic/sql](https://docs.snowflake.com/en/user-guide/views-semantic/sql)),
consultada el 2026-09-01. No se ha inventado ninguna cláusula.

## D-01: `CREATE OR ALTER` frente a `CREATE OR REPLACE`

**Decision**: Usar `CREATE OR ALTER SEMANTIC VIEW`.

**Rationale**: `CREATE OR ALTER` crea el objeto si no existe o lo modifica in-place si ya
existe; a diferencia de `CREATE OR REPLACE`, **preserva los grants existentes** sin necesitar
`COPY GRANTS`, y dos despliegues consecutivos con la misma definición no producen cambio
alguno (idempotencia real). Encaja con el Principio III de la constitución (todo despliegue
reversible y repetible) y con FR-010 / SC-004 de la spec.

**Alternatives considered**: `CREATE OR REPLACE SEMANTIC VIEW ... COPY GRANTS` — funciona pero
recrea el objeto en cada despliegue (menos "idempotente" en espíritu) y exige acordarse de
`COPY GRANTS` cada vez. Rechazada por ser menos robusta ante el mismo objetivo.

## D-02: Nombres de tablas lógicas y alias

**Decision**: Alias de negocio **en inglés** para las tablas lógicas: `PRODUCT AS DIM_PRODUCT`,
`COUNTRY AS DIM_COUNTRY`, `SALE AS FACT_SALES`. Objeto renombrado a `SV_PHARMA_SALES`.

**Rationale**: FR-006 exige nombres y descripciones en lenguaje de negocio; una decisión
posterior del usuario (2026-09-01, ver D-09) fija que ese lenguaje de negocio es **inglés** en
todo lo que ve o pregunta el agente (nombres, sinónimos, `AI_VERIFIED_QUERIES`), reservando el
español para la documentación del repositorio. La sintaxis permite `table_alias AS
table_name`; una vez fijado el alias, todas las relaciones, facts, dimensiones y métricas se
referencian por el alias, nunca por el nombre físico. Los sinónimos (`WITH SYNONYMS`) son solo
informativos y no sirven para referenciar la tabla en el resto del DDL — por eso el alias en sí
ya debe ser el nombre de negocio en inglés.

**Alternatives considered**: Mantener los nombres físicos (`DIM_PRODUCT`, `DIM_COUNTRY`,
`FACT_SALES`) como alias y delegar todo en sinónimos. Rechazada: los nombres físicos son
prefijos técnicos (`DIM_`, `FACT_`) que no aportan a alguien de negocio. También se consideró
usar alias en español (`PRODUCTO`, `PAIS`, `VENTA`, diseño inicial de esta fase) — descartada
tras la aclaración del usuario de que el agente y sus preguntas operan en inglés.

## D-03: Separación FACTS vs. METRICS

**Decision**: Definir primero **FACTS** como expresiones a nivel de fila (sin agregar) —
unidades, importe bruto, importe de descuento, importe neto — y después **METRICS** como
agregaciones (`SUM`, `AVG`) de esos facts.

**Rationale**: Es el patrón que usa la propia documentación de Snowflake (ejemplo
`line_items.discounted_price AS l_extendedprice * (1 - l_discount)` como FACT, seguido de
métricas que lo agregan). Los facts son los "bloques" reutilizables; las métricas son lo que de
verdad se expone como KPI de negocio y lo que aparece en `AI_VERIFIED_QUERIES`. Permite además
definir `SALE.NET_AMOUNT` (bruto − descuento) una sola vez y reutilizarlo en dos métricas
(`NET_SALES` con `SUM`, `AVG_NET_SALES` con `AVG`) sin repetir la resta.

**Alternatives considered**: Definir las ventas netas directamente como métrica
(`SUM(GROSS_SALES_EUR - DISCOUNT_EUR)`) sin fact intermedio. Funciona igual de bien para un
único agregado, pero obliga a repetir la expresión si se quiere también la media; se rechaza
por duplicación.

## D-04: Métrica de negocio por defecto para "sales" (FR-012)

**Decision**: El sinónimo `'sales'` (y su equivalente `'revenue'`) se asigna
**únicamente** a la métrica `SALE.NET_SALES`. La métrica `SALE.GROSS_SALES` solo lleva
sinónimos que mencionan explícitamente "gross" (`'gross sales'`, `'gross revenue'`).

**Rationale**: Cortex Analyst resuelve una pregunta ambigua hacia la métrica cuyo nombre o
sinónimo coincide mejor con los términos de la pregunta. Si ambas métricas llevasen `'sales'`
como sinónimo, la resolución sería ambigua — justo lo que FR-012 prohíbe. Excluir la palabra
suelta "sales" de la métrica bruta fuerza la resolución hacia la neta salvo que la pregunta
cualifique explícitamente "gross".

**Alternatives considered**: Usar `AI_QUESTION_CATEGORIZATION` para instruir explícitamente
"si la pregunta dice ventas sin más, usa ventas netas". Válido y complementario, pero se
descarta añadir esa cláusula extra en esta primera versión: el diseño de sinónimos ya resuelve
el caso sin ampliar la superficie del DDL (Principio I). Queda anotado como posible mejora
futura, no bloqueante.

## D-05: Dimensiones de dominio cerrado con `IS_ENUM` / `SAMPLE_VALUES`

**Decision**: Marcar `THERAPEUTIC_AREA`, `BUSINESS_UNIT`, `REGION` y `CHANNEL` con
`SAMPLE_VALUES (...)` seguido de `IS_ENUM`, listando los valores exactos y completos del
dominio cerrado (documentados en
[data-model.md de la feature 001](../001-mock-sales-dataset/data-model.md)).

**Rationale**: La documentación de Snowflake indica que `SAMPLE_VALUES` ayuda a Cortex Analyst
a generar SQL más preciso, y que `IS_ENUM` le dice que esos son **todos** los valores posibles,
de forma que solo filtrará por esos valores exactos. Esto reduce el riesgo de que el modelo
invente un valor de filtro que no existe (alineado con FR-009: cero errores, cero cifras
inventadas). No se aplica a `BRAND` ni a `COUNTRY_NAME`: son dominios abiertos/enumerables pero
no "cerrados" en el mismo sentido de negocio (aunque de hecho son 12 y 10 valores fijos, se
tratan como catálogos, no como enumeraciones estilo estado/categoría).

**Alternatives considered**: No usar `IS_ENUM` en ningún caso. Rechazada: la documentación es
explícita en que mejora la precisión de filtrado, que es exactamente el objetivo de SC-001.

## D-06: Métrica derivada para la tasa de descuento (Q-07)

**Decision**: Definir una métrica derivada **sin tabla lógica** (`AVG_DISCOUNT_RATE AS
DIV0(SALE.DISCOUNT, SALE.GROSS_SALES)`), combinando dos métricas ya agregadas.

**Rationale**: La documentación permite "derived metrics" que combinan métricas de distintas
tablas lógicas (o, como aquí, de la misma) mediante una expresión escalar sin volver a agregar.
`DIV0` evita división por cero (aunque no debería ocurrir, dado que `GROSS_SALES_EUR > 0`
siempre, por el contrato del dataset). Una métrica derivada se define omitiendo el alias de
tabla, tal como exige la sintaxis.

**Alternatives considered**: Calcular la tasa como una `DIMENSIONS` con expresión por fila
(`DISCOUNT_EUR / GROSS_SALES_EUR`) y promediarla con `AVG` como métrica. Rechazada: promediar
una razón por fila (media de razones) no es lo mismo que la razón de las sumas totales
(razón de medias), y la pregunta de referencia Q-07 pide el segundo cálculo (descuento total
entre ventas brutas totales del grupo).

## D-07: Ejes temporales derivados (año y trimestre)

**Decision**: Añadir dos dimensiones derivadas directamente de la columna física
`SALE_MONTH`: `SALE.YEAR AS YEAR(SALE_MONTH)` y `SALE.QUARTER AS QUARTER(SALE_MONTH)`,
además de la dimensión base `SALE.MONTH AS SALE_MONTH`.

**Rationale**: El dataset no tiene tabla de calendario (ver contrato del dataset); el grano
nativo es mensual. Preguntas como "ventas netas por región en el cuarto trimestre de 2025"
(Q-08) o comparativas por año (Q-01, Q-04, Q-10) necesitan poder agrupar/filtrar por año y
trimestre sin que Cortex Analyst tenga que inventar la expresión `YEAR(...)` por su cuenta.
Es exactamente el patrón que usa el ejemplo oficial (`orders.order_year AS YEAR(o_orderdate)`).

**Alternatives considered**: Dejar que Cortex Analyst derive año/trimestre él mismo a partir de
`SALE.MONTH` en tiempo de consulta. Rechazada: es menos fiable y no está garantizado que el
modelo use siempre la misma expresión; definirlo una vez en el modelo semántico es más robusto
y barato de mantener.

## D-08: Formato y alcance de `AI_VERIFIED_QUERIES`

**Decision**: El texto `QUESTION` de cada verified query se escribe **en inglés** (D-09). El
`SQL` se escribe como una consulta directa, autocontenida y ejecutable contra las tablas
físicas (`CICD_DEMO.DATA.FACT_SALES`, `DIM_PRODUCT`, `DIM_COUNTRY`, totalmente cualificadas),
replicando el cálculo de ventas netas (`GROSS_SALES_EUR - DISCOUNT_EUR`) ya usado por
`specs/001-mock-sales-dataset/contracts/reference-questions.md` y por
`tests/test_reference_questions.py` (ese catálogo se mantiene en español: es documentación de
test, no se despliega a Snowflake). Se omite la cláusula opcional `VERIFIED_BY` (requiere un
objeto `CONTACT` de Snowflake que no existe en este proyecto) y se fija `VERIFIED_AT` a un
timestamp único (época Unix del día de creación de la feature) para reproducibilidad.

**Rationale**: La cláusula `SQL` de una verified query exige únicamente "una consulta SQL que
devuelve la respuesta a la pregunta" — no exige que la consulta pase por la sintaxis
`SELECT * FROM SEMANTIC_VIEW(...)`. Escribirla contra las tablas físicas garantiza que es
válida y ejecutable de forma independiente (se puede probar con `EXPLAIN` o ejecutándola
directamente), y reutiliza exactamente la misma lógica de cálculo que ya está probada en la
feature 001, evitando divergencias entre "lo que dice el test" y "lo que dice la semantic
view". `VERIFIED_BY` requeriría crear infraestructura de contactos solo para esta feature, lo
que viola el Principio I (simplicidad) sin aportar valor a la demo.

**Alternatives considered**: Escribir el `SQL` usando los nombres lógicos del modelo semántico
(p. ej. `SELECT sale.net_sales ... FROM sale`), imitando literalmente el ejemplo de la
documentación de TPC-H. Rechazada por riesgo: la documentación no explica de forma inequívoca
si esa sintaxis se resuelve como una vista implícita sobre el modelo semántico o si es un atajo
del ejemplo; escribir SQL directo contra las tablas físicas elimina esa ambigüedad y es
verificable con el mismo mecanismo de test que ya usa el proyecto.

## D-09: Idioma de los identificadores frente al idioma de la documentación

**Decision** (2026-09-01, refinamiento posterior a la primera versión de esta fase): los
nombres de tablas lógicas, dimensiones, facts, métricas, sinónimos y el texto `QUESTION` de
`AI_VERIFIED_QUERIES` se escriben **en inglés**. La documentación de este repositorio
(`spec.md`, `plan.md`, `research.md`, `data-model.md`, comentarios de commit, etc.) se sigue
redactando **en español**, incluidos los `COMMENT` del DDL, que son descripciones de negocio
dirigidas a quien mantiene el repositorio — se escriben también en inglés porque viajan dentro
del propio artefacto que Cortex Analyst expone al agente, no como documentación del repo.

**Rationale**: El usuario indicó explícitamente que el agente, sus preguntas y los
identificadores de la plataforma conversacional operan en inglés, mientras que el trabajo de
repositorio (specs, planes, commits) se mantiene en español. Esto también resuelve una
inconsistencia previa: los valores de dominio ya estaban en inglés (`Hospital`, `Human Pharma`,
`Cardiometabolic`...), así que nombrar las tablas/columnas en español mezclaba dos idiomas
dentro del mismo objeto.

**Alternatives considered**: Sinónimos bilingües (español + inglés), descartados explícitamente
por el usuario para evitar ambigüedad de resolución y mantener el modelo más simple (Principio
I). Traducir también `reference-questions.md` de la feature 001 — descartado porque ese
catálogo es documentación de test ya cerrada, no se despliega en Snowflake ni lo ve el agente.

## Resumen de decisiones

| # | Decisión | Requisito que satisface |
|---|---|---|
| D-01 | `CREATE OR ALTER SEMANTIC VIEW` | FR-010, SC-004 |
| D-02 | Alias de negocio en inglés para tablas lógicas | FR-006 |
| D-03 | FACTS (fila) → METRICS (agregado) | FR-005 |
| D-04 | "sales" sin cualificar → sinónimo solo en la métrica neta | FR-012, SC-003 |
| D-05 | `IS_ENUM` + `SAMPLE_VALUES` en dominios cerrados | FR-009 |
| D-06 | Métrica derivada para tasa de descuento | Q-07 (User Story 3) |
| D-07 | Dimensiones derivadas de año y trimestre | Q-01, Q-04, Q-08, Q-10 |
| D-08 | `AI_VERIFIED_QUERIES` con pregunta en inglés y SQL directo sobre tablas físicas | FR-008 |
| D-09 | Identificadores/sinónimos/preguntas en inglés; documentación del repo en español | Aclaración del usuario, 2026-09-01 |


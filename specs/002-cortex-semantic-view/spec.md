# Feature Specification: Semantic View de ventas para Cortex Analyst

**Feature Branch**: `002-cortex-semantic-view`

**Created**: 2026-09-01

**Status**: Draft

**Input**: User description: "Crea una Semantic View en Snowflake para que Cortex Analyst pueda
responder preguntas de negocio sobre mis datos. Analiza las tablas disponibles y sus
relaciones, identifica tablas lógicas, dimensiones, facts y métricas, define correctamente los
joins, añade nombres y descripciones claras orientadas a negocio, incluye sinónimos, define las
métricas principales, genera el SQL con CREATE OR ALTER SEMANTIC VIEW, añade
AI_VERIFIED_QUERIES representativas, sin inventar columnas ni relaciones. Debe quedar
preparada para ser consumida posteriormente por Cortex Analyst desde una tool de OpenAI
Agents SDK."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Responder preguntas agregadas y filtradas sobre ventas (Priority: P1)

Una persona de negocio (sin conocer los nombres de tablas ni columnas) pregunta en lenguaje
natural por cifras de ventas totales, unidades o descuentos, filtrando por producto, marca,
país, canal o periodo de tiempo, y obtiene una cifra correcta sin necesidad de escribir SQL.

**Why this priority**: Es el caso de uso mínimo que justifica la existencia de la semantic
view: sin agregación y filtrado correctos por las dimensiones básicas, no hay demo que enseñar.

**Independent Test**: Se puede probar de forma aislada ejecutando contra la semantic view el
equivalente de las preguntas Q-01, Q-02, Q-08, Q-10 y Q-12 del
[catálogo de referencia](../001-mock-sales-dataset/contracts/reference-questions.md) y
comprobando que el resultado numérico coincide con el de la consulta SQL directa sobre las
tablas base (o, en el caso de Q-12, que no hay filas).

**Acceptance Scenarios**:

1. **Given** la semantic view desplegada, **When** se pregunta por las ventas netas totales de
   un año dentro del histórico (2023-2025), **Then** se obtiene un único número que coincide
   con `SUM(GROSS_SALES_EUR - DISCOUNT_EUR)` para ese año.
2. **Given** la semantic view desplegada, **When** se pregunta por unidades vendidas de una
   marca concreta en un país y año concretos, **Then** se obtiene un único entero que coincide
   con el filtro equivalente sobre `FACT_SALES` unido a `DIM_PRODUCT` y `DIM_COUNTRY`.
3. **Given** la semantic view desplegada, **When** se pregunta por un año fuera del histórico
   (p. ej. 2021), **Then** la respuesta indica que no hay datos, nunca un error ni una cifra
   inventada.

---

### User Story 2 - Comparar y rankear entre dimensiones de negocio (Priority: P2)

Una persona de negocio pide comparativas entre categorías (unidad de negocio, región, área
terapéutica) o un ranking top-N (marcas, países), y la semantic view calcula correctamente la
métrica agregada por grupo y la ordena.

**Why this priority**: Depende de que la P1 funcione, pero añade valor real de analista:
comparar y priorizar es más útil que una sola cifra suelta.

**Independent Test**: Se puede probar de forma aislada con las preguntas Q-03, Q-04, Q-05 y
Q-09 del catálogo de referencia, comprobando número de filas, ausencia de empates y orden
correcto.

**Acceptance Scenarios**:

1. **Given** la semantic view desplegada, **When** se pide el top 5 de marcas por ventas netas
   en una región, **Then** se devuelven 5 marcas con valores distintos en orden descendente.
2. **Given** la semantic view desplegada, **When** se pide comparar dos unidades de negocio en
   un año, **Then** se devuelve una fila por unidad de negocio, ambas con ventas netas `> 0`.
3. **Given** la semantic view desplegada, **When** se pregunta qué área terapéutica creció más
   entre dos años, **Then** se devuelve una única área con la variación calculada.

---

### User Story 3 - Preguntar con métricas derivadas y series temporales (Priority: P3)

Una persona de negocio pregunta por métricas que no son una suma directa (tasa de descuento,
media mensual) o pide la evolución mes a mes de una combinación de producto y país.

**Why this priority**: Es la capa más sofisticada del modelo semántico: métricas calculadas y
series temporales sin huecos. Aporta valor pero no es indispensable para la primera demo.

**Independent Test**: Se puede probar de forma aislada con las preguntas Q-06, Q-07 y Q-11 del
catálogo de referencia, comprobando el número de filas esperado (p. ej. 12 meses sin huecos) y
que los ratios calculados están en el rango válido (0-40% de descuento).

**Acceptance Scenarios**:

1. **Given** la semantic view desplegada, **When** se pide la evolución mensual de unidades de
   una marca en un país durante un año, **Then** se devuelven 12 filas, una por mes, sin huecos.
2. **Given** la semantic view desplegada, **When** se pregunta en qué canal el descuento medio
   como porcentaje de las ventas brutas es mayor, **Then** se devuelve un único canal con un
   ratio entre 0 y 0.40.

### Edge Cases

- Pregunta por un producto, marca o país que no existe en el catálogo → cero filas, no error.
- Pregunta por un periodo total o parcialmente fuera del histórico 2023-01 a 2025-12 → cero
  filas para la parte fuera de rango, no error ni cifra inventada.
- Pregunta que combina dimensiones sin especificar agregación (p. ej. "ventas por canal y área
  terapéutica") → el modelo debe agregar al grano correcto sin duplicar filas por el grano
  mensual real de `FACT_SALES`.
- Pregunta por una métrica de negocio no cubierta por el modelo (p. ej. "cuota de mercado") →
  fuera de alcance; el modelo no debe inventar una métrica no derivable de las columnas
  existentes.
- Pregunta que usa "sales" o un sinónimo ("revenue") sin especificar que son
  brutas ("gross") → el modelo MUST resolverla hacia ventas netas por defecto (FR-012), nunca
  hacia ambas cifras a la vez ni dejando la métrica sin resolver.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST exponer un modelo semántico de negocio sobre las tablas de
  ventas (`DIM_PRODUCT`, `DIM_COUNTRY`, `FACT_SALES` en `CICD_DEMO.DATA`) que permita responder
  preguntas en lenguaje natural sin que quien pregunta conozca nombres de tablas o columnas.
- **FR-002**: El modelo MUST identificar `FACT_SALES` como la tabla de hechos (grano mes ×
  producto × país × canal) y `DIM_PRODUCT` y `DIM_COUNTRY` como dimensiones, sin inventar
  ninguna tabla, columna o relación que no exista en el esquema físico.
- **FR-003**: El modelo MUST definir los joins entre el hecho y las dimensiones usando
  exactamente las claves foráneas ya declaradas (`FACT_SALES.PRODUCT_ID` →
  `DIM_PRODUCT.PRODUCT_ID`, `FACT_SALES.COUNTRY_CODE` → `DIM_COUNTRY.COUNTRY_CODE`).
- **FR-004**: El modelo MUST exponer como dimensiones de negocio, como mínimo: marca, área
  terapéutica, unidad de negocio (del producto); país y región (del país); canal y el eje
  temporal mensual (del hecho).
- **FR-005**: El modelo MUST exponer como métricas de negocio, como mínimo: unidades vendidas,
  ventas brutas, descuento y ventas netas (esta última derivada como ventas brutas menos
  descuento, nunca almacenada).
- **FR-006**: El modelo MUST incluir nombres y descripciones en lenguaje de negocio **en
  inglés** (no nombres técnicos de columna ni abreviaturas de esquema) para cada tabla lógica,
  dimensión y métrica, dado que las preguntas del agente y el resto de la plataforma operan en
  inglés.
- **FR-007**: El modelo MUST incluir sinónimos de negocio habituales **en inglés** (p. ej.
  "revenue" para sales, "discount" para discount, "brand" para brand) que ayuden a
  interpretar preguntas formuladas de distintas maneras.
- **FR-008**: El sistema MUST incluir un conjunto de preguntas verificadas representativas
  (una por cada pregunta en rango del catálogo de referencia, Q-01 a Q-11) para mejorar la
  precisión de las respuestas de Cortex Analyst.
- **FR-009**: El sistema MUST responder con "no hay datos" (cero filas), nunca con un error ni
  con una cifra inventada, ante preguntas fuera del histórico o sobre valores inexistentes
  (mismo contrato que las tablas base, ver
  [dataset-contract.md](../001-mock-sales-dataset/contracts/dataset-contract.md)).
- **FR-010**: El artefacto de la semantic view MUST vivir versionado en Git y desplegarse de
  forma idempotente (recrear o alterar el objeto sin dejar el esquema en un estado distinto al
  definido en el fichero), siguiendo el mismo patrón que las tablas de la feature
  `001-mock-sales-dataset`.
- **FR-011**: El modelo semántico MUST quedar estructurado para ser invocado como fuente de
  datos por una herramienta externa (una tool que use Cortex Analyst desde el OpenAI Agents
  SDK), sin que dicha herramienta necesite conocer el SQL subyacente ni los nombres físicos de
  columna.
- **FR-012**: Ante una pregunta que use "sales" o cualquiera de sus sinónimos de negocio
  ("revenue") sin especificar explícitamente "gross", el modelo MUST resolverla
  hacia la métrica de ventas netas ("net sales"). Sólo cuando la pregunta mencione
  explícitamente "gross" (o sinónimo equivalente) MUST resolverse hacia ventas brutas.

### Key Entities

- **Producto / `PRODUCT` (tabla lógica dimensión)**: representa el catálogo de productos
  vendidos. Atributos de negocio relevantes: marca (`BRAND`), área terapéutica
  (`THERAPEUTIC_AREA`) y unidad de negocio (`BUSINESS_UNIT`) a la que pertenece. Corresponde a
  `DIM_PRODUCT`.
- **Mercado / País / `COUNTRY` (tabla lógica dimensión)**: representa los países donde se
  vende. Atributos de negocio relevantes: nombre del país (`COUNTRY_NAME`) y región comercial
  (`REGION`) a la que pertenece. Corresponde a `DIM_COUNTRY`.
- **Venta mensual / `SALE` (tabla lógica de hechos)**: representa la actividad de ventas al
  grano mes × producto × país × canal. Atributos de negocio relevantes: mes (`MONTH`), canal de
  venta (`CHANNEL`), unidades vendidas, ventas brutas y descuento; relacionada con `PRODUCT` y
  con `COUNTRY`. Corresponde a `FACT_SALES`.

> Los nombres entre backticks son los identificadores en inglés que usará el modelo semántico
> (ver [plan.md](./plan.md)); la narrativa de este documento se mantiene en español.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Las 11 preguntas en rango del catálogo de referencia (Q-01 a Q-11) obtienen,
  a través del modelo semántico, el mismo resultado numérico que su consulta SQL equivalente
  sobre las tablas base.
- **SC-002**: La pregunta fuera de rango del catálogo (Q-12) devuelve cero filas a través del
  modelo semántico, nunca un error.
- **SC-003**: El 100% de los sinónimos de negocio definidos (en inglés) resuelve sin
  ambigüedad a una única dimensión o métrica del modelo, incluyendo que "sales" (y sus
  sinónimo "revenue") sin más especificación resuelve siempre a ventas netas
  ("net sales").
- **SC-004**: Volver a desplegar el artefacto de la semantic view sobre un esquema ya
  desplegado no produce diferencias de definición (recuento de tablas lógicas, dimensiones,
  métricas y joins idéntico antes y después).
- **SC-005**: Cero columnas o relaciones del modelo semántico son ajenas al esquema físico
  documentado en
  [data-model.md](../001-mock-sales-dataset/data-model.md): toda dimensión, métrica y join
  del modelo traza a una columna o clave real de `DIM_PRODUCT`, `DIM_COUNTRY` o `FACT_SALES`.

## Assumptions

- El modelo semántico se construye directamente sobre las tres tablas físicas ya desplegadas
  por la feature `001-mock-sales-dataset`; esta feature no crea columnas ni tablas nuevas.
- Se crea una única semantic view (una sola perspectiva de negocio), no varias vistas
  alternativas.
- La moneda es siempre euros, igual que en el contrato del dataset; no se expone dimensión de
  divisa.
- El eje temporal expuesto tiene grano nativo mensual (`SALE_MONTH`); agregaciones a trimestre
  o año se resuelven sobre ese grano, sin tabla de calendario adicional.
- Los nombres de tablas lógicas, dimensiones, métricas, sus sinónimos y las preguntas de
  `AI_VERIFIED_QUERIES` están **en inglés** (igual que los valores ya presentes en los datos,
  p. ej. "Hospital", "Retail Pharmacy", "Human Pharma", y que el resto de la plataforma
  conversacional). La documentación de este repositorio (specs, plan, comentarios de PR, etc.)
  se sigue redactando en español; solo el artefacto orientado al agente y a quien lo consulta
  usa inglés.
- La integración real con la tool del OpenAI Agents SDK y el agente conversacional es una
  feature futura y queda fuera de alcance aquí: esta feature entrega y valida únicamente el
  artefacto de la semantic view.
- El acceso y despliegue de la semantic view usa el mismo rol (`CICD_DEMO_ROLE`) y warehouse
  (`COMPUTE_WH`) que las tablas base, sin permisos adicionales.
- "Ventas netas" (`NET_SALES`) es la métrica de negocio por defecto: cualquier pregunta que
  diga "sales" o un sinónimo ("revenue") sin cualificar "gross" se resuelve hacia
  ventas netas.

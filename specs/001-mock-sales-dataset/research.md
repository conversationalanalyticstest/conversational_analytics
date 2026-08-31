# Research: Dataset mock de ventas farma

**Feature**: `001-mock-sales-dataset` | **Fecha**: 2026-08-31 | **Fase**: 0

Decisiones técnicas previas al diseño. Cada una resuelve una incógnita del contexto técnico
del [plan](plan.md).

---

## D-01: Cómo generar datos deterministas

**Decisión**: fórmula aritmética determinista sobre los índices de la propia fila
(producto, país, canal, mes). **Cero aleatoriedad.**

**Rationale**:

- FR-017 exige determinismo estricto: dos cargas producen exactamente los mismos valores.
- `RANDOM(seed)` de Snowflake garantiza la misma *secuencia* de valores con la misma semilla,
  pero **no garantiza la asociación de cada valor a cada fila** entre ejecuciones, porque el
  reparto depende de la paralelización. Es decir, `RANDOM(seed)` **no es reproducible a nivel
  de fila**. Descartado.
- `HASH()` sí es determinista dentro de una versión de Snowflake, pero la documentación no
  garantiza estabilidad del algoritmo entre releases. Un cambio de release rompería los
  resultados esperados de los tests sin que nadie tocara el repositorio. Descartado.
- Una fórmula aritmética (producto de factores + un término de ruido por módulo) es
  determinista por construcción, independiente del motor, y se explica en 30 segundos ante
  una audiencia — que es exactamente lo que pide el Principio I.

**Alternativas consideradas**:

| Alternativa | Rechazada porque |
|---|---|
| `RANDOM(seed)` | No reproducible a nivel de fila (ver arriba) |
| `HASH()` como pseudo-aleatorio | Estabilidad no garantizada entre releases de Snowflake |
| Generar el CSV con Python/Faker y cargarlo | Añade dependencia, un artefacto binario/CSV al repo y un paso de carga. Más piezas que explicar, ningún beneficio |
| Fichero SQL con 12.960 `INSERT` literales | Ilegible, imposible de revisar en PR, imposible de ajustar |

---

## D-02: Índice de mes sin `SEQ4()` directo

**Decisión**: `ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1` sobre `GENERATOR(ROWCOUNT => 36)`.

**Rationale**: la documentación de Snowflake advierte de que `SEQ4()` **puede tener huecos**;
no garantiza una secuencia densa 0..N-1. Envolverlo en `ROW_NUMBER()` fuerza una secuencia
densa y ordenada, que es lo que necesita FR-010 (36 meses consecutivos sin huecos).

**Alternativas consideradas**: usar `SEQ4()` directamente (rechazado: riesgo de huecos);
tabla de calendario materializada (rechazado: entidad extra, prohibida por la spec).

---

## D-03: Idempotencia — DDL y datos separados

**Decisión**: dos scripts. `002_tables.sql` con `CREATE OR REPLACE TABLE` (estructura);
`003_seed.sql` con `TRUNCATE` + `INSERT ... SELECT` (datos).

**Rationale**:

- `CREATE OR REPLACE` hace que la estructura **converja siempre** a lo declarado en Git, que
  es justo la tesis de la demo (Principio III: Git es la fuente de verdad). Si mañana se añade
  una columna, basta editar el fichero y volver a desplegar.
- Separar estructura de datos permite recargar los datos sin recrear las tablas, y hace que en
  la demo se distinga con claridad "cambio de esquema" de "cambio de datos".
- `TRUNCATE` + `INSERT` es idempotente y trivial de leer (FR-018).

**Nota sobre permisos**: `002` y `003` se ejecutan con `CICD_DEMO_ROLE`, que tiene
`CREATE TABLE` sobre `CICD_DEMO.DATA` (concedido en `001_bootstrap.sql`) y por tanto **es
propietario** de las tablas que crea. No hacen falta grants adicionales de `SELECT`, ni
`GRANT ... ON FUTURE TABLES`. No es necesario tocar `001_bootstrap.sql`.

**Alternativas consideradas**:

| Alternativa | Rechazada porque |
|---|---|
| Un único script `CREATE OR REPLACE TABLE ... AS SELECT` | Mezcla estructura y datos; no se puede recargar sin recrear ni cambiar el esquema sin regenerar |
| `CREATE TABLE IF NOT EXISTS` | No converge: un cambio de columnas en Git no se aplicaría nunca al entorno ya desplegado. Rompe el Principio III |
| `MERGE` para carga incremental | Innecesario: el dataset es fijo y pequeño. Complejidad sin beneficio |

---

## D-04: Ventas netas derivadas, no almacenadas

**Decisión**: `FACT_SALES` almacena `UNITS_SOLD`, `GROSS_SALES_EUR` y `DISCOUNT_EUR`. Las
ventas netas **no se almacenan**: se derivan como `GROSS_SALES_EUR - DISCOUNT_EUR`.

**Rationale**:

- FR-012 enumera las tres columnas físicas; FR-013 dice que el neto debe ser *derivable*.
- Almacenarlo introduce una columna redundante que puede desincronizarse. Derivarlo hace que
  la invariante sea cierta por construcción.
- Da a la futura semantic view una métrica calculada real que enseñar, en vez de un simple
  `SUM` de columna.

**Alternativas consideradas**: columna física calculada en el `INSERT` (rechazada: redundante);
columna virtual de Snowflake (rechazada: sintaxis extra que explicar sin ganancia).

---

## D-05: Cómo se ejecutan los scripts SQL

**Decisión**: Snowflake CLI — `snow sql -f snowflake/00X_....sql`.

**Rationale**: ya está instalado y es la herramienta que usará el pipeline de despliegue en la
feature de CI/CD. No requiere escribir código Python de despliegue ahora. Los scripts quedan
como SQL puro, legible y revisable en la PR.

**Alternativas consideradas**: script Python que lea el `.sql` y lo ejecute por el conector
(rechazado: código propio que mantener para algo que la CLI ya hace); ejecución manual en la
consola de Snowflake (**prohibido** por el Principio III).

---

## D-06: Acceso desde los tests

**Decisión**: `snowflake-connector-python` + `python-dotenv`, con un único helper
`get_connection()` en `src/conversational_analytics/db.py`.

**Rationale**:

- La constitución fija `pytest` como runner y exige tests que se ejecuten contra Snowflake.
  Hace falta un cliente Python; no hay forma de evitar la dependencia.
- Se elige el **conector** y no Snowpark: Snowpark arrastra un stack mucho mayor y aquí sólo se
  ejecutan consultas de agregación. Principio I.
- `python-dotenv` carga `.env` en local; en CI las variables vienen de GitHub Secrets y
  `dotenv` simplemente no encuentra fichero y no hace nada. Un único camino de código.
- El helper se reutilizará después por el agente y por la telemetría; no es una abstracción
  especulativa, es la única forma de no repetir la lectura de 7 variables de entorno.

**Riesgo abierto**: el venv del proyecto es **Python 3.14.6** y la máquina **no tiene
compilador C**. La resolución en seco de `snowflake-connector-python 4.7.2` para 3.14 funciona,
pero la instalación real no se ha verificado. Si fallara por falta de wheel, la mitigación es
bajar el venv a Python 3.12 (`requires-python` ya admite `>=3.11`). **A verificar en la primera
tarea de la fase de implementación, antes de escribir nada más.**

---

## D-07: Rango histórico fijo, no relativo

**Decisión**: `2023-01-01` a `2025-12-01`, constante en el SQL.

**Rationale**: si el rango fuese relativo a `CURRENT_DATE`, los resultados esperados de los
tests cambiarían solos cada mes y la suite se volvería inestable — inaceptable para el
Principio II. Confirmado como asunción en la spec.

**Consecuencia asumida**: en una demo hecha en 2026, "el último año con datos" es 2025.

---

## D-08: Ordinales estables, asignados una vez y nunca renumerados

**Decisión**: el ordinal de producto sale de `TO_NUMBER(SUBSTR(PRODUCT_ID, 2))`; los de país y
canal son **literales fijos** en las listas de `003_seed.sql`. Ninguno se calcula con
`ROW_NUMBER()` sobre la tabla de dimensión.

**Rationale**:

- La fórmula de generación depende de estos ordinales. Si se derivasen del orden de la
  dimensión (`ROW_NUMBER() OVER (ORDER BY COUNTRY_CODE)`), **añadir un país renumeraría a todos
  los posteriores alfabéticamente** y cambiarían sus ventas de los tres años de histórico. En
  una demo eso genera la pregunta incómoda de "¿por qué han cambiado las ventas de Estados
  Unidos de 2023 si sólo he añadido Portugal?".
- Con ordinales fijos, ampliar el catálogo es aditivo: el país nuevo recibe el siguiente
  ordinal libre y las cifras existentes no se mueven.
- El ordinal de producto ya es estable por construcción: va codificado en el propio
  `PRODUCT_ID` (`P013` → 13), así que no necesita tratamiento especial.

**Regla de mantenimiento**: los ordinales se asignan una vez y **nunca se reutilizan ni se
renumeran**. Si se retira un país, su ordinal queda vacante; no se reasigna.

**Coste asumido**: la lista de países de `003_seed.sql` lleva una columna de ordinal que no
existe en `DIM_COUNTRY`. Es una columna auxiliar de generación, visible sólo en el script.

**Alternativas consideradas**:

| Alternativa | Rechazada porque |
|---|---|
| `ROW_NUMBER()` sobre la dimensión | Añadir una fila reescribe el histórico de las demás (ver arriba) |
| Columna `ORDINAL` física en `DIM_COUNTRY` | Ensucia con un campo sin significado de negocio el modelo que verá el agente en la semantic view |
| Derivar el ordinal del código ISO (`ASCII` del par de letras) | Estable, pero puede colisionar: dos países compartirían factor y aparecerían empates en los rankings, rompiendo FR-016 |


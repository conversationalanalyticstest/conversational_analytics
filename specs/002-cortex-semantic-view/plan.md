# Implementation Plan: Semantic View de ventas para Cortex Analyst

**Branch**: `002-cortex-semantic-view` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-cortex-semantic-view/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Exponer las tres tablas físicas de `CICD_DEMO.DATA` (`DIM_PRODUCT`, `DIM_COUNTRY`, `FACT_SALES`)
a través de una única `SEMANTIC VIEW` (`SV_VENTAS_FARMA`), con tablas lógicas, dimensiones,
facts y métricas nombradas en lenguaje de negocio, sinónimos bilingües, y un conjunto de
`AI_VERIFIED_QUERIES` que cubre las 11 preguntas en rango del catálogo de referencia. El
enfoque técnico es declarativo: un único `CREATE OR ALTER SEMANTIC VIEW` idempotente,
desplegado con el mismo patrón (rol, warehouse, script numerado) que las tablas de la feature
`001-mock-sales-dataset`. No se toca ninguna tabla física ni se crea infraestructura de agente:
esta feature solo entrega y valida el artefacto semántico.

## Technical Context

**Language/Version**: SQL DDL de Snowflake (`CREATE OR ALTER SEMANTIC VIEW`); Python 3.14 sólo
para los tests que validan el artefacto (mismo patrón que `tests/test_reference_questions.py`).

**Primary Dependencies**: Snowflake Semantic Views (nativo, sin librería adicional);
`snowflake-connector-python` ya presente en el proyecto para los tests.

**Storage**: Snowflake, esquema `CICD_DEMO.DATA` (mismo esquema que las tablas base). La
semantic view es un objeto adicional en ese esquema, no una tabla nueva.

**Testing**: `pytest` contra la cuenta real de Snowflake, extendiendo el patrón de
`tests/test_reference_questions.py`: cada pregunta verificada se contrasta contra la consulta
SQL equivalente sobre las tablas base.

**Target Platform**: Snowflake (cuenta `cicd_demo`, rol `CICD_DEMO_ROLE`, warehouse
`COMPUTE_WH`).

**Project Type**: Single project — un fichero SQL declarativo más sus tests, sin nuevo código de
aplicación.

**Performance Goals**: No aplica (objeto declarativo; el coste de consulta lo determina
Cortex Analyst en tiempo de pregunta, fuera de alcance de esta feature).

**Constraints**: Debe desplegarse de forma idempotente (`CREATE OR ALTER`, no
`CREATE OR REPLACE`) para no perder grants en cada despliegue; cero columnas o relaciones
ajenas al esquema físico (FR-002, SC-005); debe poder explicarse en menos de cinco minutos
(Principio I).

**Scale/Scope**: 3 tablas lógicas, 9 dimensiones de negocio, 4 facts, 6 métricas, 11
`AI_VERIFIED_QUERIES` (una por pregunta en rango del catálogo de referencia).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principio I (Simplicidad)** — PASA. Una única semantic view, sin instrucciones
  `AI_SQL_GENERATION` / `AI_QUESTION_CATEGORIZATION` adicionales (se documentan como posible
  ampliación futura, no se añaden ahora porque no aportan a la demo). Nombres de tablas
  lógicas y métricas en español, explicables sin jerga técnica.
- **Principio II (Evaluación del agente como test)** — PASA. Los `AI_VERIFIED_QUERIES` se
  derivan 1:1 del catálogo `reference-questions.md` ya versionado; los tests que validan el
  artefacto se escriben en esta misma feature, antes de considerarla completa.
- **Principio III (CI/CD es el producto)** — PASA. El artefacto vive en Git
  (`snowflake/004_semantic_view.sql`), se despliega con `CREATE OR ALTER` (idempotente,
  reversible con `DROP SEMANTIC VIEW` + redeploy del commit anterior).
- **Principio IV (Observabilidad y coste)** — NO APLICA a esta feature: no hay invocación de
  agente todavía, solo el modelo semántico que consumirá una feature futura.
- **Principio V (Reproducibilidad y secretos)** — PASA. Mismo rol y warehouse que las tablas
  base; ninguna credencial nueva.
- **Restricción tecnológica** (semantic views versionadas en el repo) — PASA, es exactamente lo
  que exige la constitución.

Sin violaciones que requieran justificación en Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/002-cortex-semantic-view/
├── plan.md                          # This file
├── research.md                      # Phase 0 output: decisiones de sintaxis y diseño
├── data-model.md                    # Phase 1 output: modelo semántico (tablas, dims, facts, métricas)
├── quickstart.md                    # Phase 1 output: despliegue y validación manual
├── contracts/
│   ├── semantic-view-ddl.md         # DDL completo `CREATE OR ALTER SEMANTIC VIEW`
│   └── verified-queries-mapping.md  # Q-01..Q-11 → AI_VERIFIED_QUERIES
└── tasks.md                         # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
snowflake/
├── 001_bootstrap.sql        # (existente) rol y warehouse
├── 002_tables.sql           # (existente) DIM_PRODUCT, DIM_COUNTRY, FACT_SALES
├── 003_seed.sql             # (existente) carga determinista
└── 004_semantic_view.sql    # NUEVO: CREATE OR ALTER SEMANTIC VIEW SV_VENTAS_FARMA

tests/
├── conftest.py                        # (existente) fixture de conexión
├── test_dataset.py                    # (existente)
├── test_reference_questions.py        # (existente) Q-01..Q-12 contra tablas base
└── test_semantic_view.py              # NUEVO: valida la semantic view contra las mismas preguntas
```

**Structure Decision**: Se mantiene la estructura de proyecto único (Opción 1) ya usada por la
feature `001-mock-sales-dataset`: un script SQL numerado más en `snowflake/`, y un módulo de
test más en `tests/`. No se introduce ningún directorio, paquete o dependencia nueva — coherente
con el Principio I.

## Complexity Tracking

> Sin violaciones de la constitución que justificar. Tabla omitida.


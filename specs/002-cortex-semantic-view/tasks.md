---

description: "Task list template for feature implementation"
---

# Tasks: Semantic View de ventas para Cortex Analyst

**Input**: Documentos de diseño de `specs/002-cortex-semantic-view/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Incluidos y **obligatorios** (no opcionales): el Principio II de la constitución
("Evaluación del Agente como Test") exige que el artefacto se valide con tests antes de darlo
por completo, y el Constitution Check de `plan.md` ya asumió que se escriben en esta feature.

**Organization**: Las tareas están agrupadas por historia de usuario (spec.md) para poder
implementar y probar cada una de forma independiente. Como el artefacto es un único objeto
declarativo (`CREATE OR ALTER SEMANTIC VIEW`, ver D-08/D-09 en research.md), el despliegue
ocurre una sola vez en la fase Foundational; cada historia de usuario aporta y valida un
subconjunto de preguntas verificadas sobre ese mismo objeto ya desplegado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (ficheros distintos, sin dependencias)
- **[Story]**: A qué historia de usuario pertenece (US1, US2, US3)
- Cada tarea incluye la ruta de fichero exacta

## Path Conventions

Proyecto único (ver "Project Structure" en [plan.md](./plan.md)):

- `snowflake/004_semantic_view.sql` — artefacto DDL nuevo
- `tests/test_semantic_view.py` — tests nuevos
- `tests/conftest.py` — fixtures ya existentes (`sf_conn`, `fetch_one`, `fetch_all`, `scalar`),
  reutilizadas sin cambios

---

## Phase 1: Setup

**Purpose**: Preparar el fichero DDL y el módulo de test antes de desplegar nada.

- [ ] T001 Crear `snowflake/004_semantic_view.sql` copiando literalmente el bloque SQL de
      [contracts/semantic-view-ddl.md](./contracts/semantic-view-ddl.md) (desde `USE ROLE
      CICD_DEMO_ROLE;` hasta el `;` final de `AI_VERIFIED_QUERIES`), siguiendo la cabecera de
      estilo de `snowflake/002_tables.sql` (comentario de encabezado con feature y fecha).
- [ ] T002 [P] Crear `tests/test_semantic_view.py` con el docstring de módulo (qué cubre, qué
      fixtures usa, alcance), imports (`from __future__ import annotations`, `Callable`, `Any`),
      y las constantes `SCHEMA = "CICD_DEMO.DATA"` y `VIEW = "SV_PHARMA_SALES"`, sin casos de
      test todavía (se añaden en las fases de historia de usuario).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Desplegar el objeto `SEMANTIC VIEW` y confirmar su estructura. Es la única unidad
atómica de este artefacto: ninguna historia de usuario puede validarse hasta que exista.

**⚠️ CRITICAL**: Ninguna tarea de las fases 3-5 puede ejecutarse hasta completar esta fase.

- [ ] T003 Desplegar `snowflake/004_semantic_view.sql` contra `CICD_DEMO.DATA` con
      `snow sql -f snowflake/004_semantic_view.sql --connection cicd_demo` (ver paso 1 de
      [quickstart.md](./quickstart.md)).
- [ ] T004 Verificar el despliegue con `SHOW SEMANTIC VIEWS IN SCHEMA CICD_DEMO.DATA;` y
      `DESCRIBE SEMANTIC VIEW CICD_DEMO.DATA.SV_PHARMA_SALES;` (paso 2 de quickstart.md),
      confirmando 3 tablas lógicas, 2 relaciones, 4 facts, 9 dimensiones y 6 métricas (SC-005,
      ver [data-model.md](./data-model.md)).

**Checkpoint**: `SV_PHARMA_SALES` existe y tiene la estructura esperada — las historias de
usuario pueden empezar a validarse.

---

## Phase 3: User Story 1 - Responder preguntas agregadas y filtradas sobre ventas (Priority: P1) 🎯 MVP

**Goal**: Confirmar que la semantic view agrega y filtra correctamente por producto, marca,
país, canal y periodo, y que una pregunta fuera de rango devuelve "no hay datos" sin error.

**Independent Test**: Ejecutar solo `tests/test_semantic_view.py -k US1` (o los tests T005-T009)
tras completar la Fase 2 — no depende de las demás historias.

### Tests for User Story 1

> Cada test construye una consulta `SELECT * FROM SEMANTIC_VIEW(...)` usando los nombres
> lógicos del modelo (ver [data-model.md](./data-model.md)) y compara el resultado con la
> consulta SQL física equivalente ya usada en `tests/test_reference_questions.py` /
> [contracts/verified-queries-mapping.md](./contracts/verified-queries-mapping.md).

- [ ] T005 [P] [US1] Test `q01_total_net_sales_2025`: `DIMENSIONS SALE.YEAR METRICS
      SALE.NET_SALES` filtrado a `YEAR = 2025`, un único número `> 0`, en
      `tests/test_semantic_view.py`.
- [ ] T006 [P] [US1] Test `q02_units_respiralia_germany_2024`: `DIMENSIONS PRODUCT.BRAND
      METRICS SALE.UNITS_SOLD` filtrado a marca `Respiralia`, país `DE` y año 2024, un único
      entero `> 0`, en `tests/test_semantic_view.py`.
- [ ] T007 [P] [US1] Test `q08_net_sales_by_region_q4_2025`: `DIMENSIONS COUNTRY.REGION METRICS
      SALE.NET_SALES` filtrado al cuarto trimestre de 2025, 4 filas todas `> 0`, en
      `tests/test_semantic_view.py`.
- [ ] T008 [P] [US1] Test `q10_net_sales_hospital_oncology_2023`: filtro triple canal=Hospital,
      área terapéutica=Oncology, año=2023, un único número `> 0`, en
      `tests/test_semantic_view.py`.
- [ ] T009 [US1] Test de borde (equivalente a Q-12): consulta por `YEAR = 2021` (fuera del
      histórico 2023-2025) devuelve cero filas, nunca un error ni una excepción, en
      `tests/test_semantic_view.py`.

**Checkpoint**: User Story 1 queda validada de forma independiente — es el MVP demostrable.

---

## Phase 4: User Story 2 - Comparar y rankear entre dimensiones de negocio (Priority: P2)

**Goal**: Confirmar rankings top-N y comparativas categóricas sin empates y en el orden
correcto.

**Independent Test**: Ejecutar `tests/test_semantic_view.py -k US2` tras la Fase 2 (no depende
de la Fase 3, aunque reutiliza el mismo objeto ya desplegado).

### Tests for User Story 2

- [ ] T010 [P] [US2] Test `q03_top5_brands_net_sales_europe`: `DIMENSIONS PRODUCT.BRAND METRICS
      SALE.NET_SALES` filtrado a `REGION = Europe`, orden descendente, 5 filas con valores
      distintos, en `tests/test_semantic_view.py`.
- [ ] T011 [P] [US2] Test `q04_business_unit_comparison_2025`: `DIMENSIONS
      PRODUCT.BUSINESS_UNIT METRICS SALE.NET_SALES` filtrado a 2025, 2 filas ambas `> 0`, en
      `tests/test_semantic_view.py`.
- [ ] T012 [P] [US2] Test `q05_therapeutic_area_highest_growth`: comparar `SALE.NET_SALES` por
      `PRODUCT.THERAPEUTIC_AREA` entre 2024 y 2025, una única área con variación no nula, en
      `tests/test_semantic_view.py`.
- [ ] T013 [P] [US2] Test `q09_country_most_units_animal_health`: `DIMENSIONS
      COUNTRY.COUNTRY_NAME METRICS SALE.UNITS_SOLD` filtrado a `BUSINESS_UNIT = 'Animal
      Health'`, un único país entero `> 0`, en `tests/test_semantic_view.py`.

**Checkpoint**: User Stories 1 y 2 quedan validadas de forma independiente.

---

## Phase 5: User Story 3 - Preguntar con métricas derivadas y series temporales (Priority: P3)

**Goal**: Confirmar la métrica derivada de tasa de descuento y las series temporales sin
huecos.

**Independent Test**: Ejecutar `tests/test_semantic_view.py -k US3` tras la Fase 2.

### Tests for User Story 3

- [ ] T014 [P] [US3] Test `q06_monthly_evolution_cardiovex_spain_2025`: `DIMENSIONS SALE.MONTH
      METRICS SALE.UNITS_SOLD` filtrado a marca `Cardiovex`, país `ES`, año 2025 → 12 filas, una
      por mes, sin huecos, en `tests/test_semantic_view.py`.
- [ ] T015 [P] [US3] Test `q07_channel_highest_discount_rate`: `DIMENSIONS SALE.CHANNEL METRICS
      AVG_DISCOUNT_RATE` → 1 canal, ratio entre 0 y 0.40, en `tests/test_semantic_view.py`.
- [ ] T016 [P] [US3] Test `q11_avg_monthly_net_sales_per_product_latam`: `DIMENSIONS
      PRODUCT.BRAND METRICS SALE.AVG_NET_SALES` filtrado a `REGION = LATAM` → 12 filas, todas
      `> 0`, en `tests/test_semantic_view.py`.

**Checkpoint**: Las tres historias de usuario quedan validadas de forma independiente.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cerrar la feature validando idempotencia, documentación y ejecución completa.

- [ ] T017 Volver a ejecutar `snow sql -f snowflake/004_semantic_view.sql --connection
      cicd_demo` y confirmar con `DESCRIBE SEMANTIC VIEW` que la estructura (recuento de
      tablas lógicas, dimensiones, métricas y relaciones) no cambia respecto a T004 (valida
      SC-004, idempotencia de `CREATE OR ALTER`).
- [ ] T018 [P] Añadir una entrada para `004_semantic_view.sql` en `snowflake/README.md`,
      siguiendo el mismo formato que las entradas de `001_bootstrap.sql`/`002_tables.sql`/
      `003_seed.sql`.
- [ ] T019 Ejecutar `py -m pytest tests/test_semantic_view.py -v` completo y confirmar que las
      11 preguntas (T005-T016) y el caso de borde (T009) pasan (SC-001, SC-002).
- [ ] T020 Commitear `snowflake/004_semantic_view.sql` y `tests/test_semantic_view.py` con
      mensaje `implement: despliega y valida la semantic view de ventas`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — puede empezar de inmediato.
- **Foundational (Phase 2)**: Depende de Setup — BLOQUEA las tres historias de usuario.
- **User Stories (Phase 3-5)**: Todas dependen solo de Foundational; son independientes entre
  sí (pueden ejecutarse en cualquier orden o en paralelo, todas contra el mismo objeto ya
  desplegado en T003-T004).
- **Polish (Phase 6)**: Depende de que las historias que se quieran entregar estén completas.

### User Story Dependencies

- **User Story 1 (P1)**: Solo depende de Foundational. Es el MVP.
- **User Story 2 (P2)**: Solo depende de Foundational. No depende de US1.
- **User Story 3 (P3)**: Solo depende de Foundational. No depende de US1 ni de US2.

### Parallel Opportunities

- T001 y T002 (Setup) pueden ir en paralelo (ficheros distintos).
- T003 debe preceder a T004 (no son paralelos entre sí).
- Todos los tests marcados `[P]` dentro de una misma historia (T005-T008, T010-T013,
  T014-T016) pueden ejecutarse/escribirse en paralelo: son funciones independientes en el
  mismo fichero, sin dependencias entre ellas.
- Las historias de usuario completas (Phase 3, 4, 5) pueden abordarse en paralelo por personas
  distintas una vez completada la Fase 2.

---

## Parallel Example: User Story 1

```bash
# Una vez completada la Fase 2 (T003-T004), lanzar en paralelo:
Task: "Test q01_total_net_sales_2025 en tests/test_semantic_view.py"
Task: "Test q02_units_respiralia_germany_2024 en tests/test_semantic_view.py"
Task: "Test q08_net_sales_by_region_q4_2025 en tests/test_semantic_view.py"
Task: "Test q10_net_sales_hospital_oncology_2023 en tests/test_semantic_view.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Fase 1: Setup (T001-T002).
2. Completar Fase 2: Foundational (T003-T004) — despliega el único artefacto de esta feature.
3. Completar Fase 3: User Story 1 (T005-T009).
4. **STOP and VALIDATE**: `py -m pytest tests/test_semantic_view.py -k US1 -v`.
5. La semantic view ya responde el catálogo mínimo de preguntas — demostrable.

### Incremental Delivery

1. Setup + Foundational → objeto desplegado y verificado.
2. Añadir User Story 1 → validar sola → MVP demostrable.
3. Añadir User Story 2 → validar sola → rankings y comparativas.
4. Añadir User Story 3 → validar sola → métricas derivadas y series temporales.
5. Phase 6 (Polish) → idempotencia, documentación, commit final.

Cada historia añade cobertura de test sobre el mismo objeto ya desplegado, sin romper las
anteriores (no hay tabla ni columna que una historia le quite a otra).

---

description: "Task list template for feature implementation"
---

# Tasks: Dataset mock de ventas farma

**Input**: Design documents from `/specs/001-mock-sales-dataset/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: **SÍ, obligatorios.** El Principio II de la constitución es *NON-NEGOTIABLE*: los
tests se escriben **antes** del cambio que validan y deben fallar antes de implementarlo.

**Organization**: por historia de usuario, para que cada una sea entregable y verificable por
separado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: historia de usuario a la que pertenece (US1, US2, US3)
- Toda tarea indica la ruta exacta del fichero

## Path Conventions

Proyecto único: `snowflake/` para el SQL desplegable, `src/conversational_analytics/` para el
código Python, `tests/` para la suite. Rutas relativas a la raíz del repositorio.

> **Nota sobre `[P]`**: la mayoría de los tests viven en el mismo fichero
> (`tests/test_dataset.py`) y la generación entera en `snowflake/003_seed.sql`. Por eso hay
> pocas tareas paralelizables: es una consecuencia real del diseño, no un descuido.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dejar el entorno en condiciones de ejecutar `pytest` contra Snowflake.

- [X] T001 Verificar la instalación real de `snowflake-connector-python` en `.venv` (Python 3.14.6) ejecutando `poetry add snowflake-connector-python`; si falla por ausencia de wheel o por falta de compilador C, recrear `.venv` con Python 3.12 y anotar el desenlace en la sección "Riesgo abierto" de `specs/001-mock-sales-dataset/plan.md` — **BLOQUEA todo lo demás** (ver research.md D-06)
- [X] T002 Añadir `snowflake-connector-python ^4.7` y `python-dotenv ^1.2` a `[project].dependencies` en `pyproject.toml` y regenerar `poetry.lock`
- [X] T003 [P] Declarar el marker `writes_db` en `[tool.pytest.ini_options].markers` de `pyproject.toml`
- [X] T004 [P] Crear `src/conversational_analytics/db.py` con `get_connection()`: carga `.env` con `python-dotenv` si existe, lee las 7 variables `SNOWFLAKE_*` de `os.environ`, y falla con un mensaje explícito indicando cuál falta
- [X] T005 Crear `tests/conftest.py` con una fixture de sesión `sf_conn` que abra una única conexión para toda la suite, y helpers `fetch_one(sql)` / `fetch_all(sql)`
- [X] T006 Crear `tests/test_connection.py` con un smoke test que ejecute `SELECT 1` y compruebe que el rol activo es `CICD_DEMO_ROLE` y la base `CICD_DEMO`

**Checkpoint**: `poetry run pytest tests/test_connection.py` en verde. Hay conexión a Snowflake desde Python.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: estructura de las tres tablas y carga de las dos dimensiones. Sin esto, ninguna
historia puede empezar.

**⚠️ CRITICAL**: ninguna historia de usuario puede comenzar hasta completar esta fase.

- [X] T007 Escribir en `tests/test_dataset.py` los tests de dimensiones, que **DEBEN FALLAR** ahora: `test_dimension_row_counts` (12 y 10, invariante I-01), `test_no_nulls` limitado a `DIM_PRODUCT` y `DIM_COUNTRY` (I-03), `test_closed_domains` (5 áreas / 2 unidades / 4 regiones, con ≥2 productos por unidad y ≥2 países por región, I-07) y `test_launch_years_precede_history` (`MAX(LAUNCH_YEAR) < 2023`, I-08)
- [X] T008 Crear `snowflake/002_tables.sql`: `CREATE OR REPLACE TABLE` de `DIM_PRODUCT`, `DIM_COUNTRY` y `FACT_SALES` en `CICD_DEMO.DATA`, con los tipos y `NOT NULL` de data-model.md y las declaraciones `PRIMARY KEY` / `FOREIGN KEY` (metadatos para la futura semantic view; Snowflake no las impone)
- [X] T009 Crear `snowflake/003_seed.sql`: cabecera con `USE ROLE CICD_DEMO_ROLE` / `USE SCHEMA CICD_DEMO.DATA`, `TRUNCATE TABLE` de las tres tablas, e `INSERT ... VALUES` literales de las 12 filas de `DIM_PRODUCT` y las 10 de `DIM_COUNTRY` exactamente como figuran en data-model.md (sin tildes ni `ñ`)
- [X] T010 Desplegar con `snow sql -f snowflake/002_tables.sql` y `snow sql -f snowflake/003_seed.sql`, y comprobar que los tests de T007 pasan

**Checkpoint**: dimensiones cargadas y verificadas. `FACT_SALES` existe pero está vacía.

---

## Phase 3: User Story 1 - Preguntar por cifras filtradas por dimensión (Priority: P1) 🎯 MVP

**Goal**: dejar `FACT_SALES` cargada con la rejilla completa y medidas coherentes, de modo que
cualquier pregunta de agregación con filtros por producto, área terapéutica, unidad de negocio,
país, región o canal devuelva una cifra válida.

**Independent Test**: agregar ventas netas filtrando por país y año devuelve un único número
positivo; agrupar por área terapéutica devuelve 5 filas sin categorías vacías; el total de
ventas netas coincide con la suma de brutas menos descuentos.

### Tests for User Story 1 ⚠️

> **Escribir primero y comprobar que FALLAN antes de tocar el SQL.**

- [X] T011 [US1] Añadir a `tests/test_dataset.py`: `test_fact_row_count` (12.960, I-01), `test_month_grid_is_complete` (36 meses distintos y consecutivos, de `2023-01-01` a `2025-12-01`, I-02), `test_every_combination_has_all_months` (ninguna de las 360 combinaciones producto×país×canal tiene ≠ 36 meses, I-11) y `test_country_list_matches_dimension` (los `COUNTRY_CODE` de `FACT_SALES` coinciden exactamente con los de `DIM_COUNTRY`, I-12)
- [X] T012 [US1] Añadir a `tests/test_dataset.py`: `test_no_nulls` ampliado a `FACT_SALES` (I-03) y `test_no_orphan_references` (anti-join contra ambas dimensiones = 0 filas, I-04)
- [X] T013 [US1] Añadir a `tests/test_dataset.py`: `test_net_sales_always_positive` (I-05), `test_discount_rate_within_bounds` (ratio entre 0 y 0.40, I-06) y `test_brand_ranking_has_no_ties` (el top-5 de marcas por ventas netas tiene 5 valores distintos, I-10)

### Implementation for User Story 1

- [X] T014 [US1] Ampliar `snowflake/003_seed.sql` con el `INSERT` de `FACT_SALES`: CTE `COUNTRY_ORDINAL` con el mapa literal código→ordinal (BR=1 … US=10), CTE `CHANNELS` con los tres canales y su ordinal, CTE `MONTHS` con `ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1` sobre `GENERATOR(ROWCOUNT => 36)`, y el `CROSS JOIN` de los cuatro conjuntos
- [X] T015 [US1] En el mismo `INSERT` de `snowflake/003_seed.sql`, calcular las medidas **sin componente temporal todavía**: `base_p`, `f_pais`, `f_canal` y `f_ruido` para `UNITS_SOLD`; `precio_p` para `GROSS_SALES_EUR`; y `tasa_desc` para `DISCOUNT_EUR`, según las fórmulas de data-model.md
- [X] T016 [US1] Desplegar `snow sql -f snowflake/003_seed.sql` y comprobar que T011, T012 y T013 pasan y que los tests de la Fase 2 no han regresado

**Checkpoint**: dataset consultable. Las preguntas Q-01 a Q-04 y Q-07 a Q-11 del catálogo ya tienen respuesta. **Este es el MVP entregable.**

---

## Phase 4: User Story 2 - Comparar evolución temporal (Priority: P2)

**Goal**: que las preguntas de tendencia y comparativa interanual produzcan resultados
distinguibles. Tras la Fase 3 los 36 meses existen, pero las cifras son planas en el tiempo:
un ranking de crecimiento empataría.

**Independent Test**: la variación interanual 2024→2025 por área terapéutica produce un ganador
único; la serie mensual de una marca en un país tiene forma, no es una recta.

### Tests for User Story 2 ⚠️

- [X] T017 [US2] Añadir a `tests/test_dataset.py`: `test_yoy_growth_by_area_has_no_ties` (la variación interanual 2024→2025 de las 5 áreas terapéuticas da 5 valores distintos y un máximo único) y `test_monthly_series_varies` (la serie de 36 meses de una marca en un país tiene al menos 30 valores distintos de `UNITS_SOLD` y no es monótona) — **DEBEN FALLAR** con la fórmula plana de la Fase 3

### Implementation for User Story 2

- [X] T018 [US2] Añadir a la fórmula de `UNITS_SOLD` en `snowflake/003_seed.sql` los factores `f_tendencia` = `1 + 0.002 * (MOD(p,5) + 1) * m` y `f_estacional` = `1 + 0.18 * SIN(2 * PI() * (m + p) / 12)`, según data-model.md
- [X] T019 [US2] Desplegar `snow sql -f snowflake/003_seed.sql` y comprobar que T017 pasa y que ningún test de US1 ni de la Fase 2 ha regresado (en particular `test_net_sales_always_positive` y `test_brand_ranking_has_no_ties`)

**Checkpoint**: preguntas Q-05 y Q-06 del catálogo respondidas. El dataset ya sirve para toda la demo conversacional.

---

## Phase 5: User Story 3 - Regenerar el dataset de forma reproducible (Priority: P3)

**Goal**: garantizar que dos cargas independientes producen exactamente el mismo dataset, en
cualquier cuenta y cuantas veces se ejecuten.

**Independent Test**: ejecutar `003_seed.sql` dos veces seguidas deja recuentos y sumas
agregadas idénticos, sin filas duplicadas.

> **Nota**: el diseño ya persigue esta propiedad desde la Fase 2 (`CREATE OR REPLACE`,
> `TRUNCATE`, cero aleatoriedad). Esta fase consiste en **demostrarlo**, no en añadir lógica.
> Si algún test falla aquí, es que se ha colado una dependencia de `RANDOM()`, de `HASH()` o de
> `CURRENT_DATE` en el SQL.

### Tests for User Story 3 ⚠️

- [X] T020 [US3] Añadir a `tests/test_dataset.py` el test `test_reload_is_idempotent` marcado con `@pytest.mark.writes_db` (I-09): captura recuentos y `SUM` de las tres medidas, vuelve a ejecutar el contenido de `003_seed.sql` desde la conexión, y compara que todo es idéntico

### Implementation for User Story 3

- [X] T021 [US3] Auditar `snowflake/002_tables.sql` y `snowflake/003_seed.sql`: confirmar que no aparecen `RANDOM(`, `HASH(`, `CURRENT_DATE`, `CURRENT_TIMESTAMP` ni `SEQ4()` sin envolver en `ROW_NUMBER()`, y que cada `INSERT` va precedido de su `TRUNCATE`
- [X] T022 [US3] Ejecutar la secuencia completa dos veces (`002` y `003`, seguidos de `002` y `003` de nuevo) y verificar que T020 pasa
- [X] T023 [US3] Documentar en `specs/001-mock-sales-dataset/quickstart.md` y en `snowflake/README.md` cómo excluir los tests que escriben: `poetry run pytest -m "not writes_db"`

**Checkpoint**: las tres historias completas. El dataset es reproducible y está listo para el pipeline.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T024 [P] Crear `tests/test_reference_questions.py` con las 12 consultas de `specs/001-mock-sales-dataset/contracts/reference-questions.md`, cada una con la aserción indicada en su fila (incluida Q-12, que debe devolver cero filas sin lanzar error) — cubre SC-003
- [X] T025 [P] Actualizar la tabla de scripts de `snowflake/README.md`: `002_tables.sql` y `003_seed.sql` dejan de figurar como pendientes y pasan a la tabla de scripts numerados con su descripción
- [X] T026 Ejecutar de principio a fin `specs/001-mock-sales-dataset/quickstart.md` sobre un schema limpio y corregir cualquier paso que no funcione tal como está escrito
- [X] T027 Comprobar el objetivo de rendimiento del plan: cada consulta del catálogo de referencia responde en menos de 5 s sobre `COMPUTE_WH`
- [X] T028 Revisión final contra `.specify/memory/constitution.md`: confirmar que no se ha aplicado nada a mano en la consola de Snowflake (Principio III), que no hay credenciales en el repositorio (Principio V) y que el delta de tokens de la PR es cero (Principio IV)

---

## Estado

> **28/28 completadas.** Dataset desplegado en `CICD_DEMO.DATA` y verificado: 12.960 filas,
> 36 meses de 2023-01 a 2025-12, 42 tests en verde. La secuencia `002` + `003` se ha ejecutado
> dos veces seguidas produciendo cifras idénticas (T022).
>
> Consulta más lenta del catálogo: 0,13 s, muy por debajo del objetivo de 5 s (T027).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: sin dependencias. **T001 bloquea todo**: si el conector no instala, no hay tests.
- **Foundational (Fase 2)**: depende de la Fase 1. **Bloquea todas las historias.**
- **US1 (Fase 3)**: depende de la Fase 2.
- **US2 (Fase 4)**: depende de **US1**, no sólo de la Fase 2 — modifica la fórmula que US1 escribe en `003_seed.sql`.
- **US3 (Fase 5)**: depende de US1. Puede hacerse antes que US2 si interesa; no depende de ella.
- **Polish (Fase 6)**: depende de US1 y US2 (T024 necesita las preguntas temporales respondidas).

### User Story Dependencies

- **US1 (P1)**: independiente una vez lista la Fase 2. Es el MVP.
- **US2 (P2)**: **no es independiente de US1**. Ambas escriben el mismo `INSERT` de `snowflake/003_seed.sql`; US2 le añade dos factores. Se ha dejado así en vez de duplicar el script, que habría sido ceremonia sin valor (Principio I).
- **US3 (P3)**: independiente de US2. Sólo necesita que `FACT_SALES` tenga datos.

### Within Each User Story

- Los tests se escriben **primero** y deben fallar antes de la implementación (Principio II).
- Estructura antes que datos: `002_tables.sql` antes que `003_seed.sql`.
- Dimensiones antes que hechos.
- Cada despliegue va seguido de la ejecución completa de la suite, no sólo de los tests nuevos.

### Parallel Opportunities

Escasas por diseño, y conviene saber por qué:

- **T003 y T004**: ficheros distintos (`pyproject.toml` y `src/conversational_analytics/db.py`).
- **T024 y T025**: ficheros distintos (`tests/test_reference_questions.py` y `snowflake/README.md`).
- **Todo lo demás es secuencial**: T007 y T011–T013, T017 y T020 tocan `tests/test_dataset.py`; T009, T014, T015 y T018 tocan `snowflake/003_seed.sql`. Dos personas editando esos ficheros a la vez sólo generan conflictos.

Con un equipo de 2-5 personas, el reparto realista es: **una persona lleva la cadena SQL completa** (Fases 2→4) y **otra la infraestructura de tests** (Fase 1 y T024).

## Implementation Strategy

### MVP

**Fases 1 + 2 + 3 (T001–T016).** Al terminarlas hay un dataset consultable que responde a 10 de
las 12 preguntas de referencia. Suficiente para enseñar la demo, aunque las cifras sean planas
en el tiempo.

### Entrega incremental

| Incremento | Tareas | Qué se puede enseñar |
|---|---|---|
| 1. Conexión | T001–T006 | `pytest` habla con Snowflake |
| 2. Dimensiones | T007–T010 | El catálogo de productos y países ya se consulta |
| 3. **MVP** | T011–T016 | Preguntas con filtros multidimensionales y rankings |
| 4. Tiempo | T017–T019 | Tendencias, comparativas interanuales, estacionalidad |
| 5. Reproducibilidad | T020–T023 | El pipeline puede recargar sin miedo |
| 6. Cierre | T024–T028 | Catálogo de preguntas verde y documentación al día |

### Criterio de "hecho" de la feature

Toda la suite en verde (incluidos los tests marcados `writes_db`), `quickstart.md` ejecutable
sin correcciones, y `snowflake/README.md` reflejando los dos scripts nuevos.

---

## Phase 7: Convergence

- [ ] T029 **CRITICAL** Eliminar la duplicación del PAT y reducir la puesta en marcha a los tres pasos del Principio V: añadir a `src/conversational_analytics/db.py` (o a un módulo hermano mínimo) la ejecución de un fichero `.sql` mediante `execute_string()` sobre la conexión de `.env`, sustituir los `snow sql -f` de `specs/001-mock-sales-dataset/quickstart.md` y de `snowflake/README.md` por ese comando, y retirar `pat.txt` y el requisito de `snow connection add` de ambos documentos per Constitution V (partial)
- [ ] T030 Añadir a `tests/test_dataset.py` un test que consulte `FACT_SALES` filtrando por una marca inexistente y verifique que devuelve cero filas sin lanzar error, cubriendo el edge case "combinaciones sin datos" que hoy sólo cubre Q-12 para el año fuera de rango per spec: Edge Cases (missing)
- [ ] T031 Reconciliar el mapa de tests de `specs/001-mock-sales-dataset/contracts/dataset-contract.md` con los nombres reales: `test_row_counts` → `test_dimension_row_counts` + `test_fact_row_count`, `test_no_nulls` → `test_no_nulls_in_dimensions` + `test_no_nulls_in_fact`, y `test_closed_domains` → los cuatro tests de dominio cerrado per contracts/dataset-contract.md (partial)

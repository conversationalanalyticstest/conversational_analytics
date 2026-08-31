# Contrato del dataset

**Feature**: `001-mock-sales-dataset` | **Fecha**: 2026-08-31 | **Fase**: 1

Esta feature no expone API ni CLI. Su interfaz pública son **las tres tablas de
`CICD_DEMO.DATA`**, que consumirán después la semantic view, el agente y los tests de
evaluación. Este documento fija lo que esos consumidores pueden dar por cierto.

## Superficie expuesta

| Objeto | Tipo | Estabilidad |
|---|---|---|
| `CICD_DEMO.DATA.DIM_PRODUCT` | Tabla | Estable — cambios de columna requieren PR |
| `CICD_DEMO.DATA.DIM_COUNTRY` | Tabla | Estable — cambios de columna requieren PR |
| `CICD_DEMO.DATA.FACT_SALES` | Tabla | Estable — cambios de columna requieren PR |

Esquema y dominios completos en [data-model.md](../data-model.md).

## Garantías al consumidor

Un consumidor puede asumir, sin comprobarlo:

1. **Sin nulos.** Ninguna columna de ninguna tabla contiene `NULL`.
2. **Integridad referencial.** Toda fila de `FACT_SALES` referencia un `PRODUCT_ID` y un
   `COUNTRY_CODE` existentes.
3. **Rejilla temporal completa.** Las 360 combinaciones producto×país×canal existen en los 36
   meses. Ninguna serie temporal tiene huecos.
4. **Rango histórico fijo.** `[2023-01-01, 2025-12-01]`, mensual. No cambia con el calendario.
5. **Signo de las medidas.** `UNITS_SOLD > 0`, `GROSS_SALES_EUR > 0`, `DISCOUNT_EUR >= 0`, y
   `GROSS_SALES_EUR - DISCOUNT_EUR > 0`.
6. **Moneda única.** Todos los importes en euros. No hay columna de divisa porque no hay más de
   una.
7. **Dominios cerrados.** 5 áreas terapéuticas, 2 unidades de negocio, 4 regiones, 3 canales.
   Los valores exactos están en [data-model.md](../data-model.md) y no cambian sin PR.
8. **Determinismo.** El mismo commit produce exactamente las mismas cifras en cualquier cuenta
   de Snowflake.

## Lo que el consumidor NO debe asumir

- **No hay columna de ventas netas.** Se calcula: `GROSS_SALES_EUR - DISCOUNT_EUR`.
- **No hay tabla de calendario.** El eje temporal se deriva de `SALE_MONTH`.
- **Las claves primarias y foráneas están declaradas pero Snowflake NO las impone.** Están para
  documentar el modelo y para que la futura semantic view y el optimizador dispongan de los
  metadatos de relación. La integridad real la garantizan los tests, no el motor.
- **Los datos son ficticios.** No representan a ninguna compañía real y no deben presentarse
  como tales.

## Ampliar el catálogo

Añadir un producto o un país es **aditivo**: recibe el siguiente ordinal de generación libre y
las cifras de los ya existentes **no cambian** (ver [research D-08](../research.md)). Lo que sí
cambia son los recuentos del contrato (12 / 10 / 12.960), que están fijados en los tests y
deben actualizarse en la misma PR.

## Tests que verifican el contrato

Cada invariante del modelo de datos queda cubierta. Se escriben **antes** que el SQL
(Principio II). Los nombres son los reales de `tests/test_dataset.py`: algunas invariantes se
verifican con más de un test porque afectan a tablas distintas.

| Test | Invariante | Comprobación |
|---|---|---|
| `test_dimension_row_counts` | I-01 | 12 productos y 10 países |
| `test_fact_row_count` | I-01 | 12960 filas en `FACT_SALES` |
| `test_month_grid_is_complete` | I-02 | 36 meses distintos, consecutivos, min y max esperados |
| `test_no_nulls_in_dimensions` | I-03 | Cero nulos en `DIM_PRODUCT` y `DIM_COUNTRY` |
| `test_no_nulls_in_fact` | I-03 | Cero nulos en `FACT_SALES` |
| `test_no_orphan_references` | I-04 | Anti-join de `FACT_SALES` contra ambas dimensiones = 0 filas |
| `test_net_sales_always_positive` | I-05 | `COUNT(*) WHERE GROSS - DISCOUNT <= 0` = 0 |
| `test_discount_rate_within_bounds` | I-06 | `COUNT(*) WHERE ratio < 0 OR ratio > 0.40` = 0 |
| `test_therapeutic_areas_match_the_closed_domain` | I-07 | Las 4 áreas terapéuticas, exactamente |
| `test_business_units_match_the_closed_domain_with_minimum_products` | I-07 | Las 2 unidades de negocio, con mínimo de productos cada una |
| `test_regions_match_the_closed_domain_with_minimum_countries` | I-07 | Las 4 regiones, con mínimo de países cada una |
| `test_channels_match_the_closed_domain` | I-07 | Los 3 canales, exactamente |
| `test_launch_years_precede_history` | I-08 | `MAX(LAUNCH_YEAR) < 2023` |
| `test_reload_is_idempotent` | I-09 | Recargar `003_seed.sql` deja recuentos y sumas idénticos |
| `test_brand_ranking_has_no_ties` | I-10 | El top-5 por ventas netas tiene 5 valores distintos |
| `test_every_combination_has_all_months` | I-11 | Ninguna de las 360 combinaciones tiene ≠ 36 meses |
| `test_country_list_matches_dimension` | I-12 | Los `COUNTRY_CODE` de `FACT_SALES` coinciden exactamente con los de `DIM_COUNTRY` |
| `tests/test_reference_questions.py` (Q-01..Q-12) | SC-003 | Cada consulta de [reference-questions.md](reference-questions.md) devuelve resultado no vacío y numérico no nulo |

Además, dos tests cubren el caso límite de "no hay datos" que exige el spec:
`test_out_of_range_year_returns_no_rows` (año fuera del histórico) y
`test_unknown_dimension_values_return_no_rows` (marca o país que no existen). Ninguno de los dos
mapea a una invariante: verifican que la ausencia de datos es una respuesta vacía y no un error.

`test_reload_is_idempotent` **escribe** en la base de datos: debe marcarse para poder excluirlo
en ejecuciones rápidas (`pre-commit`) y reservarse a la suite completa de PR.

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

## Tests que verifican el contrato

Un test por invariante del modelo de datos. Se escriben **antes** que el SQL (Principio II).

| Test | Invariante | Comprobación |
|---|---|---|
| `test_row_counts` | I-01 | 12 / 10 / 12960 filas |
| `test_month_grid_is_complete` | I-02 | 36 meses distintos, consecutivos, min y max esperados |
| `test_no_nulls` | I-03 | Cero nulos en toda columna de las tres tablas |
| `test_no_orphan_references` | I-04 | Anti-join de `FACT_SALES` contra ambas dimensiones = 0 filas |
| `test_net_sales_always_positive` | I-05 | `COUNT(*) WHERE GROSS - DISCOUNT <= 0` = 0 |
| `test_discount_rate_within_bounds` | I-06 | `COUNT(*) WHERE ratio < 0 OR ratio > 0.40` = 0 |
| `test_closed_domains` | I-07 | Cardinalidad exacta de cada dominio y mínimos por grupo |
| `test_launch_years_precede_history` | I-08 | `MAX(LAUNCH_YEAR) < 2023` |
| `test_reload_is_idempotent` | I-09 | Recargar `003_seed.sql` deja recuentos y sumas idénticos |
| `test_brand_ranking_has_no_ties` | I-10 | El top-5 por ventas netas tiene 5 valores distintos |
| `test_every_combination_has_all_months` | I-11 | Ninguna de las 360 combinaciones tiene ≠ 36 meses |
| `test_reference_questions` | SC-003 | Cada consulta de [reference-questions.md](reference-questions.md) devuelve resultado no vacío y numérico no nulo |

`test_reload_is_idempotent` **escribe** en la base de datos: debe marcarse para poder excluirlo
en ejecuciones rápidas (`pre-commit`) y reservarse a la suite completa de PR.

# Contract: Mapeo Q-01..Q-11 → AI_VERIFIED_QUERIES

**Feature**: `002-cortex-semantic-view` | **Fecha**: 2026-09-01 | **Fase**: 1

Cada pregunta en rango del catálogo
[reference-questions.md](../../001-mock-sales-dataset/contracts/reference-questions.md) de la
feature 001 tiene exactamente una entrada `AI_VERIFIED_QUERIES` correspondiente en
[semantic-view-ddl.md](semantic-view-ddl.md). Q-12 queda **fuera** de este mapeo a propósito:
es la pregunta intencionadamente insatisfacible (fuera del histórico 2023-2025) y no debe tener
una verified query, para no darle a Cortex Analyst un ejemplo de "cómo forzar una respuesta"
donde el comportamiento correcto es decir que no hay datos (FR-011).

| Pregunta | Entrada `AI_VERIFIED_QUERIES` | Aserción del catálogo (feature 001) |
|---|---|---|
| Q-01 | `q01_ventas_netas_totales_2025` | Un único número `> 0` |
| Q-02 | `q02_unidades_respiralia_alemania_2024` | Un único entero `> 0` |
| Q-03 | `q03_top5_marcas_ventas_netas_europa` | 5 filas, valores distintos, orden descendente |
| Q-04 | `q04_comparativa_unidad_negocio_2025` | 2 filas, ambas `> 0` |
| Q-05 | `q05_area_terapeutica_mayor_crecimiento` | 1 área, variación no nula |
| Q-06 | `q06_evolucion_mensual_cardiovex_espana_2025` | 12 filas, una por mes, sin huecos |
| Q-07 | `q07_canal_mayor_tasa_descuento` | 1 canal, ratio entre 0 y 0.40 |
| Q-08 | `q08_ventas_netas_region_q4_2025` | 4 filas, todas `> 0` |
| Q-09 | `q09_pais_mas_unidades_animal_health` | 1 país, entero `> 0` |
| Q-10 | `q10_ventas_netas_hospital_oncology_2023` | Un único número `> 0` |
| Q-11 | `q11_media_mensual_ventas_netas_producto_latam` | 12 filas, todas `> 0` |
| Q-12 | *(sin verified query — fuera de rango, intencionadamente insatisfacible)* | Cero filas, "no hay datos" |

## Cómo se prueba (Fase de implementación)

`tests/test_semantic_view.py` ejecutará, para cada fila de esta tabla salvo Q-12, el `SQL` de
la entrada `AI_VERIFIED_QUERIES` correspondiente (copiado o reconstruido desde
`semantic-view-ddl.md`) contra la conexión de test ya existente
(`tests/conftest.py`), y comprobará la misma aserción que ya usa
`tests/test_reference_questions.py`. Esto garantiza que la semantic view no diverge del
comportamiento ya probado sobre las tablas base.

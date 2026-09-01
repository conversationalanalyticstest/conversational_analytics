# Contract: Mapeo Q-01..Q-11 → AI_VERIFIED_QUERIES

**Feature**: `002-cortex-semantic-view` | **Fecha**: 2026-09-01 | **Fase**: 1

Cada pregunta en rango del catálogo
[reference-questions.md](../../001-mock-sales-dataset/contracts/reference-questions.md) de la
feature 001 tiene exactamente una entrada `AI_VERIFIED_QUERIES` correspondiente en
[semantic-view-ddl.md](semantic-view-ddl.md). Q-12 queda **fuera** de este mapeo a propósito:
es la pregunta intencionadamente insatisfacible (fuera del histórico 2023-2025) y no debe tener
una verified query, para no darle a Cortex Analyst un ejemplo de "cómo forzar una respuesta"
donde el comportamiento correcto es decir que no hay datos (FR-011).

| Pregunta (catálogo, ES) | Entrada `AI_VERIFIED_QUERIES` | `QUESTION` (EN) | Aserción del catálogo (feature 001) |
|---|---|---|---|
| Q-01 | `q01_total_net_sales_2025` | What were the total net sales in 2025? | Un único número `> 0` |
| Q-02 | `q02_units_respiralia_germany_2024` | How many units of Respiralia did we sell in Germany in 2024? | Un único entero `> 0` |
| Q-03 | `q03_top5_brands_net_sales_europe` | What are the top 5 brands by net sales in Europe? | 5 filas, valores distintos, orden descendente |
| Q-04 | `q04_business_unit_comparison_2025` | Compare net sales of Human Pharma and Animal Health in 2025. | 2 filas, ambas `> 0` |
| Q-05 | `q05_therapeutic_area_highest_growth` | Which therapeutic area grew the most in net sales from 2024 to 2025? | 1 área, variación no nula |
| Q-06 | `q06_monthly_evolution_cardiovex_spain_2025` | Monthly evolution of Cardiovex units in Spain during 2025. | 12 filas, una por mes, sin huecos |
| Q-07 | `q07_channel_highest_discount_rate` | In which channel is the average discount, as a percentage of gross sales, highest? | 1 canal, ratio entre 0 y 0.40 |
| Q-08 | `q08_net_sales_by_region_q4_2025` | Net sales by region in the fourth quarter of 2025. | 4 filas, todas `> 0` |
| Q-09 | `q09_country_most_units_animal_health` | Which country has the most units sold of Animal Health products? | 1 país, entero `> 0` |
| Q-10 | `q10_net_sales_hospital_oncology_2023` | How much net sales did the hospital channel generate in Oncology in 2023? | Un único número `> 0` |
| Q-11 | `q11_avg_monthly_net_sales_per_product_latam` | Average monthly net sales per product in LATAM. | 12 filas, todas `> 0` |
| Q-12 | *(sin verified query — fuera de rango, intencionadamente insatisfacible)* | — | Cero filas, "no hay datos" |

> El catálogo original (columna izquierda) está en español y se mantiene así
> ([reference-questions.md](../../001-mock-sales-dataset/contracts/reference-questions.md),
> feature 001 ya cerrada, no se despliega a Snowflake). El texto `QUESTION` que ve el agente
> está en inglés (decisión D-09 de [research.md](../research.md)).

## Cómo se prueba (Fase de implementación)

`tests/test_semantic_view.py` ejecutará, para cada fila de esta tabla salvo Q-12, el `SQL` de
la entrada `AI_VERIFIED_QUERIES` correspondiente (copiado o reconstruido desde
`semantic-view-ddl.md`) contra la conexión de test ya existente
(`tests/conftest.py`), y comprobará la misma aserción que ya usa
`tests/test_reference_questions.py`. Esto garantiza que la semantic view no diverge del
comportamiento ya probado sobre las tablas base.

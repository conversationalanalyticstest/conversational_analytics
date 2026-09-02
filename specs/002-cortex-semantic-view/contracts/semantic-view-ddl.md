# Contract: DDL de la Semantic View

**Feature**: `002-cortex-semantic-view` | **Fecha**: 2026-09-01 | **Fase**: 1

Este es el contrato ejecutable de la feature: el `CREATE OR ALTER SEMANTIC VIEW` completo que
`speckit-implement` copiará (sin cambios de fondo) a `snowflake/004_semantic_view.sql`. Sintaxis
validada contra la documentación oficial de Snowflake (ver [research.md](../research.md)).

> **Idioma**: nombres de tablas lógicas, dimensiones, facts, métricas, sinónimos, comentarios
> (`COMMENT`) y el texto `QUESTION` de cada `AI_VERIFIED_QUERIES` van **en inglés** (decisión
> D-09 de research.md); solo esta explicación alrededor del bloque SQL está en español.

Los valores de `SAMPLE_VALUES` para los dominios cerrados están copiados literalmente de
[data-model.md de la feature 001](../../001-mock-sales-dataset/data-model.md); si ese dominio
cambia alguna vez, este fichero debe actualizarse en la misma PR (ver "Ampliar el catálogo" en
[dataset-contract.md](../../001-mock-sales-dataset/contracts/dataset-contract.md)).

```sql
USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DATA;

CREATE OR ALTER SEMANTIC VIEW SV_PHARMA_SALES

  TABLES (
    PRODUCT AS DIM_PRODUCT
      PRIMARY KEY (PRODUCT_ID)
      WITH SYNONYMS ('products', 'product catalog', 'medicines')
      COMMENT = 'Catalog of pharmaceutical and animal health products sold. Each product belongs to a brand, a therapeutic area and a business unit.',
    COUNTRY AS DIM_COUNTRY
      PRIMARY KEY (COUNTRY_CODE)
      WITH SYNONYMS ('countries', 'markets', 'market')
      COMMENT = 'Catalog of countries where products are sold. Each country belongs to a commercial region.',
    SALE AS FACT_SALES
      PRIMARY KEY (SALE_MONTH, PRODUCT_ID, COUNTRY_CODE, CHANNEL)
      WITH SYNONYMS ('sales', 'sales transactions', 'commercial activity')
      COMMENT = 'Monthly sales by product, country and channel. Grain: month x product x country x channel.'
  )

  RELATIONSHIPS (
    SALE_TO_PRODUCT AS SALE (PRODUCT_ID) REFERENCES PRODUCT,
    SALE_TO_COUNTRY AS SALE (COUNTRY_CODE) REFERENCES COUNTRY
  )

  FACTS (
    SALE.GROSS_AMOUNT AS GROSS_SALES_EUR
      COMMENT = 'Gross sales amount in euros, before discount, for the row.',
    SALE.DISCOUNT_AMOUNT AS DISCOUNT_EUR
      COMMENT = 'Discount amount in euros applied to the row.',
    SALE.NET_AMOUNT AS GROSS_SALES_EUR - DISCOUNT_EUR
      COMMENT = 'Net sales amount in euros for the row (gross minus discount). Not physically stored; always computed from the two columns above.'
  )

  DIMENSIONS (
    PRODUCT.BRAND AS BRAND
      WITH SYNONYMS ('brand', 'product name')
      COMMENT = 'Commercial brand of the product.',
    PRODUCT.THERAPEUTIC_AREA AS THERAPEUTIC_AREA
      WITH SYNONYMS ('therapeutic area', 'therapy area', 'specialty')
      COMMENT = 'Therapeutic area the product belongs to.'
      SAMPLE_VALUES ('Cardiometabolic', 'Respiratory', 'Oncology', 'Central Nervous System', 'Animal Health')
      IS_ENUM,
    PRODUCT.BUSINESS_UNIT AS BUSINESS_UNIT
      WITH SYNONYMS ('business unit', 'line of business', 'division')
      COMMENT = 'Business unit of the product: human health or animal health.'
      SAMPLE_VALUES ('Human Pharma', 'Animal Health')
      IS_ENUM,
    COUNTRY.COUNTRY_NAME AS COUNTRY_NAME
      WITH SYNONYMS ('country', 'market name')
      COMMENT = 'Name of the country where the sale is recorded.'
      SAMPLE_VALUES ('Brazil', 'Canada', 'China', 'France', 'Germany', 'Italy', 'Japan', 'Mexico', 'Spain', 'United States')
      IS_ENUM,
    COUNTRY.REGION AS REGION
      WITH SYNONYMS ('region', 'commercial region', 'zone')
      COMMENT = 'Commercial region the country belongs to.'
      SAMPLE_VALUES ('Europe', 'North America', 'LATAM', 'APAC')
      IS_ENUM,
    SALE.CHANNEL AS CHANNEL
      WITH SYNONYMS ('channel', 'sales channel')
      COMMENT = 'Channel through which the sale happened: hospital, retail/specialty pharmacy or distributor.'
      SAMPLE_VALUES ('Hospital', 'Retail Pharmacy', 'Distributor')
      IS_ENUM,
    SALE.MONTH AS SALE_MONTH
      WITH SYNONYMS ('month', 'sales month', 'period')
      COMMENT = 'First day of the sales month. History from 2023-01 to 2025-12.',
    SALE.YEAR AS YEAR(SALE_MONTH)
      WITH SYNONYMS ('year')
      COMMENT = 'Year of the sale, derived from the month.',
    SALE.QUARTER AS QUARTER(SALE_MONTH)
      WITH SYNONYMS ('quarter')
      COMMENT = 'Quarter of the year of the sale (1 to 4), derived from the month.'
  )

  METRICS (
    SALE.UNITS_SOLD AS SUM(SALE.UNITS_SOLD)
      WITH SYNONYMS ('units', 'units sold', 'volume')
      COMMENT = 'Total units sold.',
    SALE.GROSS_SALES AS SUM(SALE.GROSS_AMOUNT)
      WITH SYNONYMS ('gross sales', 'gross revenue')
      COMMENT = 'Total gross sales in euros, before discount.',
    SALE.DISCOUNT AS SUM(SALE.DISCOUNT_AMOUNT)
      WITH SYNONYMS ('discount', 'discounts', 'discount amount')
      COMMENT = 'Total discount granted, in euros.',
    SALE.NET_SALES AS SUM(SALE.NET_AMOUNT)
      WITH SYNONYMS ('sales', 'net sales', 'revenue')
      COMMENT = 'Total net sales in euros (gross minus discount). Default business metric for unqualified "sales".',
    SALE.AVG_NET_SALES AS AVG(SALE.NET_AMOUNT)
      WITH SYNONYMS ('average net sales', 'average sales')
      COMMENT = 'Average net sales per row within the queried group.',
    AVG_DISCOUNT_RATE AS DIV0(SALE.DISCOUNT, SALE.GROSS_SALES)
      WITH SYNONYMS ('discount rate', 'average discount rate', 'discount percentage')
      COMMENT = 'Discount as a proportion of gross sales (0 to 0.40), computed as total discount divided by total gross sales for the queried group.'
  )

  COMMENT = 'Semantic model of pharma sales (fictitious data) to answer business questions with Cortex Analyst: units, gross sales, discount and net sales by product, brand, therapeutic area, business unit, country, region, channel and time.'

  AI_VERIFIED_QUERIES (
    q01_total_net_sales_2025 AS (
      QUESTION 'What were the total net sales in 2025?'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT NET_SALES
           FROM SEMANTIC_VIEW(
             CICD_DEMO.DATA.SV_PHARMA_SALES
             METRICS SALE.NET_SALES
             WHERE SALE.YEAR = 2025
           )'
    ),
    q02_units_respiralia_germany_2024 AS (
      QUESTION 'How many units of Respiralia did we sell in Germany in 2024?'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT UNITS_SOLD AS UNITS
           FROM SEMANTIC_VIEW(
             CICD_DEMO.DATA.SV_PHARMA_SALES
             METRICS SALE.UNITS_SOLD
             WHERE PRODUCT.BRAND = ''Respiralia'' AND COUNTRY.COUNTRY_NAME = ''Germany'' AND SALE.YEAR = 2024
           )'
    ),
    q03_top5_brands_net_sales_europe AS (
      QUESTION 'What are the top 5 brands by net sales in Europe?'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT BRAND, NET_SALES
           FROM SEMANTIC_VIEW(
             CICD_DEMO.DATA.SV_PHARMA_SALES
             DIMENSIONS PRODUCT.BRAND
             METRICS SALE.NET_SALES
             WHERE COUNTRY.REGION = ''Europe''
           )
           ORDER BY NET_SALES DESC
           LIMIT 5'
    ),
    q04_business_unit_comparison_2025 AS (
      QUESTION 'Compare net sales of Human Pharma and Animal Health in 2025.'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT BUSINESS_UNIT, NET_SALES
           FROM SEMANTIC_VIEW(
             CICD_DEMO.DATA.SV_PHARMA_SALES
             DIMENSIONS PRODUCT.BUSINESS_UNIT
             METRICS SALE.NET_SALES
             WHERE SALE.YEAR = 2025
           )'
    ),
    q05_therapeutic_area_highest_growth AS (
      QUESTION 'Which therapeutic area grew the most in net sales from 2024 to 2025?'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION FALSE
      SQL 'WITH BY_YEAR AS (
             SELECT THERAPEUTIC_AREA, YEAR, NET_SALES
             FROM SEMANTIC_VIEW(
               CICD_DEMO.DATA.SV_PHARMA_SALES
               DIMENSIONS PRODUCT.THERAPEUTIC_AREA, SALE.YEAR
               METRICS SALE.NET_SALES
               WHERE SALE.YEAR IN (2024, 2025)
             )
           )
           SELECT THERAPEUTIC_AREA,
                  SUM(CASE WHEN YEAR = 2025 THEN NET_SALES ELSE -NET_SALES END) AS GROWTH
           FROM BY_YEAR
           GROUP BY THERAPEUTIC_AREA
           ORDER BY GROWTH DESC
           LIMIT 1'
    ),
    q06_monthly_evolution_cardiovex_spain_2025 AS (
      QUESTION 'Monthly evolution of Cardiovex units in Spain during 2025.'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT MONTH, UNITS_SOLD AS UNITS
           FROM SEMANTIC_VIEW(
             CICD_DEMO.DATA.SV_PHARMA_SALES
             DIMENSIONS SALE.MONTH
             METRICS SALE.UNITS_SOLD
             WHERE PRODUCT.BRAND = ''Cardiovex'' AND COUNTRY.COUNTRY_NAME = ''Spain'' AND SALE.YEAR = 2025
           )
           ORDER BY MONTH'
    ),
    q07_channel_highest_discount_rate AS (
      QUESTION 'In which channel is the average discount, as a percentage of gross sales, highest?'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT CHANNEL, AVG_DISCOUNT_RATE AS DISCOUNT_RATE
           FROM SEMANTIC_VIEW(
             CICD_DEMO.DATA.SV_PHARMA_SALES
             DIMENSIONS SALE.CHANNEL
             METRICS AVG_DISCOUNT_RATE
           )
           ORDER BY DISCOUNT_RATE DESC
           LIMIT 1'
    ),
    q08_net_sales_by_region_q4_2025 AS (
      QUESTION 'Net sales by region in the fourth quarter of 2025.'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT REGION, NET_SALES
           FROM SEMANTIC_VIEW(
             CICD_DEMO.DATA.SV_PHARMA_SALES
             DIMENSIONS COUNTRY.REGION
             METRICS SALE.NET_SALES
             WHERE SALE.YEAR = 2025 AND SALE.QUARTER = 4
           )'
    ),
    q09_country_most_units_animal_health AS (
      QUESTION 'Which country has the most units sold of Animal Health products?'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT COUNTRY_NAME, UNITS_SOLD AS UNITS
           FROM SEMANTIC_VIEW(
             CICD_DEMO.DATA.SV_PHARMA_SALES
             DIMENSIONS COUNTRY.COUNTRY_NAME
             METRICS SALE.UNITS_SOLD
             WHERE PRODUCT.BUSINESS_UNIT = ''Animal Health''
           )
           ORDER BY UNITS DESC
           LIMIT 1'
    ),
    q10_net_sales_hospital_oncology_2023 AS (
      QUESTION 'How much net sales did the hospital channel generate in Oncology in 2023?'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT NET_SALES
           FROM SEMANTIC_VIEW(
             CICD_DEMO.DATA.SV_PHARMA_SALES
             METRICS SALE.NET_SALES
             WHERE SALE.CHANNEL = ''Hospital'' AND PRODUCT.THERAPEUTIC_AREA = ''Oncology'' AND SALE.YEAR = 2023
           )'
    ),
    q11_avg_monthly_net_sales_per_product_latam AS (
      QUESTION 'Average monthly net sales per product in LATAM.'
      VERIFIED_AT 1788307200
      ONBOARDING_QUESTION FALSE
      SQL 'WITH MONTHLY_SALES AS (
             SELECT BRAND, MONTH, NET_SALES
             FROM SEMANTIC_VIEW(
               CICD_DEMO.DATA.SV_PHARMA_SALES
               DIMENSIONS PRODUCT.BRAND, SALE.MONTH
               METRICS SALE.NET_SALES
               WHERE COUNTRY.REGION = ''LATAM''
             )
           )
           SELECT BRAND, AVG(NET_SALES) AS AVG_MONTHLY_NET_SALES
           FROM MONTHLY_SALES
           GROUP BY BRAND'
    )
  );
```

## Notas de validación

- Todas las expresiones de `FACTS`, `DIMENSIONS` y `METRICS` referencian exclusivamente columnas
  de `DIM_PRODUCT`, `DIM_COUNTRY` y `FACT_SALES` (ver trazabilidad en
  [data-model.md](../data-model.md)).
- El pedido de la spec (FR-002) de no inventar relaciones se cumple: solo existen las dos
  claves foráneas ya declaradas en `002_tables.sql`.
- `VERIFIED_AT 1788220800` corresponde a 2026-09-01T00:00:00Z (fecha de esta fase). Se
  actualizará solo si se reverifica alguna consulta más adelante.
- Las preguntas (`QUESTION`) están en inglés porque el agente y quien lo consulta operan en
  inglés (decisión D-09); el catálogo español
  [reference-questions.md](../../001-mock-sales-dataset/contracts/reference-questions.md) de la
  feature 001 se mantiene sin cambios, ya que es documentación de test que no se despliega a
  Snowflake.
- `VERIFIED_AT 1788307200` (2026-09-02T00:00:00Z): el `SQL` de las 11 verified queries se
  reescribió para usar `SEMANTIC_VIEW(CICD_DEMO.DATA.SV_PHARMA_SALES ...)` con el nombre
  completamente cualificado (ver D-11 en [research.md](../research.md)), corrigiendo el
  defecto D-06 documentado en `specs/003-conversational-agent/research.md`: con SQL directo
  sobre tablas físicas, o con el nombre de la semantic view sin cualificar, Cortex Analyst
  nunca marcaba `confidence.verified_query_used`. Verificado empíricamente contra la cuenta
  real (Q01 y Q05).

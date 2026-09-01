# Contract: DDL de la Semantic View

**Feature**: `002-cortex-semantic-view` | **Fecha**: 2026-09-01 | **Fase**: 1

Este es el contrato ejecutable de la feature: el `CREATE OR ALTER SEMANTIC VIEW` completo que
`speckit-implement` copiará (sin cambios de fondo) a `snowflake/004_semantic_view.sql`. Sintaxis
validada contra la documentación oficial de Snowflake (ver [research.md](../research.md)).

Los valores de `SAMPLE_VALUES` para los dominios cerrados están copiados literalmente de
[data-model.md de la feature 001](../../001-mock-sales-dataset/data-model.md); si ese dominio
cambia alguna vez, este fichero debe actualizarse en la misma PR (ver "Ampliar el catálogo" en
[dataset-contract.md](../../001-mock-sales-dataset/contracts/dataset-contract.md)).

```sql
USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DATA;

CREATE OR ALTER SEMANTIC VIEW SV_VENTAS_FARMA

  TABLES (
    PRODUCTO AS DIM_PRODUCT
      PRIMARY KEY (PRODUCT_ID)
      WITH SYNONYMS ('productos', 'catalogo de productos', 'medicamentos')
      COMMENT = 'Catalogo de productos farmaceuticos y de salud animal vendidos. Cada producto pertenece a una marca, un area terapeutica y una unidad de negocio.',
    PAIS AS DIM_COUNTRY
      PRIMARY KEY (COUNTRY_CODE)
      WITH SYNONYMS ('paises', 'mercados', 'mercado')
      COMMENT = 'Catalogo de paises donde se vende. Cada pais pertenece a una region comercial.',
    VENTA AS FACT_SALES
      PRIMARY KEY (SALE_MONTH, PRODUCT_ID, COUNTRY_CODE, CHANNEL)
      WITH SYNONYMS ('ventas', 'transacciones de venta', 'actividad comercial')
      COMMENT = 'Ventas mensuales por producto, pais y canal. Grano: mes x producto x pais x canal.'
  )

  RELATIONSHIPS (
    VENTA_A_PRODUCTO AS VENTA (PRODUCT_ID) REFERENCES PRODUCTO,
    VENTA_A_PAIS AS VENTA (COUNTRY_CODE) REFERENCES PAIS
  )

  FACTS (
    VENTA.UNIDADES AS UNITS_SOLD
      COMMENT = 'Unidades vendidas en la fila (mes x producto x pais x canal).',
    VENTA.IMPORTE_BRUTO AS GROSS_SALES_EUR
      COMMENT = 'Ventas brutas en euros, antes de descuento, en la fila.',
    VENTA.IMPORTE_DESCUENTO AS DISCOUNT_EUR
      COMMENT = 'Descuento en euros aplicado en la fila.',
    VENTA.IMPORTE_NETO AS GROSS_SALES_EUR - DISCOUNT_EUR
      COMMENT = 'Ventas netas en euros de la fila (bruto menos descuento). No esta almacenado fisicamente; se calcula siempre a partir de las dos columnas anteriores.'
  )

  DIMENSIONS (
    PRODUCTO.MARCA AS BRAND
      WITH SYNONYMS ('marca', 'producto', 'nombre comercial')
      COMMENT = 'Marca comercial del producto.',
    PRODUCTO.AREA_TERAPEUTICA AS THERAPEUTIC_AREA
      WITH SYNONYMS ('area terapeutica', 'categoria terapeutica', 'especialidad')
      COMMENT = 'Area terapeutica a la que pertenece el producto.'
      SAMPLE_VALUES ('Cardiometabolic', 'Respiratory', 'Oncology', 'Central Nervous System', 'Animal Health')
      IS_ENUM,
    PRODUCTO.UNIDAD_NEGOCIO AS BUSINESS_UNIT
      WITH SYNONYMS ('unidad de negocio', 'linea de negocio', 'division')
      COMMENT = 'Unidad de negocio del producto: salud humana o salud animal.'
      SAMPLE_VALUES ('Human Pharma', 'Animal Health')
      IS_ENUM,
    PAIS.NOMBRE_PAIS AS COUNTRY_NAME
      WITH SYNONYMS ('pais', 'mercado', 'nombre del pais')
      COMMENT = 'Nombre del pais donde se registra la venta.',
    PAIS.REGION AS REGION
      WITH SYNONYMS ('region', 'region comercial', 'zona')
      COMMENT = 'Region comercial a la que pertenece el pais.'
      SAMPLE_VALUES ('Europe', 'North America', 'LATAM', 'APAC')
      IS_ENUM,
    VENTA.CANAL AS CHANNEL
      WITH SYNONYMS ('canal', 'canal de venta', 'via de venta')
      COMMENT = 'Canal a traves del cual se vendio: hospital, farmacia/tienda especializada o mayorista.'
      SAMPLE_VALUES ('Hospital', 'Retail Pharmacy', 'Distributor')
      IS_ENUM,
    VENTA.MES AS SALE_MONTH
      WITH SYNONYMS ('mes', 'mes de venta', 'periodo')
      COMMENT = 'Primer dia del mes de la venta. Historico de 2023-01 a 2025-12.',
    VENTA.ANIO AS YEAR(SALE_MONTH)
      WITH SYNONYMS ('anio', 'ano')
      COMMENT = 'Anio de la venta, derivado del mes.',
    VENTA.TRIMESTRE AS QUARTER(SALE_MONTH)
      WITH SYNONYMS ('trimestre', 'quarter')
      COMMENT = 'Trimestre del anio de la venta (1 a 4), derivado del mes.'
  )

  METRICS (
    VENTA.UNIDADES_VENDIDAS AS SUM(VENTA.UNIDADES)
      WITH SYNONYMS ('unidades', 'unidades vendidas', 'volumen')
      COMMENT = 'Total de unidades vendidas.',
    VENTA.VENTAS_BRUTAS AS SUM(VENTA.IMPORTE_BRUTO)
      WITH SYNONYMS ('ventas brutas', 'facturacion bruta', 'ingresos brutos')
      COMMENT = 'Total de ventas brutas en euros, antes de descuento.',
    VENTA.DESCUENTO AS SUM(VENTA.IMPORTE_DESCUENTO)
      WITH SYNONYMS ('descuento', 'descuentos', 'importe descontado')
      COMMENT = 'Total del descuento concedido en euros.',
    VENTA.VENTAS_NETAS AS SUM(VENTA.IMPORTE_NETO)
      WITH SYNONYMS ('ventas', 'ventas netas', 'ingresos', 'facturacion', 'facturacion neta')
      COMMENT = 'Total de ventas netas en euros (brutas menos descuento). Metrica de negocio por defecto para "ventas" sin cualificar.',
    VENTA.VENTAS_NETAS_MEDIA AS AVG(VENTA.IMPORTE_NETO)
      WITH SYNONYMS ('media de ventas netas', 'promedio de ventas netas', 'venta neta media')
      COMMENT = 'Media de ventas netas por fila dentro del grupo consultado.',
    TASA_DESCUENTO_MEDIA AS DIV0(VENTA.DESCUENTO, VENTA.VENTAS_BRUTAS)
      WITH SYNONYMS ('tasa de descuento', 'porcentaje de descuento', 'descuento medio')
      COMMENT = 'Descuento como proporcion de las ventas brutas (0 a 0.40), calculado como descuento total entre ventas brutas totales del grupo consultado.'
  )

  COMMENT = 'Modelo semantico de ventas farma (datos ficticios) para responder preguntas de negocio con Cortex Analyst: unidades, ventas brutas, descuento y ventas netas por producto, marca, area terapeutica, unidad de negocio, pais, region, canal y tiempo.'

  AI_VERIFIED_QUERIES (
    q01_ventas_netas_totales_2025 AS (
      QUESTION 'Cuales fueron las ventas netas totales en 2025?'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT SUM(GROSS_SALES_EUR - DISCOUNT_EUR) AS VENTAS_NETAS
           FROM CICD_DEMO.DATA.FACT_SALES
           WHERE YEAR(SALE_MONTH) = 2025'
    ),
    q02_unidades_respiralia_alemania_2024 AS (
      QUESTION 'Cuantas unidades vendimos de Respiralia en Alemania en 2024?'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT SUM(f.UNITS_SOLD) AS UNIDADES
           FROM CICD_DEMO.DATA.FACT_SALES f
           JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON f.PRODUCT_ID = p.PRODUCT_ID
           WHERE p.BRAND = ''Respiralia'' AND f.COUNTRY_CODE = ''DE'' AND YEAR(f.SALE_MONTH) = 2024'
    ),
    q03_top5_marcas_ventas_netas_europa AS (
      QUESTION 'Cual es el top 5 de marcas por ventas netas en Europa?'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT p.BRAND, SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS VENTAS_NETAS
           FROM CICD_DEMO.DATA.FACT_SALES f
           JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON f.PRODUCT_ID = p.PRODUCT_ID
           JOIN CICD_DEMO.DATA.DIM_COUNTRY c ON f.COUNTRY_CODE = c.COUNTRY_CODE
           WHERE c.REGION = ''Europe''
           GROUP BY p.BRAND
           ORDER BY VENTAS_NETAS DESC
           LIMIT 5'
    ),
    q04_comparativa_unidad_negocio_2025 AS (
      QUESTION 'Compara las ventas netas de Human Pharma y Animal Health en 2025.'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT p.BUSINESS_UNIT, SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS VENTAS_NETAS
           FROM CICD_DEMO.DATA.FACT_SALES f
           JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON f.PRODUCT_ID = p.PRODUCT_ID
           WHERE YEAR(f.SALE_MONTH) = 2025
           GROUP BY p.BUSINESS_UNIT'
    ),
    q05_area_terapeutica_mayor_crecimiento AS (
      QUESTION 'Que area terapeutica crecio mas en ventas netas de 2024 a 2025?'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION FALSE
      SQL 'WITH POR_ANIO AS (
             SELECT p.THERAPEUTIC_AREA, YEAR(f.SALE_MONTH) AS ANIO,
                    SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS VENTAS_NETAS
             FROM CICD_DEMO.DATA.FACT_SALES f
             JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON f.PRODUCT_ID = p.PRODUCT_ID
             WHERE YEAR(f.SALE_MONTH) IN (2024, 2025)
             GROUP BY p.THERAPEUTIC_AREA, YEAR(f.SALE_MONTH)
           )
           SELECT THERAPEUTIC_AREA,
                  SUM(CASE WHEN ANIO = 2025 THEN VENTAS_NETAS ELSE -VENTAS_NETAS END) AS VARIACION
           FROM POR_ANIO
           GROUP BY THERAPEUTIC_AREA
           ORDER BY VARIACION DESC
           LIMIT 1'
    ),
    q06_evolucion_mensual_cardiovex_espana_2025 AS (
      QUESTION 'Evolucion mensual de las unidades de Cardiovex en Espana durante 2025.'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT f.SALE_MONTH, SUM(f.UNITS_SOLD) AS UNIDADES
           FROM CICD_DEMO.DATA.FACT_SALES f
           JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON f.PRODUCT_ID = p.PRODUCT_ID
           WHERE p.BRAND = ''Cardiovex'' AND f.COUNTRY_CODE = ''ES'' AND YEAR(f.SALE_MONTH) = 2025
           GROUP BY f.SALE_MONTH
           ORDER BY f.SALE_MONTH'
    ),
    q07_canal_mayor_tasa_descuento AS (
      QUESTION 'En que canal es mayor el descuento medio como porcentaje de las ventas brutas?'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT CHANNEL, SUM(DISCOUNT_EUR) / SUM(GROSS_SALES_EUR) AS TASA_DESCUENTO
           FROM CICD_DEMO.DATA.FACT_SALES
           GROUP BY CHANNEL
           ORDER BY TASA_DESCUENTO DESC
           LIMIT 1'
    ),
    q08_ventas_netas_region_q4_2025 AS (
      QUESTION 'Ventas netas por region en el cuarto trimestre de 2025.'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT c.REGION, SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS VENTAS_NETAS
           FROM CICD_DEMO.DATA.FACT_SALES f
           JOIN CICD_DEMO.DATA.DIM_COUNTRY c ON f.COUNTRY_CODE = c.COUNTRY_CODE
           WHERE f.SALE_MONTH BETWEEN DATE ''2025-10-01'' AND DATE ''2025-12-01''
           GROUP BY c.REGION'
    ),
    q09_pais_mas_unidades_animal_health AS (
      QUESTION 'Cual es el pais con mas unidades vendidas de productos de Animal Health?'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT f.COUNTRY_CODE, SUM(f.UNITS_SOLD) AS UNIDADES
           FROM CICD_DEMO.DATA.FACT_SALES f
           JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON f.PRODUCT_ID = p.PRODUCT_ID
           WHERE p.BUSINESS_UNIT = ''Animal Health''
           GROUP BY f.COUNTRY_CODE
           ORDER BY UNIDADES DESC
           LIMIT 1'
    ),
    q10_ventas_netas_hospital_oncology_2023 AS (
      QUESTION 'Cuantas ventas netas genero el canal hospitalario en Oncology en 2023?'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION FALSE
      SQL 'SELECT SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS VENTAS_NETAS
           FROM CICD_DEMO.DATA.FACT_SALES f
           JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON f.PRODUCT_ID = p.PRODUCT_ID
           WHERE f.CHANNEL = ''Hospital'' AND p.THERAPEUTIC_AREA = ''Oncology'' AND YEAR(f.SALE_MONTH) = 2023'
    ),
    q11_media_mensual_ventas_netas_producto_latam AS (
      QUESTION 'Media mensual de ventas netas por producto en LATAM.'
      VERIFIED_AT 1788220800
      ONBOARDING_QUESTION FALSE
      SQL 'WITH VENTAS_MES AS (
             SELECT p.BRAND, f.SALE_MONTH, SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS VENTAS_NETAS_MES
             FROM CICD_DEMO.DATA.FACT_SALES f
             JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON f.PRODUCT_ID = p.PRODUCT_ID
             JOIN CICD_DEMO.DATA.DIM_COUNTRY c ON f.COUNTRY_CODE = c.COUNTRY_CODE
             WHERE c.REGION = ''LATAM''
             GROUP BY p.BRAND, f.SALE_MONTH
           )
           SELECT BRAND, AVG(VENTAS_NETAS_MES) AS MEDIA_MENSUAL
           FROM VENTAS_MES
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

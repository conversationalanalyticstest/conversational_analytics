-- =========================================================
-- 002_tables.sql
-- Estructura del dataset mock de ventas farma.
--
-- Idempotente: CREATE OR REPLACE hace que el esquema converja SIEMPRE a lo que
-- dice este fichero. Si aqui se anade una columna, el siguiente despliegue la
-- aplica. Git es la fuente de verdad (Principio III de la constitucion).
--
-- OJO: CREATE OR REPLACE vacia las tablas. La carga va aparte, en 003_seed.sql.
--
-- Las PRIMARY KEY y FOREIGN KEY son METADATOS: Snowflake no las impone. Estan
-- para documentar el modelo y para que la futura semantic view disponga de las
-- relaciones. La integridad real la garantizan los tests.
--
-- Requiere CICD_DEMO_ROLE (creado en 001_bootstrap.sql), que queda como
-- propietario de las tablas y por tanto no necesita grants adicionales.
-- =========================================================

USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DATA;


-- ---------------------------------------------------------
-- Dimension: productos (12 filas)
-- ---------------------------------------------------------

CREATE OR REPLACE TABLE DIM_PRODUCT (
    PRODUCT_ID       VARCHAR(4)  NOT NULL COMMENT 'Identificador del producto: P001..P012',
    BRAND            VARCHAR(40) NOT NULL COMMENT 'Marca comercial (ficticia)',
    THERAPEUTIC_AREA VARCHAR(40) NOT NULL COMMENT 'Area terapeutica. Dominio cerrado de 5 valores',
    BUSINESS_UNIT    VARCHAR(20) NOT NULL COMMENT 'Human Pharma o Animal Health',
    LAUNCH_YEAR      NUMBER(4,0) NOT NULL COMMENT 'Anio de lanzamiento, siempre anterior a 2023',

    CONSTRAINT PK_DIM_PRODUCT PRIMARY KEY (PRODUCT_ID)
)
COMMENT = 'Catalogo de productos. Datos ficticios.';


-- ---------------------------------------------------------
-- Dimension: paises (10 filas)
-- ---------------------------------------------------------

CREATE OR REPLACE TABLE DIM_COUNTRY (
    COUNTRY_CODE VARCHAR(2)  NOT NULL COMMENT 'Codigo ISO-3166 alpha-2',
    COUNTRY_NAME VARCHAR(40) NOT NULL COMMENT 'Nombre del pais',
    REGION       VARCHAR(20) NOT NULL COMMENT 'Region comercial. Dominio cerrado de 4 valores',

    CONSTRAINT PK_DIM_COUNTRY PRIMARY KEY (COUNTRY_CODE)
)
COMMENT = 'Catalogo de mercados. Datos ficticios.';


-- ---------------------------------------------------------
-- Hecho: ventas mensuales (12.960 filas)
-- Grano: mes x producto x pais x canal
--
-- No hay columna de ventas netas: se derivan como
--   GROSS_SALES_EUR - DISCOUNT_EUR
-- Almacenarlas seria redundante y podria desincronizarse.
-- ---------------------------------------------------------

CREATE OR REPLACE TABLE FACT_SALES (
    SALE_MONTH      DATE         NOT NULL COMMENT 'Primer dia del mes. De 2023-01-01 a 2025-12-01',
    PRODUCT_ID      VARCHAR(4)   NOT NULL COMMENT 'FK a DIM_PRODUCT',
    COUNTRY_CODE    VARCHAR(2)   NOT NULL COMMENT 'FK a DIM_COUNTRY',
    CHANNEL         VARCHAR(20)  NOT NULL COMMENT 'Hospital, Retail Pharmacy o Distributor',
    UNITS_SOLD      NUMBER(10,0) NOT NULL COMMENT 'Unidades vendidas en el mes',
    GROSS_SALES_EUR NUMBER(12,2) NOT NULL COMMENT 'Ventas brutas en euros',
    DISCOUNT_EUR    NUMBER(12,2) NOT NULL COMMENT 'Descuento en euros. Entre el 0% y el 40% de las brutas',

    CONSTRAINT PK_FACT_SALES PRIMARY KEY (SALE_MONTH, PRODUCT_ID, COUNTRY_CODE, CHANNEL),
    CONSTRAINT FK_FACT_SALES_PRODUCT FOREIGN KEY (PRODUCT_ID)   REFERENCES DIM_PRODUCT (PRODUCT_ID),
    CONSTRAINT FK_FACT_SALES_COUNTRY FOREIGN KEY (COUNTRY_CODE) REFERENCES DIM_COUNTRY (COUNTRY_CODE)
)
COMMENT = 'Ventas mensuales. Datos ficticios generados de forma determinista por 003_seed.sql.';

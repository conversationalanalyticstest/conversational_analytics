-- =========================================================
-- 003_seed.sql
-- Carga del dataset mock. TODOS los datos son FICTICIOS.
--
-- Idempotente: TRUNCATE + INSERT. Ejecutarlo N veces deja exactamente el mismo
-- resultado.
--
-- Determinista: NO se usa RANDOM() ni HASH() ni CURRENT_DATE. Cada cifra se
-- deriva por aritmetica de los indices de su propia fila. Dos cargas en dos
-- cuentas distintas producen los mismos numeros, bit a bit.
--
-- Requiere haber ejecutado antes 002_tables.sql.
-- Formula completa documentada en:
--   specs/001-mock-sales-dataset/data-model.md
-- =========================================================

USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DATA;


-- ---------------------------------------------------------
-- Vaciado previo. El orden importa poco (Snowflake no impone las FK),
-- pero se vacia el hecho primero por coherencia con el modelo.
-- ---------------------------------------------------------

TRUNCATE TABLE FACT_SALES;
TRUNCATE TABLE DIM_PRODUCT;
TRUNCATE TABLE DIM_COUNTRY;


-- ---------------------------------------------------------
-- DIM_PRODUCT
-- El numero del PRODUCT_ID (P007 -> 7) es el ordinal 'p' que alimenta la
-- formula de generacion. Al anadir un producto se usa el siguiente ID libre;
-- los existentes NUNCA se renumeran, para no alterar el historico ya generado.
-- ---------------------------------------------------------

INSERT INTO DIM_PRODUCT (PRODUCT_ID, BRAND, THERAPEUTIC_AREA, BUSINESS_UNIT, LAUNCH_YEAR)
VALUES
    ('P001', 'Cardiovex',   'Cardiometabolic',        'Human Pharma',  2016),
    ('P002', 'Glycemira',   'Cardiometabolic',        'Human Pharma',  2018),
    ('P003', 'Vasculin',    'Cardiometabolic',        'Human Pharma',  2014),
    ('P004', 'Respiralia',  'Respiratory',            'Human Pharma',  2015),
    ('P005', 'Bronchoflow', 'Respiratory',            'Human Pharma',  2019),
    ('P006', 'Pulmonex',    'Respiratory',            'Human Pharma',  2021),
    ('P007', 'Oncoteva',    'Oncology',               'Human Pharma',  2020),
    ('P008', 'Onkaris',     'Oncology',               'Human Pharma',  2022),
    ('P009', 'Neurosana',   'Central Nervous System', 'Human Pharma',  2017),
    ('P010', 'Cognivia',    'Central Nervous System', 'Human Pharma',  2013),
    ('P011', 'Petvitalis',  'Animal Health',          'Animal Health', 2018),
    ('P012', 'Vetarion',    'Animal Health',          'Animal Health', 2020);


-- ---------------------------------------------------------
-- DIM_COUNTRY
-- Sin tildes ni enie: los .sql se ejecutan desde consolas Windows en cp1252.
-- ---------------------------------------------------------

INSERT INTO DIM_COUNTRY (COUNTRY_CODE, COUNTRY_NAME, REGION)
VALUES
    ('BR', 'Brasil',         'LATAM'),
    ('CA', 'Canada',         'North America'),
    ('CN', 'China',          'APAC'),
    ('DE', 'Alemania',       'Europe'),
    ('ES', 'Espana',         'Europe'),
    ('FR', 'Francia',        'Europe'),
    ('IT', 'Italia',         'Europe'),
    ('JP', 'Japon',          'APAC'),
    ('MX', 'Mexico',         'LATAM'),
    ('US', 'Estados Unidos', 'North America');


-- =========================================================
-- FACT_SALES
--
-- 12 productos x 10 paises x 3 canales x 36 meses = 12.960 filas.
--
-- Los cuatro indices que alimentan la formula:
--   p  = numero del PRODUCT_ID          (1..12)
--   c  = ordinal del pais, literal       (1..10)
--   ch = ordinal del canal, literal      (1..3)
--   m  = indice de mes desde 2023-01     (0..35)
--
-- Los ordinales de pais y canal son LITERALES a proposito: si se derivasen del
-- orden de la dimension, anadir un pais renumeraria a los demas y cambiarian
-- sus ventas de todo el historico. Al anadir un pais se le da el siguiente
-- ordinal libre (11, 12, ...) y las cifras existentes no se mueven.
-- =========================================================

INSERT INTO FACT_SALES (
    SALE_MONTH, PRODUCT_ID, COUNTRY_CODE, CHANNEL,
    UNITS_SOLD, GROSS_SALES_EUR, DISCOUNT_EUR
)
WITH COUNTRY_ORDINAL AS (
    -- Mapa codigo -> ordinal. Debe cubrir los mismos paises que DIM_COUNTRY;
    -- el test test_country_list_matches_dimension detecta cualquier desajuste.
    SELECT * FROM VALUES
        ('BR', 1), ('CA', 2), ('CN', 3), ('DE', 4), ('ES', 5),
        ('FR', 6), ('IT', 7), ('JP', 8), ('MX', 9), ('US', 10)
    AS t (COUNTRY_CODE, C)
),
CHANNELS AS (
    SELECT * FROM VALUES
        ('Hospital',        1, 1.0),
        ('Retail Pharmacy', 2, 1.4),
        ('Distributor',     3, 0.6)
    AS t (CHANNEL, CH, F_CHANNEL)
),
MONTHS AS (
    -- ROW_NUMBER en vez de SEQ4() directo: SEQ4 puede tener huecos.
    SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1 AS M
    FROM TABLE(GENERATOR(ROWCOUNT => 36))
),
GRID AS (
    SELECT
        DATEADD(month, mo.M, DATE '2023-01-01')      AS SALE_MONTH,
        p.PRODUCT_ID,
        co.COUNTRY_CODE,
        ch.CHANNEL,
        TO_NUMBER(SUBSTR(p.PRODUCT_ID, 2))           AS P,
        co.C                                         AS C,
        ch.CH                                        AS CH,
        ch.F_CHANNEL                                 AS F_CHANNEL,
        mo.M                                         AS M
    FROM DIM_PRODUCT p
    CROSS JOIN COUNTRY_ORDINAL co
    CROSS JOIN CHANNELS ch
    CROSS JOIN MONTHS mo
),
MEASURES AS (
    SELECT
        SALE_MONTH,
        PRODUCT_ID,
        COUNTRY_CODE,
        CHANNEL,
        P,
        -- Volumen base distinto por producto: 637 .. 2144 unidades
        (500 + 137 * P)                                          AS BASE_UNITS,
        -- Factor de mercado: 1.00 .. 1.60
        (1.00 + 0.15 * MOD(C, 5))                                AS F_COUNTRY,
        F_CHANNEL,
        -- Tendencia de crecimiento, con pendiente distinta por producto.
        -- Sobre 36 meses acumula entre +0% y +35%. Es lo que hace que el ranking
        -- de crecimiento interanual por area terapeutica no empate.
        (1 + 0.002 * (MOD(P, 5) + 1) * M)                        AS F_TREND,
        -- Estacionalidad anual, desfasada por producto: 0.82 .. 1.18
        (1 + 0.18 * SIN(2 * PI() * (M + P) / 12))                AS F_SEASON,
        -- Ruido determinista por modulo: 0.95 .. 1.05
        (0.95 + MOD(7 * P + 13 * C + 29 * CH + 3 * M, 11) / 100) AS F_NOISE,
        -- Precio unitario por producto: 15.75 .. 51.50 EUR
        (12.50 + 3.25 * P)                                       AS UNIT_PRICE,
        -- Tasa de descuento: 0.05 .. 0.30 (siempre <= 0.40, luego neto > 0)
        ((5 + MOD(3 * P + 7 * C + 11 * CH + M, 26)) / 100)       AS DISCOUNT_RATE
    FROM GRID
),
UNITS AS (
    SELECT
        SALE_MONTH,
        PRODUCT_ID,
        COUNTRY_CODE,
        CHANNEL,
        UNIT_PRICE,
        DISCOUNT_RATE,
        ROUND(BASE_UNITS * F_COUNTRY * F_CHANNEL * F_TREND * F_SEASON * F_NOISE) AS UNITS_SOLD
    FROM MEASURES
),
GROSS AS (
    SELECT
        SALE_MONTH,
        PRODUCT_ID,
        COUNTRY_CODE,
        CHANNEL,
        UNITS_SOLD,
        DISCOUNT_RATE,
        ROUND(UNITS_SOLD * UNIT_PRICE, 2) AS GROSS_SALES_EUR
    FROM UNITS
)
SELECT
    SALE_MONTH,
    PRODUCT_ID,
    COUNTRY_CODE,
    CHANNEL,
    UNITS_SOLD,
    GROSS_SALES_EUR,
    ROUND(GROSS_SALES_EUR * DISCOUNT_RATE, 2) AS DISCOUNT_EUR
FROM GROSS;

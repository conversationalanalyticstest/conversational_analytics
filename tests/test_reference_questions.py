"""Verifica que el dataset puede responder las 12 preguntas de referencia.

Cubre SC-003. Cada test corresponde a una fila de
`specs/001-mock-sales-dataset/contracts/reference-questions.md` y comprueba la aserción
indicada allí.

Alcance: aquí se valida el **dataset**, ejecutando la consulta SQL equivalente. La evaluación
del agente en lenguaje natural llegará con la feature del agente.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

SCHEMA = "CICD_DEMO.DATA"

NET_SALES = "SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR)"

FACT_WITH_DIMS = f"""
    FROM {SCHEMA}.FACT_SALES f
    JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
    JOIN {SCHEMA}.DIM_COUNTRY c ON c.COUNTRY_CODE = f.COUNTRY_CODE
"""


def test_q01_total_net_sales_2025(scalar: Callable[[str], Any]) -> None:
    """¿Cuáles fueron las ventas netas totales en 2025?"""
    total = scalar(
        f"""
        SELECT SUM(GROSS_SALES_EUR - DISCOUNT_EUR)
        FROM {SCHEMA}.FACT_SALES
        WHERE YEAR(SALE_MONTH) = 2025
        """
    )
    assert total is not None and total > 0


def test_q02_units_of_a_brand_in_a_country_and_year(scalar: Callable[[str], Any]) -> None:
    """¿Cuántas unidades vendimos de Respiralia en Alemania en 2024?"""
    units = scalar(
        f"""
        SELECT SUM(f.UNITS_SOLD)
        {FACT_WITH_DIMS}
        WHERE p.BRAND = 'Respiralia'
          AND c.COUNTRY_NAME = 'Germany'
          AND YEAR(f.SALE_MONTH) = 2024
        """
    )
    assert units is not None and units > 0


def test_q03_top5_brands_in_europe(fetch_all: Callable[[str], list[tuple[Any, ...]]]) -> None:
    """¿Cuál es el top 5 de marcas por ventas netas en Europa?"""
    rows = fetch_all(
        f"""
        SELECT p.BRAND, {NET_SALES} AS NET_SALES_EUR
        {FACT_WITH_DIMS}
        WHERE c.REGION = 'Europe'
        GROUP BY p.BRAND
        ORDER BY NET_SALES_EUR DESC
        LIMIT 5
        """
    )
    assert len(rows) == 5

    values = [row[1] for row in rows]
    assert len(set(values)) == 5, f"El top 5 en Europa tiene empates: {values}"
    assert values == sorted(values, reverse=True)


def test_q04_business_units_compared_in_2025(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Compara las ventas netas de Human Pharma y Animal Health en 2025."""
    rows = fetch_all(
        f"""
        SELECT p.BUSINESS_UNIT, {NET_SALES} AS NET_SALES_EUR
        FROM {SCHEMA}.FACT_SALES f
        JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
        WHERE YEAR(f.SALE_MONTH) = 2025
        GROUP BY p.BUSINESS_UNIT
        """
    )
    assert {row[0] for row in rows} == {"Human Pharma", "Animal Health"}
    assert all(row[1] > 0 for row in rows)


def test_q05_fastest_growing_therapeutic_area(fetch_one: Callable[[str], Any]) -> None:
    """¿Qué área terapéutica creció más en ventas netas de 2024 a 2025?"""
    row = fetch_one(
        f"""
        WITH BY_YEAR AS (
            SELECT p.THERAPEUTIC_AREA,
                   YEAR(f.SALE_MONTH) AS SALE_YEAR,
                   {NET_SALES} AS NET_SALES_EUR
            FROM {SCHEMA}.FACT_SALES f
            JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
            WHERE YEAR(f.SALE_MONTH) IN (2024, 2025)
            GROUP BY p.THERAPEUTIC_AREA, YEAR(f.SALE_MONTH)
        )
        SELECT THERAPEUTIC_AREA,
               MAX(IFF(SALE_YEAR = 2025, NET_SALES_EUR, NULL))
               / MAX(IFF(SALE_YEAR = 2024, NET_SALES_EUR, NULL)) - 1 AS GROWTH
        FROM BY_YEAR
        GROUP BY THERAPEUTIC_AREA
        ORDER BY GROWTH DESC
        LIMIT 1
        """
    )
    assert row is not None
    area, growth = row
    assert area
    assert growth is not None and growth != 0, "La variación interanual es nula: no hay ganador"


def test_q06_monthly_series_of_a_brand_in_a_country(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Evolución mensual de las unidades de Cardiovex en España durante 2025."""
    rows = fetch_all(
        f"""
        SELECT f.SALE_MONTH, SUM(f.UNITS_SOLD) AS UNITS
        {FACT_WITH_DIMS}
        WHERE p.BRAND = 'Cardiovex'
          AND c.COUNTRY_NAME = 'Spain'
          AND YEAR(f.SALE_MONTH) = 2025
        GROUP BY f.SALE_MONTH
        ORDER BY f.SALE_MONTH
        """
    )
    assert len(rows) == 12, "Faltan meses en la serie de 2025"
    assert [row[0].month for row in rows] == list(range(1, 13)), "La serie tiene huecos"
    assert all(row[1] > 0 for row in rows)


def test_q07_channel_with_the_highest_average_discount(fetch_one: Callable[[str], Any]) -> None:
    """¿En qué canal es mayor el descuento medio como porcentaje de las ventas brutas?"""
    row = fetch_one(
        f"""
        SELECT CHANNEL, SUM(DISCOUNT_EUR) / SUM(GROSS_SALES_EUR) AS DISCOUNT_RATE
        FROM {SCHEMA}.FACT_SALES
        GROUP BY CHANNEL
        ORDER BY DISCOUNT_RATE DESC
        LIMIT 1
        """
    )
    assert row is not None
    channel, rate = row
    assert channel in {"Hospital", "Retail Pharmacy", "Distributor"}
    assert 0 < rate < 0.40


def test_q08_net_sales_by_region_in_q4_2025(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Ventas netas por región en el cuarto trimestre de 2025."""
    rows = fetch_all(
        f"""
        SELECT c.REGION, {NET_SALES} AS NET_SALES_EUR
        {FACT_WITH_DIMS}
        WHERE f.SALE_MONTH BETWEEN DATE '2025-10-01' AND DATE '2025-12-01'
        GROUP BY c.REGION
        """
    )
    assert len(rows) == 4
    assert all(row[1] > 0 for row in rows)


def test_q09_top_country_for_animal_health(fetch_one: Callable[[str], Any]) -> None:
    """¿Cuál es el país con más unidades vendidas de productos de Animal Health?"""
    row = fetch_one(
        f"""
        SELECT c.COUNTRY_NAME, SUM(f.UNITS_SOLD) AS UNITS
        {FACT_WITH_DIMS}
        WHERE p.BUSINESS_UNIT = 'Animal Health'
        GROUP BY c.COUNTRY_NAME
        ORDER BY UNITS DESC
        LIMIT 1
        """
    )
    assert row is not None
    country, units = row
    assert country
    assert units > 0


def test_q10_hospital_channel_in_oncology_2023(scalar: Callable[[str], Any]) -> None:
    """¿Cuántas ventas netas generó el canal hospitalario en Oncology en 2023?"""
    net_sales = scalar(
        f"""
        SELECT {NET_SALES}
        FROM {SCHEMA}.FACT_SALES f
        JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
        WHERE f.CHANNEL = 'Hospital'
          AND p.THERAPEUTIC_AREA = 'Oncology'
          AND YEAR(f.SALE_MONTH) = 2023
        """
    )
    assert net_sales is not None and net_sales > 0


def test_q11_monthly_average_by_product_in_latam(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Media mensual de ventas netas por producto en LATAM."""
    rows = fetch_all(
        f"""
        SELECT p.BRAND, AVG(MONTHLY_NET) AS AVG_MONTHLY_NET
        FROM (
            SELECT f.PRODUCT_ID, f.SALE_MONTH,
                   SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS MONTHLY_NET
            FROM {SCHEMA}.FACT_SALES f
            JOIN {SCHEMA}.DIM_COUNTRY c ON c.COUNTRY_CODE = f.COUNTRY_CODE
            WHERE c.REGION = 'LATAM'
            GROUP BY f.PRODUCT_ID, f.SALE_MONTH
        ) m
        JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = m.PRODUCT_ID
        GROUP BY p.BRAND
        """
    )
    assert len(rows) == 12
    assert all(row[1] > 0 for row in rows)


def test_q12_out_of_range_year_returns_no_rows(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """¿Cuánto vendimos en 2021? Pregunta fuera de rango: cero filas, nunca un error."""
    rows = fetch_all(
        f"""
        SELECT SUM(GROSS_SALES_EUR - DISCOUNT_EUR)
        FROM {SCHEMA}.FACT_SALES
        WHERE YEAR(SALE_MONTH) = 2021
        HAVING COUNT(*) > 0
        """
    )
    assert rows == [], "2021 está fuera del histórico y no debería devolver filas"

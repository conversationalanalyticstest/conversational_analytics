"""Valida que la semantic view `SV_PHARMA_SALES` responde el catálogo de preguntas de
referencia consultando el objeto `SEMANTIC_VIEW(...)` (sintaxis `DIMENSIONS`/`METRICS`/`WHERE`)
en vez de las tablas físicas.

Cubre SC-001 y SC-002 de `specs/002-cortex-semantic-view/spec.md`. El mapeo completo
pregunta -> entrada `AI_VERIFIED_QUERIES` está en
`specs/002-cortex-semantic-view/contracts/verified-queries-mapping.md`.

Alcance: aquí se valida la semantic view. `tests/test_reference_questions.py` valida el mismo
catálogo directamente sobre las tablas físicas (`FACT_SALES`, `DIM_PRODUCT`, `DIM_COUNTRY`).

Requiere que `snowflake/004_semantic_view.sql` ya esté desplegado (ver quickstart.md).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

VIEW = "CICD_DEMO.DATA.SV_PHARMA_SALES"


# ---------------------------------------------------------------------------
# User Story 1 (P1): preguntas agregadas y filtradas
# ---------------------------------------------------------------------------


def test_q01_total_net_sales_2025(scalar: Callable[[str], Any]) -> None:
    """¿Cuáles fueron las ventas netas totales en 2025?"""
    total = scalar(
        f"""
        SELECT NET_SALES
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS SALE.YEAR
          METRICS SALE.NET_SALES
        )
        WHERE YEAR = 2025
        """
    )
    assert total is not None and total > 0


def test_q02_units_respiralia_germany_2024(scalar: Callable[[str], Any]) -> None:
    """¿Cuántas unidades vendimos de Respiralia en Alemania en 2024?"""
    units = scalar(
        f"""
        SELECT UNITS_SOLD
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS PRODUCT.BRAND, COUNTRY.COUNTRY_NAME, SALE.YEAR
          METRICS SALE.UNITS_SOLD
        )
        WHERE BRAND = 'Respiralia' AND COUNTRY_NAME = 'Germany' AND YEAR = 2024
        """
    )
    assert units is not None and units > 0


def test_q08_net_sales_by_region_q4_2025(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Ventas netas por región en el cuarto trimestre de 2025."""
    rows = fetch_all(
        f"""
        SELECT REGION, NET_SALES
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS COUNTRY.REGION, SALE.YEAR, SALE.QUARTER
          METRICS SALE.NET_SALES
        )
        WHERE YEAR = 2025 AND QUARTER = 4
        """
    )
    assert len(rows) == 4
    assert all(row[1] > 0 for row in rows)


def test_q10_net_sales_hospital_oncology_2023(scalar: Callable[[str], Any]) -> None:
    """¿Cuántas ventas netas generó el canal hospitalario en Oncology en 2023?"""
    net_sales = scalar(
        f"""
        SELECT NET_SALES
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS SALE.CHANNEL, PRODUCT.THERAPEUTIC_AREA, SALE.YEAR
          METRICS SALE.NET_SALES
        )
        WHERE CHANNEL = 'Hospital' AND THERAPEUTIC_AREA = 'Oncology' AND YEAR = 2023
        """
    )
    assert net_sales is not None and net_sales > 0


def test_edge_case_year_out_of_range_returns_no_rows(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Una pregunta sobre un año fuera del histórico (2023-2025) no da error: cero filas."""
    rows = fetch_all(
        f"""
        SELECT YEAR, NET_SALES
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS SALE.YEAR
          METRICS SALE.NET_SALES
        )
        WHERE YEAR = 2021
        """
    )
    assert rows == []


# ---------------------------------------------------------------------------
# User Story 2 (P2): comparar y rankear entre dimensiones de negocio
# ---------------------------------------------------------------------------


def test_q03_top5_brands_net_sales_europe(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """¿Cuál es el top 5 de marcas por ventas netas en Europa?"""
    rows = fetch_all(
        f"""
        SELECT BRAND, NET_SALES
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS PRODUCT.BRAND, COUNTRY.REGION
          METRICS SALE.NET_SALES
        )
        WHERE REGION = 'Europe'
        ORDER BY NET_SALES DESC
        LIMIT 5
        """
    )
    assert len(rows) == 5

    values = [row[1] for row in rows]
    assert len(set(values)) == 5, f"El top 5 en Europa tiene empates: {values}"
    assert values == sorted(values, reverse=True)


def test_q04_business_unit_comparison_2025(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Compara las ventas netas de Human Pharma y Animal Health en 2025."""
    rows = fetch_all(
        f"""
        SELECT BUSINESS_UNIT, NET_SALES
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS PRODUCT.BUSINESS_UNIT, SALE.YEAR
          METRICS SALE.NET_SALES
        )
        WHERE YEAR = 2025
        """
    )
    assert {row[0] for row in rows} == {"Human Pharma", "Animal Health"}
    assert all(row[1] > 0 for row in rows)


def test_q05_therapeutic_area_highest_growth(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """¿Qué área terapéutica creció más en ventas netas de 2024 a 2025?"""
    rows = fetch_all(
        f"""
        SELECT THERAPEUTIC_AREA, YEAR, NET_SALES
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS PRODUCT.THERAPEUTIC_AREA, SALE.YEAR
          METRICS SALE.NET_SALES
        )
        WHERE YEAR IN (2024, 2025)
        """
    )
    by_area: dict[str, dict[int, float]] = {}
    for area, year, net_sales in rows:
        by_area.setdefault(area, {})[year] = net_sales

    growth = {
        area: years[2025] / years[2024] - 1
        for area, years in by_area.items()
        if 2024 in years and 2025 in years
    }
    assert growth, "No hay áreas con datos en ambos años"

    winner = max(growth, key=lambda area: growth[area])
    assert winner
    assert growth[winner] != 0, "La variación interanual es nula: no hay ganador"


def test_q09_country_most_units_animal_health(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """¿Cuál es el país con más unidades vendidas de productos de Animal Health?"""
    rows = fetch_all(
        f"""
        SELECT COUNTRY_NAME, UNITS_SOLD
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS COUNTRY.COUNTRY_NAME, PRODUCT.BUSINESS_UNIT
          METRICS SALE.UNITS_SOLD
        )
        WHERE BUSINESS_UNIT = 'Animal Health'
        ORDER BY UNITS_SOLD DESC
        LIMIT 1
        """
    )
    assert len(rows) == 1
    country, units = rows[0]
    assert country
    assert units > 0


# ---------------------------------------------------------------------------
# User Story 3 (P3): métricas derivadas y series temporales
# ---------------------------------------------------------------------------


def test_q06_monthly_evolution_cardiovex_spain_2025(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Evolución mensual de las unidades de Cardiovex en España durante 2025."""
    rows = fetch_all(
        f"""
        SELECT MONTH, UNITS_SOLD
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS PRODUCT.BRAND, COUNTRY.COUNTRY_NAME, SALE.MONTH, SALE.YEAR
          METRICS SALE.UNITS_SOLD
        )
        WHERE BRAND = 'Cardiovex' AND COUNTRY_NAME = 'Spain' AND YEAR = 2025
        ORDER BY MONTH
        """
    )
    assert len(rows) == 12, "Faltan meses en la serie de 2025"
    assert [row[0].month for row in rows] == list(range(1, 13)), "La serie tiene huecos"
    assert all(row[1] > 0 for row in rows)


def test_q07_channel_highest_discount_rate(fetch_one: Callable[[str], Any]) -> None:
    """¿En qué canal es mayor el descuento medio como porcentaje de las ventas brutas?"""
    row = fetch_one(
        f"""
        SELECT CHANNEL, DISCOUNT_RATE
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS SALE.CHANNEL
          METRICS AVG_DISCOUNT_RATE AS DISCOUNT_RATE
        )
        ORDER BY DISCOUNT_RATE DESC
        LIMIT 1
        """
    )
    assert row is not None
    channel, rate = row
    assert channel in {"Hospital", "Retail Pharmacy", "Distributor"}
    assert 0 < rate < 0.40


def test_q11_avg_monthly_net_sales_per_product_latam(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Media mensual de ventas netas por producto en LATAM."""
    rows = fetch_all(
        f"""
        SELECT BRAND, AVG_NET_SALES
        FROM SEMANTIC_VIEW(
          {VIEW}
          DIMENSIONS PRODUCT.BRAND, COUNTRY.REGION
          METRICS SALE.AVG_NET_SALES
        )
        WHERE REGION = 'LATAM'
        """
    )
    assert len(rows) == 12, "Deberia haber una fila por producto"
    assert all(row[1] > 0 for row in rows)

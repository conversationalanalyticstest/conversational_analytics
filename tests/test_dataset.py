"""Verifica las invariantes del contrato del dataset.

Cada test corresponde a una invariante de `specs/001-mock-sales-dataset/data-model.md` y al
mapa de `contracts/dataset-contract.md`. Son tests de solo lectura salvo el marcado
`writes_db`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

SCHEMA = "CICD_DEMO.DATA"

EXPECTED_PRODUCTS = 12
EXPECTED_COUNTRIES = 10
EXPECTED_CHANNELS = {"Hospital", "Retail Pharmacy", "Distributor"}
EXPECTED_MONTHS = 36
EXPECTED_COMBINATIONS = EXPECTED_PRODUCTS * EXPECTED_COUNTRIES * len(EXPECTED_CHANNELS)
EXPECTED_FACT_ROWS = EXPECTED_COMBINATIONS * EXPECTED_MONTHS  # 12.960

FIRST_MONTH = "2023-01-01"
LAST_MONTH = "2025-12-01"

MAX_DISCOUNT_RATE = 0.40

EXPECTED_THERAPEUTIC_AREAS = {
    "Cardiometabolic",
    "Respiratory",
    "Oncology",
    "Central Nervous System",
    "Animal Health",
}
EXPECTED_BUSINESS_UNITS = {"Human Pharma", "Animal Health"}
EXPECTED_REGIONS = {"Europe", "North America", "LATAM", "APAC"}

HISTORY_START_YEAR = 2023


# --------------------------------------------------------------------------------------
# I-01 (dimensiones) — recuentos
# --------------------------------------------------------------------------------------


def test_dimension_row_counts(scalar: Callable[[str], Any]) -> None:
    assert scalar(f"SELECT COUNT(*) FROM {SCHEMA}.DIM_PRODUCT") == EXPECTED_PRODUCTS
    assert scalar(f"SELECT COUNT(*) FROM {SCHEMA}.DIM_COUNTRY") == EXPECTED_COUNTRIES


def test_brands_are_unique(scalar: Callable[[str], Any]) -> None:
    assert scalar(f"SELECT COUNT(DISTINCT BRAND) FROM {SCHEMA}.DIM_PRODUCT") == EXPECTED_PRODUCTS


# --------------------------------------------------------------------------------------
# I-03 — ausencia de nulos en las dimensiones
# --------------------------------------------------------------------------------------


def test_no_nulls_in_dimensions(scalar: Callable[[str], Any]) -> None:
    product_nulls = scalar(
        f"""
        SELECT COUNT(*) FROM {SCHEMA}.DIM_PRODUCT
        WHERE PRODUCT_ID IS NULL OR BRAND IS NULL OR THERAPEUTIC_AREA IS NULL
           OR BUSINESS_UNIT IS NULL OR LAUNCH_YEAR IS NULL
        """
    )
    assert product_nulls == 0, "DIM_PRODUCT contiene nulos"

    country_nulls = scalar(
        f"""
        SELECT COUNT(*) FROM {SCHEMA}.DIM_COUNTRY
        WHERE COUNTRY_CODE IS NULL OR COUNTRY_NAME IS NULL OR REGION IS NULL
        """
    )
    assert country_nulls == 0, "DIM_COUNTRY contiene nulos"


# --------------------------------------------------------------------------------------
# I-07 — dominios cerrados
# --------------------------------------------------------------------------------------


def test_therapeutic_areas_match_the_closed_domain(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    areas = {row[0] for row in fetch_all(f"SELECT DISTINCT THERAPEUTIC_AREA FROM {SCHEMA}.DIM_PRODUCT")}
    assert areas == EXPECTED_THERAPEUTIC_AREAS


def test_business_units_match_the_closed_domain_with_minimum_products(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    rows = fetch_all(
        f"SELECT BUSINESS_UNIT, COUNT(*) FROM {SCHEMA}.DIM_PRODUCT GROUP BY BUSINESS_UNIT"
    )
    counts = dict(rows)
    assert set(counts) == EXPECTED_BUSINESS_UNITS
    for unit, count in counts.items():
        assert count >= 2, f"La unidad de negocio {unit!r} tiene solo {count} producto(s), se exigen >= 2"


def test_regions_match_the_closed_domain_with_minimum_countries(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    rows = fetch_all(f"SELECT REGION, COUNT(*) FROM {SCHEMA}.DIM_COUNTRY GROUP BY REGION")
    counts = dict(rows)
    assert set(counts) == EXPECTED_REGIONS
    for region, count in counts.items():
        assert count >= 2, f"La region {region!r} tiene solo {count} pais(es), se exigen >= 2"


# --------------------------------------------------------------------------------------
# I-08 — todos los productos se lanzaron antes del histórico
# --------------------------------------------------------------------------------------


def test_launch_years_precede_history(scalar: Callable[[str], Any]) -> None:
    max_year = scalar(f"SELECT MAX(LAUNCH_YEAR) FROM {SCHEMA}.DIM_PRODUCT")
    assert max_year < HISTORY_START_YEAR, (
        f"Hay productos lanzados en {max_year}, dentro del histórico. "
        "Eso dejaría meses sin ventas y rompería la rejilla completa (FR-005)."
    )


# ======================================================================================
# User Story 1 — el dataset responde a preguntas con filtros multidimensionales
# ======================================================================================


# --------------------------------------------------------------------------------------
# I-01 (hecho), I-02, I-11, I-12 — volumen y rejilla
# --------------------------------------------------------------------------------------


def test_fact_row_count(scalar: Callable[[str], Any]) -> None:
    assert scalar(f"SELECT COUNT(*) FROM {SCHEMA}.FACT_SALES") == EXPECTED_FACT_ROWS


def test_month_grid_is_complete(fetch_one: Callable[[str], Any], scalar: Callable[[str], Any]) -> None:
    row = fetch_one(
        f"""
        SELECT COUNT(DISTINCT SALE_MONTH), MIN(SALE_MONTH), MAX(SALE_MONTH)
        FROM {SCHEMA}.FACT_SALES
        """
    )
    assert row is not None
    distinct_months, first_month, last_month = row

    assert distinct_months == EXPECTED_MONTHS
    assert str(first_month) == FIRST_MONTH
    assert str(last_month) == LAST_MONTH

    # Sin huecos: entre dos meses consecutivos siempre hay exactamente un mes de distancia.
    gaps = scalar(
        f"""
        SELECT COUNT(*) FROM (
            SELECT DATEDIFF(month, LAG(SALE_MONTH) OVER (ORDER BY SALE_MONTH), SALE_MONTH) AS STEP
            FROM (SELECT DISTINCT SALE_MONTH FROM {SCHEMA}.FACT_SALES)
        )
        WHERE STEP IS NOT NULL AND STEP <> 1
        """
    )
    assert gaps == 0, "La serie de meses tiene huecos"


def test_every_combination_has_all_months(scalar: Callable[[str], Any]) -> None:
    incomplete = scalar(
        f"""
        SELECT COUNT(*) FROM (
            SELECT PRODUCT_ID, COUNTRY_CODE, CHANNEL, COUNT(DISTINCT SALE_MONTH) AS MONTHS
            FROM {SCHEMA}.FACT_SALES
            GROUP BY PRODUCT_ID, COUNTRY_CODE, CHANNEL
            HAVING COUNT(DISTINCT SALE_MONTH) <> {EXPECTED_MONTHS}
        )
        """
    )
    assert incomplete == 0, "Hay combinaciones producto x pais x canal con meses faltantes"


def test_combination_count(scalar: Callable[[str], Any]) -> None:
    combinations = scalar(
        f"""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT PRODUCT_ID, COUNTRY_CODE, CHANNEL FROM {SCHEMA}.FACT_SALES
        )
        """
    )
    assert combinations == EXPECTED_COMBINATIONS


def test_country_list_matches_dimension(fetch_all: Callable[[str], list[tuple[Any, ...]]]) -> None:
    """I-12: detecta que la lista de ordinales de 003_seed.sql se desincronice de DIM_COUNTRY."""
    in_fact = {row[0] for row in fetch_all(f"SELECT DISTINCT COUNTRY_CODE FROM {SCHEMA}.FACT_SALES")}
    in_dim = {row[0] for row in fetch_all(f"SELECT COUNTRY_CODE FROM {SCHEMA}.DIM_COUNTRY")}
    assert in_fact == in_dim, (
        "Los paises de FACT_SALES no coinciden con DIM_COUNTRY. "
        "Probablemente falta anadir el pais al CTE COUNTRY_ORDINAL de 003_seed.sql."
    )


def test_channels_match_the_closed_domain(fetch_all: Callable[[str], list[tuple[Any, ...]]]) -> None:
    channels = {row[0] for row in fetch_all(f"SELECT DISTINCT CHANNEL FROM {SCHEMA}.FACT_SALES")}
    assert channels == EXPECTED_CHANNELS


# --------------------------------------------------------------------------------------
# I-03 (hecho), I-04 — nulos y referencias huérfanas
# --------------------------------------------------------------------------------------


def test_no_nulls_in_fact(scalar: Callable[[str], Any]) -> None:
    nulls = scalar(
        f"""
        SELECT COUNT(*) FROM {SCHEMA}.FACT_SALES
        WHERE SALE_MONTH IS NULL OR PRODUCT_ID IS NULL OR COUNTRY_CODE IS NULL
           OR CHANNEL IS NULL OR UNITS_SOLD IS NULL OR GROSS_SALES_EUR IS NULL
           OR DISCOUNT_EUR IS NULL
        """
    )
    assert nulls == 0, "FACT_SALES contiene nulos"


def test_no_orphan_references(scalar: Callable[[str], Any]) -> None:
    orphans = scalar(
        f"""
        SELECT COUNT(*)
        FROM {SCHEMA}.FACT_SALES f
        LEFT JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
        LEFT JOIN {SCHEMA}.DIM_COUNTRY c ON c.COUNTRY_CODE = f.COUNTRY_CODE
        WHERE p.PRODUCT_ID IS NULL OR c.COUNTRY_CODE IS NULL
        """
    )
    assert orphans == 0, "Hay ventas que referencian productos o paises inexistentes"


# --------------------------------------------------------------------------------------
# I-05, I-06, I-10 — coherencia de las medidas
# --------------------------------------------------------------------------------------


def test_units_and_gross_are_positive(scalar: Callable[[str], Any]) -> None:
    bad = scalar(
        f"""
        SELECT COUNT(*) FROM {SCHEMA}.FACT_SALES
        WHERE UNITS_SOLD <= 0 OR GROSS_SALES_EUR <= 0 OR DISCOUNT_EUR < 0
        """
    )
    assert bad == 0, "Hay unidades o ventas brutas no positivas, o descuentos negativos"


def test_net_sales_always_positive(scalar: Callable[[str], Any]) -> None:
    bad = scalar(
        f"""
        SELECT COUNT(*) FROM {SCHEMA}.FACT_SALES
        WHERE GROSS_SALES_EUR - DISCOUNT_EUR <= 0
        """
    )
    assert bad == 0, "Hay filas con ventas netas negativas o cero"


def test_net_sales_total_matches_gross_minus_discount(fetch_one: Callable[[str], Any]) -> None:
    """Escenario 4 de la User Story 1 del spec."""
    row = fetch_one(
        f"""
        SELECT SUM(GROSS_SALES_EUR - DISCOUNT_EUR),
               SUM(GROSS_SALES_EUR) - SUM(DISCOUNT_EUR)
        FROM {SCHEMA}.FACT_SALES
        """
    )
    assert row is not None
    assert row[0] == row[1]


def test_discount_rate_within_bounds(scalar: Callable[[str], Any]) -> None:
    bad = scalar(
        f"""
        SELECT COUNT(*) FROM {SCHEMA}.FACT_SALES
        WHERE DISCOUNT_EUR / GROSS_SALES_EUR < 0
           OR DISCOUNT_EUR / GROSS_SALES_EUR > {MAX_DISCOUNT_RATE}
        """
    )
    assert bad == 0, f"Hay descuentos fuera del rango [0, {MAX_DISCOUNT_RATE}]"


def test_brand_ranking_has_no_ties(fetch_all: Callable[[str], list[tuple[Any, ...]]]) -> None:
    """I-10: sin empates no hay ambiguedad en las preguntas de ranking del agente."""
    rows = fetch_all(
        f"""
        SELECT p.BRAND, SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS NET_SALES_EUR
        FROM {SCHEMA}.FACT_SALES f
        JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
        GROUP BY p.BRAND
        ORDER BY NET_SALES_EUR DESC
        LIMIT 5
        """
    )
    assert len(rows) == 5
    values = [row[1] for row in rows]
    assert len(set(values)) == 5, f"El top-5 de marcas tiene empates: {values}"


# --------------------------------------------------------------------------------------
# Escenarios de aceptación de la User Story 1
# --------------------------------------------------------------------------------------


def test_aggregation_by_country_and_year_returns_a_positive_number(
    scalar: Callable[[str], Any],
) -> None:
    net_sales = scalar(
        f"""
        SELECT SUM(GROSS_SALES_EUR - DISCOUNT_EUR)
        FROM {SCHEMA}.FACT_SALES
        WHERE COUNTRY_CODE = 'ES' AND YEAR(SALE_MONTH) = 2025
        """
    )
    assert net_sales is not None and net_sales > 0


def test_grouping_by_therapeutic_area_covers_the_whole_domain(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    rows = fetch_all(
        f"""
        SELECT p.THERAPEUTIC_AREA, SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR)
        FROM {SCHEMA}.FACT_SALES f
        JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
        GROUP BY p.THERAPEUTIC_AREA
        """
    )
    assert {row[0] for row in rows} == EXPECTED_THERAPEUTIC_AREAS
    assert all(row[1] > 0 for row in rows)


def test_business_unit_and_channel_combinations_have_data(scalar: Callable[[str], Any]) -> None:
    combinations = scalar(
        f"""
        SELECT COUNT(*) FROM (
            SELECT p.BUSINESS_UNIT, f.CHANNEL
            FROM {SCHEMA}.FACT_SALES f
            JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
            GROUP BY p.BUSINESS_UNIT, f.CHANNEL
        )
        """
    )
    assert combinations == len(EXPECTED_BUSINESS_UNITS) * len(EXPECTED_CHANNELS)


def test_out_of_range_year_returns_no_rows(fetch_all: Callable[[str], list[tuple[Any, ...]]]) -> None:
    """Caso límite del spec: preguntar fuera del histórico da cero filas, no un error."""
    rows = fetch_all(
        f"""
        SELECT SALE_MONTH FROM {SCHEMA}.FACT_SALES WHERE YEAR(SALE_MONTH) = 2021
        """
    )
    assert rows == []


# ======================================================================================
# User Story 2 — comparar evolución temporal
#
# Tras US1 los 36 meses existen, pero las cifras son planas en el tiempo: un ranking de
# crecimiento empataría y una serie mensual sería una recta. Estos tests exigen que la
# fórmula incorpore tendencia y estacionalidad.
# ======================================================================================


def test_yoy_growth_by_area_has_no_ties(
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """La pregunta '¿qué área creció más de 2024 a 2025?' debe tener un ganador único."""
    rows = fetch_all(
        f"""
        WITH BY_YEAR AS (
            SELECT p.THERAPEUTIC_AREA,
                   YEAR(f.SALE_MONTH) AS SALE_YEAR,
                   SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS NET_SALES_EUR
            FROM {SCHEMA}.FACT_SALES f
            JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
            WHERE YEAR(f.SALE_MONTH) IN (2024, 2025)
            GROUP BY p.THERAPEUTIC_AREA, YEAR(f.SALE_MONTH)
        )
        SELECT THERAPEUTIC_AREA,
               ROUND(
                   (MAX(IFF(SALE_YEAR = 2025, NET_SALES_EUR, NULL))
                    / MAX(IFF(SALE_YEAR = 2024, NET_SALES_EUR, NULL)) - 1) * 100,
                   4
               ) AS GROWTH_PCT
        FROM BY_YEAR
        GROUP BY THERAPEUTIC_AREA
        ORDER BY GROWTH_PCT DESC
        """
    )
    assert len(rows) == len(EXPECTED_THERAPEUTIC_AREAS)

    growths = [row[1] for row in rows]
    assert all(g is not None for g in growths), "Falta algún año para alguna área terapéutica"
    assert len(set(growths)) == len(growths), (
        f"El ranking de crecimiento interanual tiene empates: {growths}. "
        "Falta el factor de tendencia diferenciado por producto en 003_seed.sql."
    )


def test_monthly_series_varies(fetch_all: Callable[[str], list[tuple[Any, ...]]]) -> None:
    """La evolución mensual debe tener forma, no ser una recta ni una escalera monótona."""
    rows = fetch_all(
        f"""
        SELECT f.SALE_MONTH, SUM(f.UNITS_SOLD) AS UNITS
        FROM {SCHEMA}.FACT_SALES f
        JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
        WHERE p.BRAND = 'Cardiovex' AND f.COUNTRY_CODE = 'ES'
        GROUP BY f.SALE_MONTH
        ORDER BY f.SALE_MONTH
        """
    )
    assert len(rows) == EXPECTED_MONTHS

    units = [row[1] for row in rows]
    assert len(set(units)) >= 30, f"La serie mensual apenas varía: {len(set(units))} valores distintos"

    # Estacionalidad: la serie sube y baja, no es monótona.
    deltas = [b - a for a, b in zip(units, units[1:])]
    assert any(d > 0 for d in deltas) and any(d < 0 for d in deltas), (
        "La serie mensual es monótona. Falta el factor estacional en 003_seed.sql."
    )


def test_all_three_years_have_data(fetch_all: Callable[[str], list[tuple[Any, ...]]]) -> None:
    rows = fetch_all(
        f"""
        SELECT YEAR(SALE_MONTH) AS SALE_YEAR, SUM(GROSS_SALES_EUR - DISCOUNT_EUR)
        FROM {SCHEMA}.FACT_SALES
        GROUP BY YEAR(SALE_MONTH)
        ORDER BY SALE_YEAR
        """
    )
    assert [row[0] for row in rows] == [2023, 2024, 2025]
    assert all(row[1] > 0 for row in rows)


# ======================================================================================
# User Story 3 — regeneración reproducible
# ======================================================================================

FINGERPRINT_SQL = f"""
    SELECT COUNT(*),
           SUM(UNITS_SOLD),
           SUM(GROSS_SALES_EUR),
           SUM(DISCOUNT_EUR),
           MIN(SALE_MONTH),
           MAX(SALE_MONTH)
    FROM {SCHEMA}.FACT_SALES
"""

SEED_SCRIPT = Path(__file__).resolve().parents[1] / "snowflake" / "003_seed.sql"


@pytest.mark.writes_db
def test_reload_is_idempotent(sf_conn: Any, fetch_one: Callable[[str], Any]) -> None:
    """I-09: recargar el dataset deja exactamente las mismas cifras.

    Este test RECARGA los datos. Excluirlo con: pytest -m "not writes_db"
    """
    before = fetch_one(FINGERPRINT_SQL)

    for cursor in sf_conn.execute_string(SEED_SCRIPT.read_text(encoding="utf-8")):
        cursor.close()

    after = fetch_one(FINGERPRINT_SQL)

    assert before == after, (
        "La recarga ha producido cifras distintas. Hay una fuente de no determinismo "
        f"en {SEED_SCRIPT.name}.\n  antes:   {before}\n  después: {after}"
    )




"""Suite de evaluacion del agente (Principio II, NON-NEGOTIABLE).

Cubre las 12 preguntas de
`specs/001-mock-sales-dataset/contracts/reference-questions.md`. Los asserts comparan
`AgentResponse.rows` contra el valor exacto de una consulta baseline determinista sobre las
tablas base (decision D-07 revisada en research.md): no un umbral generico como `> 0`, que un
agente que alucine cualquier numero positivo pasaria igual.

El SQL baseline es el mismo que ya usa `tests/test_reference_questions.py` (feature 001) para
verificar el dataset; aqui se reutiliza como oro de referencia, no se reescribe.

Cada pregunta se paga una unica vez por sesion de test gracias a la fixture `agent_answer`
(cacheada, T010) — Principio IV, control de coste.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from conversational_analytics.agent import AgentResponse, AgentStatus

SCHEMA = "CICD_DEMO.DATA"
NET_SALES = "SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR)"
FACT_WITH_DIMS = f"""
    FROM {SCHEMA}.FACT_SALES f
    JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
    JOIN {SCHEMA}.DIM_COUNTRY c ON c.COUNTRY_CODE = f.COUNTRY_CODE
"""

REL_TOL = 1e-6


def _numeric_values(row: dict[str, Any]) -> list[float]:
    """Valores numericos de una fila, en el orden en que los devolvio el SQL ejecutado.

    El conector de Snowflake devuelve `decimal.Decimal` para columnas `NUMBER` con escala
    (la mayoria de los agregados de este dataset), no `float` nativo: hay que aceptarlo
    explicitamente o se descartan en silencio y el test falla con un `IndexError` que
    despista (parece que no hay valores, cuando en realidad los hay pero no se reconocen).
    """
    return [
        float(value)
        for value in row.values()
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
    ]


def _assert_matches_baseline(actual: float, expected: float) -> None:
    assert not math.isnan(actual)
    assert actual == pytest.approx(expected, rel=REL_TOL), (
        f"El agente devolvio {actual}, la consulta baseline da {expected}"
    )


def _assert_common_invariants(response: AgentResponse) -> None:
    """Asserts transversales, aplicables a Q-01..Q-11 (todas `status == OK`)."""
    assert response.status != AgentStatus.ERROR
    assert response.answer.strip() != ""
    assert response.sql is not None
    assert response.usage.prompt_tokens > 0
    assert response.latency_ms > 0
    configured_provider = os.environ.get("LLM_PROVIDER", "openai")
    assert response.usage.provider == configured_provider


def test_q01_total_net_sales_2025(
    agent_answer: Callable[[str], AgentResponse], scalar: Callable[[str], Any]
) -> None:
    """¿Cuáles fueron las ventas netas totales en 2025?"""
    baseline = scalar(
        f"""
        SELECT SUM(GROSS_SALES_EUR - DISCOUNT_EUR)
        FROM {SCHEMA}.FACT_SALES
        WHERE YEAR(SALE_MONTH) = 2025
        """
    )
    response = agent_answer("¿Cuáles fueron las ventas netas totales en 2025?")
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) == 1
    values = _numeric_values(response.rows[0])
    assert len(values) == 1
    # DEMO: assert roto a proposito para el Escenario 1 de quickstart.md (revertir tras la demo).
    _assert_matches_baseline(values[0], float(baseline) + 1)


def test_q02_units_of_a_brand_in_a_country_and_year(
    agent_answer: Callable[[str], AgentResponse], scalar: Callable[[str], Any]
) -> None:
    """¿Cuántas unidades vendimos de Respiralia en Alemania en 2024?"""
    baseline = scalar(
        f"""
        SELECT SUM(f.UNITS_SOLD)
        {FACT_WITH_DIMS}
        WHERE p.BRAND = 'Respiralia'
          AND c.COUNTRY_NAME = 'Germany'
          AND YEAR(f.SALE_MONTH) = 2024
        """
    )
    response = agent_answer("¿Cuántas unidades vendimos de Respiralia en Alemania en 2024?")
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) == 1
    values = _numeric_values(response.rows[0])
    assert len(values) == 1
    _assert_matches_baseline(values[0], float(baseline))


def test_q03_top5_brands_in_europe(
    agent_answer: Callable[[str], AgentResponse],
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """¿Cuál es el top 5 de marcas por ventas netas en Europa?"""
    baseline_rows = fetch_all(
        f"""
        SELECT p.BRAND, {NET_SALES} AS NET_SALES_EUR
        {FACT_WITH_DIMS}
        WHERE c.REGION = 'Europe'
        GROUP BY p.BRAND
        ORDER BY NET_SALES_EUR DESC
        LIMIT 5
        """
    )
    baseline_values = [float(row[1]) for row in baseline_rows]

    response = agent_answer("¿Cuál es el top 5 de marcas por ventas netas en Europa?")
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) == 5

    actual_values = [_numeric_values(row)[0] for row in response.rows]
    for actual, expected in zip(actual_values, baseline_values, strict=True):
        _assert_matches_baseline(actual, expected)


def test_q04_business_units_compared_in_2025(
    agent_answer: Callable[[str], AgentResponse],
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Compara las ventas netas de Human Pharma y Animal Health en 2025."""
    baseline_rows = fetch_all(
        f"""
        SELECT p.BUSINESS_UNIT, {NET_SALES} AS NET_SALES_EUR
        FROM {SCHEMA}.FACT_SALES f
        JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
        WHERE YEAR(f.SALE_MONTH) = 2025
        GROUP BY p.BUSINESS_UNIT
        """
    )
    baseline_by_unit = {row[0]: float(row[1]) for row in baseline_rows}
    assert set(baseline_by_unit) == {"Human Pharma", "Animal Health"}

    response = agent_answer(
        "Compara las ventas netas de Human Pharma y Animal Health en 2025."
    )
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) == 2

    baseline_total = sum(baseline_by_unit.values())
    actual_total = sum(_numeric_values(row)[0] for row in response.rows)
    _assert_matches_baseline(actual_total, baseline_total)


def test_q05_fastest_growing_therapeutic_area(
    agent_answer: Callable[[str], AgentResponse], fetch_one: Callable[[str], Any]
) -> None:
    """¿En qué área terapéutica aumentaron más las ventas netas, en euros, de 2024 a 2025?

    El crecimiento se pide explícitamente en euros (no en porcentaje) porque así lo calcula
    la verified query `q05_therapeutic_area_highest_growth` ya desplegada en la feature 002
    (ver specs/002-cortex-semantic-view/contracts/semantic-view-ddl.md): diferencia absoluta
    de NET_SALES entre 2025 y 2024, no una tasa. Una redacción ambigua ("creció más") deja que
    Cortex Analyst y el baseline interpreten "crecimiento" de forma distinta (absoluto vs. %).
    """
    baseline_row = fetch_one(
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
               SUM(IFF(SALE_YEAR = 2025, NET_SALES_EUR, -NET_SALES_EUR)) AS GROWTH
        FROM BY_YEAR
        GROUP BY THERAPEUTIC_AREA
        ORDER BY GROWTH DESC
        LIMIT 1
        """
    )
    assert baseline_row is not None
    baseline_area, _ = baseline_row

    response = agent_answer(
        "¿En qué área terapéutica aumentaron más las ventas netas, en euros, de 2024 a 2025?"
    )
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) >= 1
    row_text = " ".join(str(v) for v in response.rows[0].values())
    assert baseline_area in row_text


def test_q06_monthly_series_of_a_brand_in_a_country(
    agent_answer: Callable[[str], AgentResponse],
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Evolución mensual de las unidades de Cardiovex en España durante 2025."""
    baseline_rows = fetch_all(
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
    assert len(baseline_rows) == 12
    baseline_total = sum(float(row[1]) for row in baseline_rows)

    response = agent_answer(
        "Evolución mensual de las unidades de Cardiovex en España durante 2025."
    )
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) == 12
    actual_total = sum(_numeric_values(row)[0] for row in response.rows)
    _assert_matches_baseline(actual_total, baseline_total)


def test_q07_channel_with_the_highest_average_discount(
    agent_answer: Callable[[str], AgentResponse], fetch_one: Callable[[str], Any]
) -> None:
    """¿En qué canal es mayor el descuento medio como porcentaje de las ventas brutas?"""
    baseline_row = fetch_one(
        f"""
        SELECT CHANNEL, SUM(DISCOUNT_EUR) / SUM(GROSS_SALES_EUR) AS DISCOUNT_RATE
        FROM {SCHEMA}.FACT_SALES
        GROUP BY CHANNEL
        ORDER BY DISCOUNT_RATE DESC
        LIMIT 1
        """
    )
    assert baseline_row is not None
    baseline_channel, baseline_rate = baseline_row

    response = agent_answer(
        "¿En qué canal es mayor el descuento medio como porcentaje de las ventas brutas?"
    )
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) >= 1
    row_text = " ".join(str(v) for v in response.rows[0].values())
    assert baseline_channel in row_text
    values = _numeric_values(response.rows[0])
    assert len(values) >= 1
    _assert_matches_baseline(values[0], float(baseline_rate))


def test_q08_net_sales_by_region_in_q4_2025(
    agent_answer: Callable[[str], AgentResponse],
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Ventas netas por región en el cuarto trimestre de 2025."""
    baseline_rows = fetch_all(
        f"""
        SELECT c.REGION, {NET_SALES} AS NET_SALES_EUR
        {FACT_WITH_DIMS}
        WHERE f.SALE_MONTH BETWEEN DATE '2025-10-01' AND DATE '2025-12-01'
        GROUP BY c.REGION
        """
    )
    assert len(baseline_rows) == 4
    baseline_total = sum(float(row[1]) for row in baseline_rows)

    response = agent_answer("Ventas netas por región en el cuarto trimestre de 2025.")
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) == 4
    actual_total = sum(_numeric_values(row)[0] for row in response.rows)
    _assert_matches_baseline(actual_total, baseline_total)


def test_q09_top_country_for_animal_health(
    agent_answer: Callable[[str], AgentResponse], fetch_one: Callable[[str], Any]
) -> None:
    """¿Cuál es el país con más unidades vendidas de productos de Animal Health?"""
    baseline_row = fetch_one(
        f"""
        SELECT c.COUNTRY_NAME, SUM(f.UNITS_SOLD) AS UNITS
        {FACT_WITH_DIMS}
        WHERE p.BUSINESS_UNIT = 'Animal Health'
        GROUP BY c.COUNTRY_NAME
        ORDER BY UNITS DESC
        LIMIT 1
        """
    )
    assert baseline_row is not None
    baseline_country, _ = baseline_row

    response = agent_answer(
        "¿Cuál es el país con más unidades vendidas de productos de Animal Health?"
    )
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) >= 1
    row_text = " ".join(str(v) for v in response.rows[0].values())
    assert baseline_country in row_text


def test_q10_hospital_channel_in_oncology_2023(
    agent_answer: Callable[[str], AgentResponse], scalar: Callable[[str], Any]
) -> None:
    """¿Cuántas ventas netas generó el canal hospitalario en Oncology en 2023?"""
    baseline = scalar(
        f"""
        SELECT {NET_SALES}
        FROM {SCHEMA}.FACT_SALES f
        JOIN {SCHEMA}.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
        WHERE f.CHANNEL = 'Hospital'
          AND p.THERAPEUTIC_AREA = 'Oncology'
          AND YEAR(f.SALE_MONTH) = 2023
        """
    )
    response = agent_answer(
        "¿Cuántas ventas netas generó el canal hospitalario en Oncology en 2023?"
    )
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) == 1
    values = _numeric_values(response.rows[0])
    assert len(values) == 1
    _assert_matches_baseline(values[0], float(baseline))


def test_q11_monthly_average_by_product_in_latam(
    agent_answer: Callable[[str], AgentResponse],
    fetch_all: Callable[[str], list[tuple[Any, ...]]],
) -> None:
    """Media mensual de ventas netas por producto en LATAM."""
    baseline_rows = fetch_all(
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
    assert len(baseline_rows) == 12
    baseline_total = sum(float(row[1]) for row in baseline_rows)

    response = agent_answer("Media mensual de ventas netas por producto en LATAM.")
    _assert_common_invariants(response)
    assert response.status == AgentStatus.OK
    assert len(response.rows) == 12
    actual_total = sum(_numeric_values(row)[0] for row in response.rows)
    _assert_matches_baseline(actual_total, baseline_total)


def test_q12_out_of_range_year_returns_no_data(
    agent_answer: Callable[[str], AgentResponse],
) -> None:
    """¿Cuánto vendimos en 2021? Fuera de rango: NO_DATA, nunca una cifra inventada."""
    response = agent_answer("¿Cuánto vendimos en 2021?")
    assert response.status == AgentStatus.NO_DATA
    assert response.rows == []
    assert response.answer.strip() != ""

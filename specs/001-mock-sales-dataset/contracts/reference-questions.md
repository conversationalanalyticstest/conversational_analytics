# Catálogo de preguntas de referencia

**Feature**: `001-mock-sales-dataset` | **Fecha**: 2026-08-31 | **Fase**: 1

Cubre **SC-003** y siembra la suite de evaluación del agente que exige el Principio II de la
constitución.

**Alcance en esta feature**: se verifica que el dataset **puede responder** cada pregunta —
es decir, que la consulta SQL equivalente devuelve un resultado no vacío y numéricamente
válido. La evaluación del agente en lenguaje natural llegará con la feature del agente; este
fichero es su punto de partida.

## Preguntas

| # | Pregunta | Tipo | Dimensiones implicadas | Aserción esperada |
|---|---|---|---|---|
| Q-01 | ¿Cuáles fueron las ventas netas totales en 2025? | Agregación simple | tiempo | Un único número `> 0` |
| Q-02 | ¿Cuántas unidades vendimos de Respiralia en Alemania en 2024? | Filtro multidimensional | marca, país, tiempo | Un único entero `> 0` |
| Q-03 | ¿Cuál es el top 5 de marcas por ventas netas en Europa? | Ranking | marca, región | 5 filas, valores distintos, orden descendente |
| Q-04 | Compara las ventas netas de Human Pharma y Animal Health en 2025. | Comparativa categórica | unidad de negocio, tiempo | 2 filas, ambas `> 0` |
| Q-05 | ¿En qué área terapéutica aumentaron más las ventas netas, en euros, de 2024 a 2025? | Comparativa interanual | área terapéutica, tiempo | 1 área, variación no nula |
| Q-06 | Evolución mensual de las unidades de Cardiovex en España durante 2025. | Serie temporal | marca, país, tiempo | 12 filas, una por mes, sin huecos |
| Q-07 | ¿En qué canal es mayor el descuento medio como porcentaje de las ventas brutas? | Métrica derivada + ranking | canal | 1 canal, ratio entre 0 y 0.40 |
| Q-08 | Ventas netas por región en el cuarto trimestre de 2025. | Filtro temporal parcial | región, tiempo | 4 filas, todas `> 0` |
| Q-09 | ¿Cuál es el país con más unidades vendidas de productos de Animal Health? | Filtro + ranking | unidad de negocio, país | 1 país, entero `> 0` |
| Q-10 | ¿Cuántas ventas netas generó el canal hospitalario en Oncology en 2023? | Filtro triple | canal, área terapéutica, tiempo | Un único número `> 0` |
| Q-11 | Media mensual de ventas netas por producto en LATAM. | Agregación con media | región, producto | 12 filas, todas `> 0` |
| Q-12 | ¿Cuánto vendimos en 2021? | **Fuera de rango** | tiempo | Cero filas — respuesta esperada "no hay datos", **no** un error |

## Notas

- Q-12 es intencionadamente insatisfacible: comprueba el caso límite de la spec según el cual
  una pregunta fuera del histórico devuelve "no hay datos" y nunca un error ni una cifra
  inventada.
- Q-03, Q-05, Q-07 y Q-09 dependen de que no haya empates. Es lo que garantizan los factores
  diferenciados de la fórmula de generación (invariante I-10).
- Q-05 pregunta explícitamente por el aumento **en euros** (no en porcentaje) para que no sea
  ambigua: la verified query desplegada en la feature 002 (`q05_therapeutic_area_highest_growth`)
  calcula la diferencia absoluta de `NET_SALES` entre 2025 y 2024, no una tasa de crecimiento.
- Q-06 depende de la rejilla temporal completa (invariante I-11).

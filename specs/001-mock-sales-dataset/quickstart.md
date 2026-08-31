# Quickstart: validar el dataset mock

**Feature**: `001-mock-sales-dataset` | **Fecha**: 2026-08-31 | **Fase**: 1

Cómo desplegar el dataset y comprobar que cumple su contrato. Es la guía que se usará en la
demo y la que replica el pipeline de CI.

## Prerrequisitos

1. `001_bootstrap.sql` ya ejecutado en la cuenta (rol, base de datos, schemas, grants).
2. Rol `CICD_DEMO_ROLE` concedido a tu usuario (`snowflake/manual/grant_user.sql`).
3. `.env` relleno a partir de `.env.example`:
   ```
   SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD,
   SNOWFLAKE_ROLE=CICD_DEMO_ROLE, SNOWFLAKE_WAREHOUSE=COMPUTE_WH,
   SNOWFLAKE_DATABASE=CICD_DEMO, SNOWFLAKE_SCHEMA=DATA
   ```
4. Conexión de Snowflake CLI registrada:
   ```powershell
   snow connection add --connection-name cicd_demo
   snow connection test --connection cicd_demo
   ```
5. Dependencias instaladas: `poetry install`.

## Desplegar

```powershell
snow sql --connection cicd_demo -f snowflake/002_tables.sql
snow sql --connection cicd_demo -f snowflake/003_seed.sql
```

Ambos scripts son idempotentes: ejecutarlos dos veces deja el mismo resultado.

## Validar

```powershell
poetry run pytest tests/test_dataset.py -v
```

Todos los tests deben pasar. Los que escriben en la base de datos (recarga para comprobar
idempotencia) están marcados y se excluyen así:

```powershell
poetry run pytest tests/test_dataset.py -v -m "not writes_db"
```

## Comprobación manual rápida

Tres consultas que confirman de un vistazo que el dataset está bien cargado.

```sql
-- 1. Volumen y rejilla temporal -> 12960 | 36 | 2023-01-01 | 2025-12-01
SELECT COUNT(*), COUNT(DISTINCT SALE_MONTH), MIN(SALE_MONTH), MAX(SALE_MONTH)
FROM CICD_DEMO.DATA.FACT_SALES;

-- 2. Ventas netas por region y anio -> 4 regiones x 3 anios, todas > 0
SELECT c.REGION, YEAR(f.SALE_MONTH) AS ANIO,
       SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS NET_SALES_EUR
FROM CICD_DEMO.DATA.FACT_SALES f
JOIN CICD_DEMO.DATA.DIM_COUNTRY c ON c.COUNTRY_CODE = f.COUNTRY_CODE
GROUP BY 1, 2
ORDER BY 1, 2;

-- 3. Top 5 marcas por ventas netas -> 5 filas sin empates
SELECT p.BRAND, SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS NET_SALES_EUR
FROM CICD_DEMO.DATA.FACT_SALES f
JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
GROUP BY 1
ORDER BY 2 DESC
LIMIT 5;
```

## Resultados esperados

| Comprobación | Resultado |
|---|---|
| Filas en `FACT_SALES` | 12.960 |
| Meses distintos | 36, de `2023-01-01` a `2025-12-01` |
| Filas en `DIM_PRODUCT` / `DIM_COUNTRY` | 12 / 10 |
| Nulos | Ninguno |
| Ventas netas negativas o cero | Ninguna |
| Segunda ejecución del seed | Recuentos y sumas idénticos |
| Suite `pytest` | Todos los tests en verde |

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| `Object does not exist` | Falta ejecutar `002_tables.sql`, o el rol/schema del `.env` no es el correcto |
| Recuento distinto de 12.960 | El seed se ejecutó a medias; volver a lanzar `003_seed.sql` completo |
| Los tests no conectan | `.env` incompleto, o `SNOWFLAKE_ROLE` distinto de `CICD_DEMO_ROLE` |
| Cifras distintas entre dos entornos | Bug de determinismo: hay aleatoriedad o dependencia de `CURRENT_DATE` en el SQL |

## Referencias

- Esquema y fórmula: [data-model.md](data-model.md)
- Garantías y tests: [contracts/dataset-contract.md](contracts/dataset-contract.md)
- Preguntas de referencia: [contracts/reference-questions.md](contracts/reference-questions.md)

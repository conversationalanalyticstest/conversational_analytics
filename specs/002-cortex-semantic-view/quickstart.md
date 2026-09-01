# Quickstart: desplegar y validar la Semantic View

**Feature**: `002-cortex-semantic-view` | **Fecha**: 2026-09-01 | **Fase**: 1

## Requisitos previos

- Rol `CICD_DEMO_ROLE` con `USAGE` sobre `CICD_DEMO.DATA` y las tablas `DIM_PRODUCT`,
  `DIM_COUNTRY`, `FACT_SALES` ya desplegadas (feature `001-mock-sales-dataset`).
- Conexión configurada como se documenta en [snowflake/README.md](../../../snowflake/README.md)
  (perfil `cicd_demo` de `snow` CLI, o `tests/conftest.py` para el conector Python).

## 1. Desplegar el DDL

Con `snow` CLI, desde la raíz del repo:

```powershell
snow sql -f snowflake/004_semantic_view.sql --connection cicd_demo
```

`CREATE OR ALTER SEMANTIC VIEW` es idempotente: volver a ejecutar el mismo fichero no falla y
no cambia nada si la definición no ha cambiado.

## 2. Verificar que el objeto existe

```sql
SHOW SEMANTIC VIEWS IN SCHEMA CICD_DEMO.DATA;
DESCRIBE SEMANTIC VIEW CICD_DEMO.DATA.SV_VENTAS_FARMA;
```

`DESCRIBE` debe listar las 3 tablas lógicas, las 2 relaciones, los 4 facts, las 9 dimensiones y
las 6 métricas definidas en [data-model.md](../data-model.md).

## 3. Consulta manual de validación (equivalente a Q-01)

```sql
SELECT *
FROM SEMANTIC_VIEW(
  CICD_DEMO.DATA.SV_VENTAS_FARMA
  DIMENSIONS VENTA.ANIO
  METRICS VENTA.VENTAS_NETAS
)
WHERE ANIO = 2025;
```

Debe devolver una fila con `VENTAS_NETAS > 0`, coherente con la aserción de Q-01 en
[reference-questions.md](../../001-mock-sales-dataset/contracts/reference-questions.md).

## 4. Validación automática (tests)

```powershell
py -m pytest tests/test_semantic_view.py -v
```

Este test (creado en la fase de implementación) recorre el mapeo de
[contracts/verified-queries-mapping.md](contracts/verified-queries-mapping.md) y comprueba,
para cada pregunta Q-01..Q-11, la misma aserción que ya valida
`tests/test_reference_questions.py` sobre las tablas base.

## 5. Rollback

Si algo falla, revertir es tan simple como no promocionar el commit: la semantic view es un
objeto adicional que no modifica ni bloquea las tablas base. Para eliminarla manualmente en un
entorno de pruebas:

```sql
DROP SEMANTIC VIEW IF EXISTS CICD_DEMO.DATA.SV_VENTAS_FARMA;
```

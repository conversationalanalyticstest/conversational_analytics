# Quickstart: Aislar el check de PR contra una copia de la semantic view

**Feature**: [005-pr-checks-semantic-isolation](./spec.md) · **Plan**: [plan.md](./plan.md)

Guion de validación end-to-end. Requiere el mismo `.env`/secretos de GitHub que la feature
004-ci-cd-pipeline (ver [quickstart de 004](../004-ci-cd-pipeline/quickstart.md)) — no se añade
ningún secreto nuevo.

## Prerrequisitos

- Rama `main` con `pr-checks.yml` ya actualizado según
  [contracts/pr-candidate-workflow.md](contracts/pr-candidate-workflow.md).
- `CICD_DEMO_ROLE` con permisos de propietario sobre `CICD_DEMO.DATA` (ya verificado en la
  feature 004, tasks.md T051) — sin permisos nuevos que conceder.
- Tests locales en verde: `poetry run pytest tests/test_ops_pr_candidate.py`.

## Escenario 1 — Un cambio roto en la semantic view bloquea el check, sin tocar producción

1. Abrir una PR que introduzca un error deliberado en `snowflake/004_semantic_view.sql` (p. ej.
   una métrica que referencia una columna inexistente).
2. Observar el check `pr-checks`: falla, y el mensaje de error hace referencia al objeto
   `SV_PHARMA_SALES_PR<número-de-esta-PR>`.
3. En Snowflake, ejecutar `SHOW SEMANTIC VIEWS IN SCHEMA CICD_DEMO.DATA;` — `SV_PHARMA_SALES`
   (producción) sigue con su definición anterior, sin cambios.
4. Corregir el error y hacer push: el check pasa.

## Escenario 2 — La candidata no sobrevive a una ejecución completada

1. Con la PR del Escenario 1 ya corregida y el check en verde, ejecutar
   `SHOW SEMANTIC VIEWS IN SCHEMA CICD_DEMO.DATA;` en Snowflake.
2. Confirmar que `SV_PHARMA_SALES_PR<número>` **no** existe (el paso "Drop candidate semantic
   view" ya se ejecutó, `if: always()`).

## Escenario 3 — Dos PRs concurrentes no interfieren

1. Abrir dos PRs distintas (números de PR distintos), cada una con una definición distinta de
   `snowflake/004_semantic_view.sql`.
2. Disparar ambos checks a la vez (push en ambas casi simultáneo).
3. Confirmar que cada check usa su propio objeto (`SV_PHARMA_SALES_PR<n1>` /
   `SV_PHARMA_SALES_PR<n2>`) y que el resultado de cada uno corresponde a su propio contenido,
   independientemente del orden en que terminen.

## Escenario 4 — Cerrar una PR limpia su candidata aunque el último run se cancelara

1. En una PR con el check en curso, hacer push de un nuevo commit antes de que termine (dispara
   `cancel-in-progress: true`, cancelando la ejecución anterior a mitad de camino).
2. Cerrar la PR (sin esperar a que termine el nuevo check, o después — cualquiera de los dos
   casos).
3. Confirmar en `SHOW SEMANTIC VIEWS IN SCHEMA CICD_DEMO.DATA;` que
   `SV_PHARMA_SALES_PR<número>` no existe tras el cierre (el job disparado por el evento
   `closed` ejecuta el paso de limpieza incondicionalmente).

## Verificación de no regresión

- `DEPLOYMENTS` no tiene ninguna fila nueva causada por estos escenarios (consultar
  `SELECT * FROM DEPLOYMENTS ORDER BY DEPLOYED_AT DESC LIMIT 5;` antes y después).
- El resto de contratos de `pr-checks.yml` (permisos `contents: read`, secretos, concurrency por
  número de PR) no cambian — ver
  [../004-ci-cd-pipeline/contracts/workflows.md](../004-ci-cd-pipeline/contracts/workflows.md).

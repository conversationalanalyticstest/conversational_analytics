# ADR-001 (005): Aislar la validación de PR con una semantic view candidata efímera

**Fecha**: 2026-09-04
**Feature**: [005-pr-checks-semantic-isolation](../spec.md)
**Estado**: Aceptada
**Supersede a**: [ADR-003](../../004-ci-cd-pipeline/decisions/003-simplificacion-semantic-view.md)
(feature 004-ci-cd-pipeline) — **únicamente su punto 4** ("se elimina el mecanismo de semantic
view candidata en `pr-checks.yml`"). El resto de ADR-003 (objeto único de producción, sin
versionado con puntero, rollback/revert vía `git show`) **sigue vigente**.
**Afecta a**: FR-001 a FR-009 de esta feature; contrato `pr-checks.yml` de la feature 004.

## Contexto

ADR-003 decidió, conscientemente, que `pr-checks.yml` validara contra la semantic view activa de
producción, sin aislamiento: un cambio en `snowflake/004_semantic_view.sql` solo se descubría
roto tras el merge, cuando la evaluación post-deploy y el rollback automático de `deploy.yml` ya
tenían que intervenir. Fue un trade-off explícito a favor de la simplicidad (Principio I): evitar
un mecanismo de versionado con puntero (`SEMANTIC_VIEW_VERSIONS`/`SEMANTIC_VIEW_ACTIVE`) que
duplicaba a Git como fuente de verdad y que, además, tenía un bug real (el revert leía el working
tree actual, no el commit objetivo).

De hecho, durante la implementación inicial de la feature 004 existió una semantic view
candidata en PR (`ops/semantic_view_registry.py`, modo `--candidate` de `deploy.py`, tasks
T014/T015) — se eliminó en la misma pasada que el versionado persistente, no porque la idea de
"candidata en PR" en sí misma fuera el problema, sino porque estaba acoplada al mecanismo de
registro que sí lo era.

El equipo revisa ahora ese trade-off: prefiere pagar la complejidad de una copia efímera por PR a
cambio de detectar un cambio roto en la semantic view **antes** de fusionar, no solo después.

## Decisión

Se reintroduce una semantic view candidata en `pr-checks.yml`, pero sin el registro persistente
que la acompañaba:

1. Cada ejecución del check construye `CICD_DEMO.DATA.SV_PHARMA_SALES_PR<número-de-PR>` a partir
   del contenido de `snowflake/004_semantic_view.sql` en el working tree de la propia PR
   (sustitución de nombre en memoria, no templating permanente del fichero — ver
   [research.md](../research.md), D-01).
2. Los tests corren contra esa candidata vía `SNOWFLAKE_SEMANTIC_VIEW` (override que
   `cortex_analyst.py` ya soporta desde la feature 004, sin cambios de código).
3. La candidata se elimina al final de cada ejecución (`if: always()`) y de nuevo cuando la PR se
   cierra (nuevo tipo de disparador `closed`), como red de seguridad ante ejecuciones canceladas
   (D-03).
4. **No hay tabla de registro.** El nombre es 100% derivable del número de PR; no hace falta
   persistir qué candidata pertenece a qué PR.
5. `DEPLOYMENTS` no recibe ninguna fila por esto (D-05): no es un despliegue de producción.

## Consecuencias

**Positivas**

- Un cambio roto en la semantic view se detecta en el check de la propia PR, no solo tras el
  merge — reduce el ciclo "fusionar → post-deploy falla → rollback automático" al caso menos
  común (regresión que solo aparece con datos/carga reales de producción).
- Sin tabla de registro: no se repite el problema de fondo que motivó ADR-003
  ("acumulación de estado sin beneficio claro").
- Reutiliza infraestructura ya existente (`sql_runner.run_sql_string`, el override de
  `SNOWFLAKE_SEMANTIC_VIEW`): el módulo nuevo (`ops/pr_candidate.py`) es pequeño y sigue el mismo
  patrón que `ops/deploy.py`.

**Negativas / aceptadas conscientemente**

- `pr-checks.yml` gana 2 pasos y un tipo de disparador adicional (`closed`): más superficie que
  el diseño actual de ADR-003, aunque menos que el mecanismo original (sin tablas, sin
  versionado con puntero).
- Riesgo residual acotado: si una PR se cancela a mitad de ejecución y nunca vuelve a recibir un
  push ni se cierra, su candidata queda viva hasta que eso ocurra. Se acepta porque está acotado
  (como máximo, un objeto por PR abierta) y es exactamente el mismo tipo de limitación que
  cualquier recurso de CI ligado al ciclo de vida de una PR.

## Notas relacionadas

- El resto de ADR-003 (semantic view de producción como objeto físico único, sin versionado con
  puntero; rollback/revert vía `git show`) **sigue vigente**: esta feature no lo toca.
- Ver [research.md](../research.md) para el detalle de cada decisión de diseño (D-01 a D-06).

# Quickstart — validar el pipeline de CI/CD

**Feature**: [004-ci-cd-pipeline](./spec.md)

Guion de validación manual, de extremo a extremo. Asume que la implementación de `tasks.md` ya
está desplegada (workflows en `.github/workflows/`, tabla `006_deployments.sql` ya ejecutada).

## Prerrequisitos

1. Secretos configurados en GitHub:
   - **Repositorio** (usados por `pr-checks.yml`): `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`,
     `SNOWFLAKE_PAT`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`,
     `LLM_PROVIDER`, `OPENAI_API_KEY` (u otras variables de proveedor según `.env.example`).
   - **Environment `production`** (usados por `deploy.yml` y `revert.yml`): los mismos nombres,
     duplicados en el Environment con protección de revisión habilitada.
2. Protección de rama en `main`: PR obligatoria, check `pr-checks` requerido, 1 aprobación
   mínima, sin push directo.
3. `006_deployments.sql` ya ejecutado (una vez, como `001_bootstrap.sql` y los siguientes).

## Escenario 1 — Una PR con un test roto no se puede mergear (User Story 1)

```powershell
git checkout -b demo/test-roto
# Rompe a proposito un assert en tests/test_agent_evaluation.py
git commit -am "demo: test roto a proposito"
git push origin demo/test-roto
```

Abrir la PR contra `main`. **Esperado**: el check `pr-checks` se pone en rojo; el botón de merge
queda deshabilitado. Corregir el test y volver a subir: el check pasa a verde y el merge se
habilita.

## Escenario 2 — Merge a main despliega e identifica la release (User Story 2)

Mergear una PR válida. **Esperado**, tras el run de `deploy.yml`:

```sql
SELECT * FROM CICD_DEMO.DEVOPS.DEPLOYMENTS ORDER BY DEPLOYED_AT DESC LIMIT 1;
-- ACTION = 'DEPLOY', TARGET_COMMIT_SHA = <sha del merge>, STATUS = 'SUCCESS'
```

```powershell
git fetch --tags
git rev-parse deployed-good   # coincide con el sha del merge
```

## Escenario 3 — Un despliegue que falla el post-deploy se revierte solo (User Story 3)

Forma más simple de forzar el escenario en la demo: mergear un cambio que se sabe que rompe una
aserción de `test_agent_evaluation.py` pero que pasa igualmente el job de tests inicial (p. ej.
un cambio en la semantic view que solo se manifiesta contra el entorno real ya desplegado).
**Esperado**:

```sql
SELECT ACTION, STATUS, REASON FROM CICD_DEMO.DEVOPS.DEPLOYMENTS ORDER BY DEPLOYED_AT DESC LIMIT 2;
-- fila 1: ACTION = 'AUTO_ROLLBACK', STATUS = 'SUCCESS'
-- fila 2: ACTION = 'DEPLOY', STATUS = 'FAILED' (o la evidencia equivalente segun se implemente)
```

`deployed-good` vuelve a apuntar al commit anterior. Se abre un GitHub Issue con la etiqueta
`drift` indicando que `main` está por delante de lo desplegado.

**Cronometrar (SC-003, SC-008)**: apunta la hora a la que `deploy.yml` detecta el fallo de la
evaluación post-deploy (inicio del job de rollback) y la hora en la que el rollback queda
`SUCCESS` en `DEPLOYMENTS`; la diferencia MUST ser menor de 10 minutos. Por separado, cronometra
cuánto tardas en determinar, mirando solo el Issue `drift` (sin revisar logs del pipeline), qué
commits de `main` no están desplegados; MUST ser menor de 1 minuto.

## Escenario 4 — Resolver el drift con un fix forward

Corregir el problema en un commit nuevo y mergearlo normalmente (Escenario 2). **Esperado**: el
Issue `drift` se cierra automáticamente al final de ese `deploy.yml`.

## Escenario 5 — Revert manual a una release anterior (User Story 4)

En GitHub → Actions → `revert.yml` → *Run workflow*, con `target_commit_sha` = un SHA de una
release exitosa anterior (consultarlo con la query de
[deployments-table.md](contracts/deployments-table.md)). **Esperado**: nueva fila en
`DEPLOYMENTS` con `ACTION = 'MANUAL_REVERT'` y `TRIGGERED_BY` = tu usuario de GitHub; la semantic
view queda con la definición que tenía ese commit (recuperada vía `git show`, ver
[ADR-003](decisions/003-simplificacion-semantic-view.md)).

Repetir con un SHA inventado (`target_commit_sha = 0000000`): el workflow **falla en el primer
paso**, sin tocar Snowflake (FR-014).

**Cronometrar (SC-004)**: desde que pulsas *Run workflow* hasta que `DEPLOYMENTS` registra la fila
`MANUAL_REVERT` con `STATUS = 'SUCCESS'` MUST pasar menos de 5 minutos, y MUST ser una única
acción (rellenar el input y confirmar), sin pasos manuales adicionales en Snowflake.

## Validación con tests automáticos

```powershell
poetry run pytest tests/test_ops_deploy.py tests/test_ops_drift.py `
  tests/test_cortex_analyst_resolves_active_view.py -v
```

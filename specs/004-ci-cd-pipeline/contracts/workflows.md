# Contrato: Workflows de GitHub Actions

**Feature**: [004-ci-cd-pipeline](../spec.md) · **Plan**: [../plan.md](../plan.md)

Describe disparador, permisos, secretos, pasos y salida observable de cada workflow. La
implementación exacta del YAML se hace en `speckit-tasks` / `speckit-implement`; este documento
fija el contrato que esa implementación MUST cumplir.

---

## `pr-checks.yml`

> ⚠️ **Actualizado por la feature
> [005-pr-checks-semantic-isolation](../../005-pr-checks-semantic-isolation/spec.md)**: el check
> ya no corre contra la semantic view de producción, sino contra una copia efímera y aislada
> ("candidata"). El contrato vigente es
> [pr-candidate-workflow.md](../../005-pr-checks-semantic-isolation/contracts/pr-candidate-workflow.md)
> de esa feature; lo que sigue queda como registro histórico del diseño original (ADR-003).

**Disparador**: `pull_request` (`opened`, `synchronize`, `reopened`) contra `main`.

**Permisos**: `contents: read` únicamente. No escribe en el repositorio ni despliega nada en
Snowflake (ver [semantic-view-versioning.md](semantic-view-versioning.md), sección "PR checks:
sin despliegue de candidato", ADR-003).

**Secretos**: los mismos nombres que `.env.example` (`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`,
`SNOWFLAKE_PAT`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`,
`LLM_PROVIDER`, `OPENAI_API_KEY` según corresponda), como **secretos de repositorio** (no del
Environment `production`).

**Concurrency**: `group: pr-checks-${{ github.event.pull_request.number }}`,
`cancel-in-progress: true` (un nuevo push a la misma PR cancela la ejecución anterior, no hace
falta esperarla).

**Pasos (contrato, no implementación)**:

1. `actions/checkout` de la PR.
2. `actions/setup-python` + `poetry install`.
3. Ejecutar la suite completa: `poetry run pytest`, sin desplegar nada — corre contra la
   semantic view activa en producción (ver ADR-003).
4. El resultado del paso 3 determina el estado del check `pr-checks` que GitHub usa como
   *required status check* de la protección de rama (FR-002, FR-003).

**Salida observable**: check `pr-checks` en verde/rojo sobre la PR; ningún cambio en Snowflake
ni en `DEPLOYMENTS`.

---

## `deploy.yml`

**Disparador**: `push` a `main` (es decir, cada merge).

**Permisos**: `contents: write` (mover el tag `deployed-good`), `issues: write` (gestionar el
Issue de drift).

**Secretos**: los mismos nombres, pero leídos del **Environment** `production` (protegido).

**Concurrency**: `group: deploy-production`, `cancel-in-progress: false` — dos merges casi
simultáneos se serializan, nunca se solapan (FR-015).

**Pasos (contrato)**:

1. `actions/checkout` de `main` en `${{ github.sha }}`.
2. Comprobar si existe un Issue abierto con etiqueta `drift`; si existe, anotar advertencia en el
   resumen del run (FR-022) — no bloquea.
3. `poetry install`.
4. Ejecutar la suite completa: `poetry run pytest` contra el entorno vigente (sin desplegar
   todavía). Si falla → FR-006: no se despliega nada, se notifica (comentario en el commit /
   resumen del run) y el job termina en rojo. No se inserta fila en `DEPLOYMENTS` (no hubo
   intento de despliegue).
5. Si pasa → `poetry run python -m conversational_analytics.ops.deploy` (release completa:
   aplica los scripts SQL idempotentes de `snowflake/` tal como están en `github.sha` —
   incluida `004_semantic_view.sql`, sobre el único objeto `SV_PHARMA_SALES` — e inserta
   `DEPLOYMENTS` con `ACTION=DEPLOY`).
6. Evaluación post-deploy: `poetry run pytest tests/test_agent_evaluation.py` contra el entorno
   ya desplegado (FR-009).
7. Si el paso 6 pasa: mover el tag `deployed-good` a `github.sha`; marcar la fila del paso 5 como
   confirmada (o insertar una segunda fila de confirmación, según se resuelva en tasks).
8. Si el paso 6 falla: `poetry run python -m conversational_analytics.ops.rollback` (lee
   `deployed-good`, re-despliega esa release, inserta `DEPLOYMENTS` con
   `ACTION=AUTO_ROLLBACK`). Si el propio rollback falla, el job termina en rojo sin reintentar
   (FR-011) y el Issue de drift se marca como incidente.
9. `if: always()` — recalcular drift (`deployed-good` vs `github.sha`) y crear/actualizar/cerrar
   el Issue con etiqueta `drift` (FR-021).

**Salida observable**: el tag `deployed-good` refleja la release realmente desplegada;
`DEPLOYMENTS` tiene una fila nueva; el Issue `drift` existe solo si `main` y lo desplegado
divergen.

---

## `revert.yml`

**Disparador**: `workflow_dispatch`, con un único input obligatorio `target_commit_sha`
(string).

**Permisos**: `contents: write`, `issues: write`. Mismo Environment `production` que
`deploy.yml`.

**Concurrency**: mismo grupo `deploy-production` que `deploy.yml` (un revert y un deploy nunca
se solapan).

**Pasos (contrato)**:

1. Validar `target_commit_sha`: `poetry run python -m conversational_analytics.ops.revert
   --target <sha>` consulta `DEPLOYMENTS WHERE TARGET_COMMIT_SHA = <sha> AND STATUS = 'SUCCESS'`;
   si no hay fila, el job falla inmediatamente con mensaje claro (FR-014), sin tocar Snowflake.
2. Si es válido: `actions/checkout` de ese commit.
3. Re-desplegar esa release (agente + semantic view) reutilizando la misma lógica de
   `ops/deploy.py` que usa `deploy.yml`: cada script SQL, incluida `004_semantic_view.sql`, se
   lee con `git show <target_commit_sha>:snowflake/<script>.sql` (no del working tree) y se
   aplica sobre el único objeto `SV_PHARMA_SALES` (ver ADR-003).
4. Insertar fila en `DEPLOYMENTS` con `ACTION=MANUAL_REVERT`, `TRIGGERED_BY` = actor de GitHub
   que disparó el workflow (`github.actor`), `WORKFLOW_RUN_URL` (FR-013).
5. `if: always()` — recalcular y actualizar el Issue de drift, igual que en `deploy.yml`.

**Salida observable**: igual que `deploy.yml` tras un rollback, más una fila en `DEPLOYMENTS` con
`TRIGGERED_BY` humano en vez de `github-actions[bot]`.

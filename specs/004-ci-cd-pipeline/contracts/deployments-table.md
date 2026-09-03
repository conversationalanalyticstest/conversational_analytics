# Contrato: tabla `DEPLOYMENTS`

**Feature**: [004-ci-cd-pipeline](../spec.md) · **Data model**: [../data-model.md](../data-model.md)

## DDL

```sql
USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DEVOPS;

CREATE TABLE IF NOT EXISTS DEPLOYMENTS (
    DEPLOYMENT_ID       STRING NOT NULL,
    ACTION              STRING NOT NULL,   -- DEPLOY | AUTO_ROLLBACK | MANUAL_REVERT
    TARGET_COMMIT_SHA   STRING NOT NULL,
    PREVIOUS_COMMIT_SHA STRING,
    STATUS              STRING NOT NULL,   -- SUCCESS | FAILED
    REASON              STRING,
    TRIGGERED_BY        STRING NOT NULL,
    WORKFLOW_RUN_URL    STRING NOT NULL,
    DEPLOYED_AT         TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
```

**`CREATE TABLE IF NOT EXISTS`**, no `CREATE OR REPLACE`: es un histórico insert-only, igual que
`AGENT_TELEMETRY` (feature 003). Nunca se hace `UPDATE` ni `DELETE` sobre esta tabla.

## Quién escribe

- `ops/deployments_log.py` — única puerta de entrada para insertar filas; ningún otro módulo
  hace `INSERT INTO DEPLOYMENTS` directamente (misma disciplina que `Telemetry.record` en
  `telemetry.py`).

## Consultas de referencia

**¿Qué está desplegado ahora mismo?**

```sql
SELECT TARGET_COMMIT_SHA, ACTION, DEPLOYED_AT
FROM DEPLOYMENTS
WHERE STATUS = 'SUCCESS'
ORDER BY DEPLOYED_AT DESC
LIMIT 1;
```

**Historial completo de una release concreta:**

```sql
SELECT *
FROM DEPLOYMENTS
WHERE TARGET_COMMIT_SHA = :sha OR PREVIOUS_COMMIT_SHA = :sha
ORDER BY DEPLOYED_AT;
```

**Validación de un revert manual (FR-014):**

```sql
SELECT COUNT(*) AS existe
FROM DEPLOYMENTS
WHERE TARGET_COMMIT_SHA = :target_sha AND STATUS = 'SUCCESS';
-- 0 filas -> rechazar el revert antes de tocar Snowflake
```

**Todos los rollbacks/reverts (para entender incidentes pasados):**

```sql
SELECT ACTION, TARGET_COMMIT_SHA, PREVIOUS_COMMIT_SHA, REASON, TRIGGERED_BY, DEPLOYED_AT
FROM DEPLOYMENTS
WHERE ACTION IN ('AUTO_ROLLBACK', 'MANUAL_REVERT')
ORDER BY DEPLOYED_AT DESC;
```

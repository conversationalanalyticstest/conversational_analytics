-- =========================================================
-- 006_deployments.sql
-- Registro insert-only de despliegues/rollbacks/reverts (feature 004-ci-cd-pipeline).
--
-- CREATE TABLE IF NOT EXISTS: es un historico, igual que AGENT_TELEMETRY. Nunca se hace
-- UPDATE ni DELETE sobre esta tabla.
--
-- Cubre el Principio III de la constitucion (CI/CD Es el Producto) y FR-008, FR-010, FR-011,
-- FR-013, FR-014.
--
-- Contrato origen (no editar aqui sin actualizar alli tambien):
--   specs/004-ci-cd-pipeline/contracts/deployments-table.md
--
-- Requiere haber ejecutado antes 001_bootstrap.sql (GRANT CREATE TABLE sobre el schema
-- DEVOPS, seccion 6).
-- =========================================================

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

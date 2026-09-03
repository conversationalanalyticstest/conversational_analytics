-- =========================================================
-- 007_semantic_view_registry.sql
-- Versionado de semantic views: historico de versiones desplegadas y puntero a la version
-- activa (feature 004-ci-cd-pipeline).
--
-- CREATE TABLE IF NOT EXISTS en ambas: SEMANTIC_VIEW_VERSIONS es un historico insert-only
-- (igual que DEPLOYMENTS); SEMANTIC_VIEW_ACTIVE es un puntero mutable (una fila por
-- BASE_NAME), pero tambien se crea con IF NOT EXISTS -- las actualizaciones posteriores se
-- hacen con MERGE/UPDATE desde ops/semantic_view_registry.py, no recreando la tabla.
--
-- Cubre FR-016 a FR-020 y la decision D-06 (ADR-001) de
-- specs/004-ci-cd-pipeline/decisions/001-estrategia-de-revert.md.
--
-- Contrato origen (no editar aqui sin actualizar alli tambien):
--   specs/004-ci-cd-pipeline/contracts/semantic-view-versioning.md
--
-- Requiere haber ejecutado antes 001_bootstrap.sql (GRANT CREATE TABLE sobre el schema
-- DEVOPS, seccion 6).
-- =========================================================

USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DEVOPS;

CREATE TABLE IF NOT EXISTS SEMANTIC_VIEW_VERSIONS (
    VERSION_ID   NUMBER AUTOINCREMENT,
    BASE_NAME    STRING NOT NULL,
    OBJECT_NAME  STRING NOT NULL,
    COMMIT_SHA   STRING NOT NULL,
    DDL_TEXT     STRING NOT NULL,
    IS_CANDIDATE BOOLEAN NOT NULL DEFAULT FALSE,
    DEPLOYED_AT  TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- Puntero mutable: una fila por semantic view base. A diferencia de la tabla anterior, esta SI
-- se actualiza in place (MERGE/UPDATE), porque representa el estado actual, no un historico.
CREATE TABLE IF NOT EXISTS SEMANTIC_VIEW_ACTIVE (
    BASE_NAME          STRING NOT NULL,
    ACTIVE_OBJECT_NAME STRING NOT NULL,
    ACTIVE_COMMIT_SHA  STRING NOT NULL,
    UPDATED_AT         TIMESTAMP_NTZ NOT NULL,
    UPDATED_BY         STRING NOT NULL,
    PRIMARY KEY (BASE_NAME)
);

-- =========================================================
-- 005_telemetry.sql
-- Tabla y vista de telemetria del agente conversacional (feature 003-conversational-agent).
--
-- Idempotente para la vista (CREATE OR REPLACE). La tabla usa CREATE TABLE IF NOT EXISTS:
-- el historico de invocaciones no se puede perder en cada despliegue (a diferencia de la
-- semantic view, esta tabla tiene datos que proteger).
--
-- Cubre el Principio IV de la constitucion (Observabilidad y Control de Coste) y FR-007.
--
-- Contrato origen (no editar aqui sin actualizar alli tambien):
--   specs/003-conversational-agent/contracts/telemetry-table.md
--
-- Requiere haber ejecutado antes 001_bootstrap.sql (GRANT CREATE TABLE, CREATE VIEW sobre
-- el schema DEVOPS, seccion 6).
-- =========================================================

USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DEVOPS;

CREATE TABLE IF NOT EXISTS AGENT_TELEMETRY (
    EVENT_ID             STRING        NOT NULL,
    EVENT_TS             TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    SOURCE               STRING        NOT NULL,
    ACTOR                STRING        NOT NULL,
    QUESTION             STRING        NOT NULL,
    ANSWER               STRING,
    GENERATED_SQL        STRING,
    VERIFIED_QUERY_NAME  STRING,
    ANALYST_REQUEST_ID   STRING,
    SF_QUERY_ID          STRING,
    ROW_COUNT            NUMBER,
    PROVIDER             STRING        NOT NULL,
    MODEL                STRING        NOT NULL,
    PROMPT_TOKENS        NUMBER        NOT NULL,
    COMPLETION_TOKENS    NUMBER        NOT NULL,
    ESTIMATED_COST       FLOAT,
    COST_UNIT            STRING        NOT NULL,
    LATENCY_MS           NUMBER        NOT NULL,
    STATUS               STRING        NOT NULL,
    ERROR_MESSAGE        STRING,
    COMMIT_SHA           STRING,
    FEEDBACK             NUMBER
)
COMMENT = 'Un evento por invocacion del agente conversacional. Principio IV de la constitucion.';

CREATE OR REPLACE VIEW V_AGENT_ACTIVITY
COMMENT = 'Que se ha preguntado, cuanto ha costado y si la respuesta fue correcta.'
AS
SELECT
    EVENT_TS,
    SOURCE,
    ACTOR,
    QUESTION,
    ANSWER,
    STATUS,
    VERIFIED_QUERY_NAME IS NOT NULL  AS USED_VERIFIED_QUERY,
    FEEDBACK,
    PROMPT_TOKENS,
    COMPLETION_TOKENS,
    PROMPT_TOKENS + COMPLETION_TOKENS AS TOTAL_TOKENS,
    ESTIMATED_COST,
    COST_UNIT,
    LATENCY_MS,
    PROVIDER,
    MODEL,
    COMMIT_SHA,
    GENERATED_SQL,
    SF_QUERY_ID
FROM AGENT_TELEMETRY;

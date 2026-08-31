-- =========================================================
-- 001_bootstrap.sql
-- Infraestructura base de la demo: rol, base de datos, schemas y permisos.
--
-- Idempotente: se puede ejecutar tantas veces como haga falta.
-- NO contiene nada especifico de un usuario o cuenta concreta.
-- Los grants a un usuario nominal van en snowflake/manual/grant_user.sql.
--
-- Requiere ACCOUNTADMIN.
-- =========================================================

USE ROLE ACCOUNTADMIN;


-- ---------------------------------------------------------
-- 1. Rol dedicado del proyecto
-- ---------------------------------------------------------

CREATE ROLE IF NOT EXISTS CICD_DEMO_ROLE;


-- ---------------------------------------------------------
-- 2. Acceso a Cortex
-- ---------------------------------------------------------

GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER
TO ROLE CICD_DEMO_ROLE;


-- ---------------------------------------------------------
-- 3. Base de datos y schemas
--    DATA   -> tablas de negocio
--    AI     -> semantic views y objetos del agente
--    DEVOPS -> telemetria, control de despliegues
-- ---------------------------------------------------------

CREATE DATABASE IF NOT EXISTS CICD_DEMO;

CREATE SCHEMA IF NOT EXISTS CICD_DEMO.DATA;
CREATE SCHEMA IF NOT EXISTS CICD_DEMO.AI;
CREATE SCHEMA IF NOT EXISTS CICD_DEMO.DEVOPS;


-- ---------------------------------------------------------
-- 4. Warehouse
-- ---------------------------------------------------------

GRANT USAGE ON WAREHOUSE COMPUTE_WH
TO ROLE CICD_DEMO_ROLE;


-- ---------------------------------------------------------
-- 5. Permisos de lectura de contenedores
-- ---------------------------------------------------------

GRANT USAGE ON DATABASE CICD_DEMO
TO ROLE CICD_DEMO_ROLE;

GRANT USAGE ON SCHEMA CICD_DEMO.DATA
TO ROLE CICD_DEMO_ROLE;

GRANT USAGE ON SCHEMA CICD_DEMO.AI
TO ROLE CICD_DEMO_ROLE;

GRANT USAGE ON SCHEMA CICD_DEMO.DEVOPS
TO ROLE CICD_DEMO_ROLE;


-- ---------------------------------------------------------
-- 6. Creacion de objetos
-- ---------------------------------------------------------

GRANT CREATE TABLE, CREATE VIEW
ON SCHEMA CICD_DEMO.DATA
TO ROLE CICD_DEMO_ROLE;

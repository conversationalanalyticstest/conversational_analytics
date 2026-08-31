-- =========================================================
-- manual/grant_user.sql
-- Paso MANUAL, especifico de cada entorno/persona.
--
-- Asigna CICD_DEMO_ROLE a un usuario concreto y fija su contexto por defecto.
-- NO lo ejecuta el pipeline: depende de a quien se le quiera dar acceso.
--
-- Uso: edita el valor de DEMO_USER y ejecuta el script entero como ACCOUNTADMIN.
-- =========================================================

USE ROLE ACCOUNTADMIN;

-- <<< CAMBIA ESTO por el usuario de Snowflake que va a usar la demo >>>
SET DEMO_USER = 'MI_USUARIO_SNOWFLAKE';

SET DEMO_ROLE = 'CICD_DEMO_ROLE';
SET DEMO_WAREHOUSE = 'COMPUTE_WH';


GRANT ROLE IDENTIFIER($DEMO_ROLE)
TO USER IDENTIFIER($DEMO_USER);

ALTER USER IDENTIFIER($DEMO_USER)
SET DEFAULT_ROLE = $DEMO_ROLE
    DEFAULT_WAREHOUSE = $DEMO_WAREHOUSE;

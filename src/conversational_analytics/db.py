"""Acceso a Snowflake.

Unico punto del proyecto donde se abre una conexion. Las credenciales salen siempre de
variables de entorno (Principio V de la constitucion): en local desde `.env`, en CI desde
GitHub Secrets. El codigo es el mismo en ambos casos.
"""

from __future__ import annotations

import os
from typing import Any

import snowflake.connector
from dotenv import load_dotenv

#: Variables de entorno requeridas. Estan documentadas en `.env.example`.
REQUIRED_ENV_VARS = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
)


def get_connection() -> snowflake.connector.SnowflakeConnection:
    """Abre una conexion a Snowflake con las credenciales del entorno.

    Carga `.env` si existe (en CI no existe y no pasa nada: las variables ya vienen del
    entorno). Falla de forma explicita indicando que variables faltan, en lugar de dejar que
    el conector devuelva un error opaco.

    Raises:
        RuntimeError: si falta alguna de las variables de `REQUIRED_ENV_VARS`.
    """
    load_dotenv()

    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Faltan variables de entorno de Snowflake: "
            + ", ".join(missing)
            + ". Copia .env.example a .env y rellenalo."
        )

    params: dict[str, Any] = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "password": os.environ["SNOWFLAKE_PASSWORD"],
        "role": os.environ["SNOWFLAKE_ROLE"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database": os.environ["SNOWFLAKE_DATABASE"],
        "schema": os.environ["SNOWFLAKE_SCHEMA"],
    }
    return snowflake.connector.connect(**params)

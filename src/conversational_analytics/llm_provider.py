"""Construccion del cliente del orquestador, segun el proveedor configurado.

Unico punto del codigo que decide el proveedor del orquestador (D-11 en
specs/003-conversational-agent/research.md). `agent.py` solo consume la tupla que devuelve
`build_llm_client()`; nunca instancia `OpenAI(...)` directamente. Cambiar de la API publica de
OpenAI a Cortex (o anadir un tercer proveedor el dia de manana) es un cambio local a este
fichero, via `LLM_PROVIDER`.

Dentro de `LLM_PROVIDER=openai` se admiten dos backends, sin que eso cambie el valor de
`provider` que se reporta en telemetria (sigue siendo `"openai"`, familia de modelos y tarifa):
- API publica de OpenAI (por defecto): solo hace falta `OPENAI_API_KEY`.
- Azure OpenAI Service (si `AZURE_OPENAI_ENDPOINT` esta presente): mismo SDK `openai`, cliente
  `AzureOpenAI` en vez de `OpenAI`, con `api_version` y nombre de *deployment* en lugar de
  nombre de modelo.

Cortex Analyst (`cortex_analyst.py`) no pasa por aqui: se autentica siempre con
`SNOWFLAKE_PAT`, sea cual sea `LLM_PROVIDER` (D-03).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

#: Modelo por defecto cuando LLM_PROVIDER=openai vía API pública (verificado con `tools` el
#: 2026-09-02, D-05). No aplica cuando se usa Azure: ahi el nombre efectivo es el del
#: *deployment* (`AZURE_OPENAI_DEPLOYMENT`), no este valor.
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"

#: Version de API por defecto para Azure OpenAI Service, si `AZURE_OPENAI_API_VERSION` no se fija.
DEFAULT_AZURE_API_VERSION = "2024-12-01-preview"

#: Modelo por defecto cuando LLM_PROVIDER=cortex. Sin verificar en esta cuenta: es trial y no
#: tiene ninguna entitlement de inferencia Cortex habilitada (D-11). Se deja como referencia
#: para cuando una cuenta de pago lo permita; `CORTEX_MODEL` lo sobreescribe.
DEFAULT_CORTEX_MODEL = "openai-gpt-4.1"


def build_llm_client() -> tuple[OpenAI | AzureOpenAI, str, str]:
    """Construye el cliente del orquestador segun `LLM_PROVIDER`.

    Returns:
        Tupla `(client, provider, model)`: el cliente ya configurado (`openai.OpenAI` o
        `openai.AzureOpenAI`, segun backend), el proveedor efectivo (`"openai"` o `"cortex"`,
        el valor que se reporta en telemetria) y el modelo/deployment efectivo.

    Raises:
        KeyError: si falta una variable de entorno obligatoria para el proveedor elegido
            (`OPENAI_API_KEY` para `openai`, `SNOWFLAKE_ACCOUNT`/`SNOWFLAKE_PAT` para
            `cortex`). Es un error de configuracion, no un fallo operativo: se deja propagar.
    """
    # Carga .env si existe (idempotente y sin pisar variables ya presentes en el entorno,
    # p.ej. en CI). Igual que db.py: cada modulo que lee credenciales lo hace de forma
    # defensiva, sin asumir que otro modulo ya la cargo antes.
    load_dotenv()

    provider = os.environ.get("LLM_PROVIDER", "openai")

    if provider == "cortex":
        account = os.environ["SNOWFLAKE_ACCOUNT"]
        client = OpenAI(
            api_key=os.environ["SNOWFLAKE_PAT"],
            base_url=f"https://{account}.snowflakecomputing.com/api/v2/cortex/v1",
            timeout=60.0,
        )
        model = os.environ.get("CORTEX_MODEL") or DEFAULT_CORTEX_MODEL
        return client, provider, model

    # provider == "openai" (por defecto): API publica de OpenAI, salvo que se configure Azure.
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if azure_endpoint:
        client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION") or DEFAULT_AZURE_API_VERSION,
            api_key=os.environ["OPENAI_API_KEY"],
        )
        model = os.environ["AZURE_OPENAI_DEPLOYMENT"]
        return client, provider, model

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=60.0)
    model = os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
    return client, provider, model

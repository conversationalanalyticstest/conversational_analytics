# Contrato: endpoints del orquestador y de Cortex Analyst

**Feature**: `003-conversational-agent` | **Fecha**: 2026-09-01 (revisado 2026-09-02) | **Fase**: 1

Formato exacto de las llamadas que hace el agente: el orquestador (proveedor configurable, D-11)
y Cortex Analyst (propietario Snowflake, su formato no es adivinable).

Base común de Snowflake: `https://<SNOWFLAKE_ACCOUNT>.snowflakecomputing.com`, con
`SNOWFLAKE_ACCOUNT = GNTUAOQ-YO01002`.

Cortex Analyst se autentica **siempre** con el `SNOWFLAKE_PAT` que ya usa `db.py` (D-03). El
orquestador se autentica según `LLM_PROVIDER`: `OPENAI_API_KEY` si es `openai` (por defecto),
o el mismo `SNOWFLAKE_PAT` si es `cortex` — ninguna combinación introduce dos secretos nuevos.

---

## 1. Orquestador — API de chat completions, compatible con OpenAI

Se consume con el SDK `openai`, **nunca con HTTP a mano**: es lo que exige la Restricción
Tecnológica de la constitución (v2.0.0). El proveedor de destino es configurable por
`LLM_PROVIDER` y se resuelve en un único punto, `build_llm_client()` (D-11): no hay dos rutas de
código distintas en `agent.py`, sólo un cliente ya construido.

### Construcción del cliente

```python
# src/conversational_analytics/llm_provider.py

import os
from openai import OpenAI

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_CORTEX_MODEL = "openai-gpt-4.1"  # verificar disponibilidad antes de fijarlo (D-05)


def build_llm_client() -> tuple[OpenAI, str, str]:
    """Devuelve (client, provider, model) segun LLM_PROVIDER."""
    provider = os.environ.get("LLM_PROVIDER", "openai")

    if provider == "cortex":
        account = os.environ["SNOWFLAKE_ACCOUNT"]
        client = OpenAI(
            api_key=os.environ["SNOWFLAKE_PAT"],
            base_url=f"https://{account}.snowflakecomputing.com/api/v2/cortex/v1",
            timeout=60.0,
        )
        model = os.environ.get("CORTEX_MODEL", DEFAULT_CORTEX_MODEL)
        return client, provider, model

    # provider == "openai" (por defecto)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=60.0)
    model = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    return client, provider, model
```

| Detalle | `openai` (por defecto) | `cortex` (alternativa) |
|---|---|---|
| Credencial | `OPENAI_API_KEY` | `SNOWFLAKE_PAT` (sin secreto nuevo) |
| `base_url` | por defecto del SDK (`api.openai.com`) | `https://<account>.snowflakecomputing.com/api/v2/cortex/v1` |
| Modelo | `OPENAI_MODEL`, por defecto `gpt-4.1-mini` | `CORTEX_MODEL`, verificado antes de fijarlo (D-05) |
| Coste | USD, tarifa pública de OpenAI | créditos de Snowflake |
| Estado en esta cuenta (verificado 2026-09-02) | funciona (conectividad confirmada, 401 con clave falsa) | `403 003001` en los 6 modelos probados — cuenta trial sin esta entitlement |

### Petición (idéntica para los dos proveedores)

```python
client.chat.completions.create(
    model=model,
    messages=messages,
    tools=[QUERY_SEMANTIC_VIEW_SCHEMA],
)
```

### Lo que se consume de la respuesta

| Campo | Uso |
|---|---|
| `choices[0].message.tool_calls` | Si existe → hay que ejecutar la herramienta y volver a llamar |
| `choices[0].message.content` | Respuesta final cuando ya no hay `tool_calls` |
| `usage.prompt_tokens` / `usage.completion_tokens` | Telemetría. **Se acumulan** en todas las llamadas del bucle |

### Restricciones conocidas

- Con `LLM_PROVIDER=cortex`, `tools` (*function calling*) sólo está soportado por parte de los
  modelos de Cortex — documentación: familias `openai-gpt-*` y Claude. El modelo concreto se
  verifica antes de escribir código (D-05). **Esta cuenta en concreto no tiene ninguno
  habilitado** (ver tabla arriba); es un problema de entitlement, no de nombre de modelo.
- La **API de Responses no existe** en Cortex. Sólo Chat Completions. Es irrelevante con el SDK
  `openai` a pelo, pero sería un `404` inmediato con `openai-agents` si no se fuerza
  `OpenAIChatCompletionsModel`.
- Con `LLM_PROVIDER=cortex`, los permisos se resuelven contra el **rol por defecto del
  usuario**, no contra el rol de la sesión del conector (D-04). Un `403` aquí con el conector
  funcionando apunta siempre a esto — aunque en esta cuenta el `403` real observado es de
  entitlement, no de rol (D-11).

---

## 2. Traductor — `/api/v2/cortex/analyst/message`

Formato propietario de Snowflake. El SDK de OpenAI no puede emitirlo ni parsearlo, así que se llama
con `httpx`. Es la única llamada HTTP a mano del proyecto, y está justificada en la tabla de
*Complexity Tracking* del [plan](../plan.md#complexity-tracking).

### Petición

```http
POST /api/v2/cortex/analyst/message
Authorization: Bearer <SNOWFLAKE_PAT>
X-Snowflake-Authorization-Token-Type: PROGRAMMATIC_ACCESS_TOKEN
Content-Type: application/json
```

```json
{
  "semantic_view": "CICD_DEMO.DATA.SV_PHARMA_SALES",
  "messages": [
    {
      "role": "user",
      "content": [{ "type": "text", "text": "¿Cuáles fueron las ventas netas totales en 2025?" }]
    }
  ]
}
```

Notas:

- `content` es una **lista de bloques tipados**, no una cadena. Es el error de integración más
  probable.
- `semantic_view` se lee de `SNOWFLAKE_SEMANTIC_VIEW`, con `CICD_DEMO.DATA.SV_PHARMA_SALES` por
  defecto. Nombre totalmente cualificado.
- Se envía **un único mensaje**: el agente es de un solo turno (FR-006). Este endpoint soporta
  multi-turno pasando el historial, y ese es el punto de extensión de D-09.

### Respuesta

```json
{
  "request_id": "…",
  "message": {
    "role": "analyst",
    "content": [
      { "type": "text", "text": "Esta consulta calcula las ventas netas de 2025…" },
      { "type": "sql", "statement": "SELECT … FROM SEMANTIC_VIEW(…)",
        "confidence": {
          "verified_query_used": {
            "name": "q01_total_net_sales_2025",
            "question": "What were total net sales in 2025?",
            "sql": "…",
            "verified_at": 1756600000
          }
        }
      }
    ]
  },
  "warnings": [],
  "response_metadata": { "model_names": ["…"], "question_category": "…" }
}
```

Cómo se consume cada parte:

| Ruta | Uso |
|---|---|
| `message.content[]` con `type == "sql"` → `statement` | **El SQL. No está ejecutado**: hay que ejecutarlo con `db.py` |
| `…confidence.verified_query_used.name` | `VERIFIED_QUERY_NAME` en telemetría. Señal de calidad gratis (D-06) |
| `message.content[]` con `type == "suggestions"` | No se pudo generar SQL → `status = NO_DATA`, no `ERROR` |
| `message.content[]` con `type == "text"` | Contexto opcional para el modelo. No se usa como respuesta final |
| `request_id` | `ANALYST_REQUEST_ID` en telemetría; es lo que pide el soporte de Snowflake |
| `warnings[]` | Se registra si no está vacío |

### El punto que más se malinterpreta

**Cortex Analyst genera SQL pero no lo ejecuta.** Por eso `query_semantic_view()` hace *dos*
llamadas a Snowflake:

```text
question ──HTTP──> /cortex/analyst/message ──> statement (texto)
                                                   │
statement ──conector──> db.get_connection() ──> filas
```

Separarlas no es un inconveniente: es lo que permite registrar el SQL **antes** de ejecutarlo, que
es lo que exige el Principio IV.

### Mapa de errores

| Situación | Detección | `AgentStatus` |
|---|---|---|
| Timeout (60 s) | `httpx.TimeoutException` | `ERROR` |
| PAT caducado o inválido | HTTP `401` | `ERROR` |
| Falta `SNOWFLAKE.CORTEX_USER` o el rol por defecto es otro | HTTP `403` | `ERROR` |
| Semantic view inexistente o sin permisos | HTTP `400` | `ERROR` |
| No se puede generar SQL / pregunta ambigua | `type == "suggestions"` | `NO_DATA` |
| SQL correcto, cero filas (Q-12) | `len(rows) == 0` | `NO_DATA` |
| SQL generado pero inejecutable | excepción del conector | `ERROR` |

En todos los casos se escribe telemetría antes de devolver (US3, escenario 2).

---

## Variables de entorno

Nuevas en esta feature. Se añaden a `.env.example` (Principio V).

| Variable | Obligatoria | Defecto | Uso |
|---|---|---|---|
| `LLM_PROVIDER` | no | `openai` | Selecciona el proveedor del orquestador: `openai` \| `cortex` (D-11) |
| `OPENAI_API_KEY` | sí, si `LLM_PROVIDER=openai` (defecto) | — | Autentica la API pública de OpenAI |
| `OPENAI_MODEL` | no | `gpt-4.1-mini` | Modelo del orquestador cuando `LLM_PROVIDER=openai` |
| `CORTEX_MODEL` | no | fijado en código tras verificar (D-05) | Modelo del orquestador cuando `LLM_PROVIDER=cortex` |
| `SNOWFLAKE_SEMANTIC_VIEW` | no | `CICD_DEMO.DATA.SV_PHARMA_SALES` | Semantic view del Analyst |

Reutilizadas sin cambios de `db.py`: `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PAT`,
`SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA` — usadas también
por Cortex Analyst, que **siempre** se autentica con `SNOWFLAKE_PAT` sea cual sea `LLM_PROVIDER`.

**`OPENAI_API_KEY` sólo se lee si `LLM_PROVIDER=openai`.** Con `LLM_PROVIDER=cortex` no hace falta
y no debe existir en `.env` (lo verifica `test_provider_matches_config`, D-08).

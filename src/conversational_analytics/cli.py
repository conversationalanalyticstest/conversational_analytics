"""Canal de invocacion del agente (FR-001).

```text
python -m conversational_analytics.cli "¿Cuáles fueron las ventas netas totales en 2025?"
python -m conversational_analytics.cli --verbose "..."
python -m conversational_analytics.cli --check
```
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import cortex_analyst, llm_provider
from .agent import QUERY_SEMANTIC_VIEW_SCHEMA, AgentStatus, ask


def _check() -> int:
    """Verifica proveedor, modelo y conectividad (paso 4 de quickstart.md)."""
    try:
        client, provider, model = llm_provider.build_llm_client()
    except KeyError as exc:
        print(f"ERROR de configuracion: falta la variable de entorno {exc}")
        return 1

    print(f"Proveedor configurado (LLM_PROVIDER): {provider}")
    print(f"Modelo: {model}")

    all_ok = True

    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            tools=[QUERY_SEMANTIC_VIEW_SCHEMA],
            max_completion_tokens=5,
        )
        print(f"Orquestador ({provider}): responde y soporta tools. OK.")
    except Exception as exc:  # noqa: BLE001 - se quiere reportar cualquier fallo, no propagarlo
        print(f"Orquestador ({provider}): ERROR - {exc}")
        all_ok = False

    try:
        cortex_analyst.generate_sql("¿Cuáles fueron las ventas netas totales en 2025?")
        print("Cortex Analyst: responde correctamente. OK.")
    except Exception as exc:  # noqa: BLE001 - idem
        print(f"Cortex Analyst: ERROR - {exc}")
        all_ok = False

    return 0 if all_ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="conversational_analytics.cli",
        description="Agente conversacional sobre SV_PHARMA_SALES.",
    )
    parser.add_argument("question", nargs="?", help="Pregunta en lenguaje natural")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Muestra SQL generado, estado, verified query, tokens, latencia, proveedor y modelo.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verifica el proveedor configurado y el endpoint de Cortex Analyst, sin preguntar nada.",
    )
    args = parser.parse_args(argv)

    if args.check:
        return _check()

    if not args.question:
        parser.error("hace falta una pregunta, o usa --check")

    response = ask(args.question, source="cli")
    print(response.answer)

    if args.verbose:
        print("\n--- detalle ---")
        print(f"estado: {response.status.value}")
        print(f"sql: {response.sql}")
        print(f"verified_query: {response.verified_query_name}")
        print(f"proveedor/modelo: {response.usage.provider}/{response.usage.model}")
        print(
            f"tokens: {response.usage.prompt_tokens} entrada / "
            f"{response.usage.completion_tokens} salida"
        )
        print(f"latencia: {response.latency_ms} ms")
        if response.error_message:
            print(f"error: {response.error_message}")

    return 0 if response.status != AgentStatus.ERROR else 1


if __name__ == "__main__":
    sys.exit(main())

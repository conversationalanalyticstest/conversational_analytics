<!--
SYNC IMPACT REPORT
Version change: 1.0.0 → 2.0.0
Bump rationale: MAJOR. Se revierte una prohibición explícita: la v1.0.0 declaraba
"NO se usa la API pública de OpenAI". La v2.0.0 la permite para la capa de
orquestación. Es una redefinición incompatible hacia atrás de una restricción
tecnológica vinculante, no una aclaración.

Causa: verificación empírica contra la cuenta Snowflake del proyecto (2026-09-02).
La cuenta es de tipo trial y NO tiene habilitada la inferencia LLM de Cortex por
ninguna vía: `SNOWFLAKE.CORTEX.COMPLETE` falla con 399258 ("not available for
trial accounts") y los endpoints REST `/api/v2/cortex/inference:complete` y
`/api/v2/cortex/v1/chat/completions` devuelven 403 003001. La restricción de la
v1.0.0 era, por tanto, imposible de cumplir. Cortex Analyst
(`/api/v2/cortex/analyst/message`) sí funciona y se conserva como pieza obligatoria.

Principios modificados:
  - IV. Observabilidad y Control de Coste — ampliado: el registro MUST incluir
    proveedor y modelo, y el coste MUST indicar su unidad (créditos o USD).

Principios sin cambios: I, II, III, V.

Secciones modificadas:
  - Restricciones Tecnológicas — la viñeta "Modelo" se reescribe separando
    traducción NL→SQL (Cortex Analyst, obligatorio) de orquestación (SDK de
    OpenAI, proveedor configurable). Se añade la viñeta "Salida de datos".

Secciones añadidas: ninguna. Secciones eliminadas: ninguna.

Follow-up TODOs: ninguno. Todos los placeholders resueltos.
-->

# Conversational Analytics Constitution

## Core Principles

### I. Simplicidad Orientada a la Demo (NON-NEGOTIABLE)

Este repositorio existe para **enseñar CI/CD sobre Snowflake de forma visible y en directo**.
Toda decisión técnica MUST optimizar la claridad de la demostración por encima de la
sofisticación.

- MUST elegirse siempre la solución más simple que demuestre el concepto (YAGNI).
- Cualquier componente MUST poder explicarse ante una audiencia en menos de cinco minutos.
- La primera arquitectura de agente MUST ser un agente *stateless* de un solo turno, sin
  memoria de la conversación anterior. Arquitecturas alternativas se añaden únicamente como
  comparativa explícita y nunca sustituyen a la base.
- Toda abstracción, capa o dependencia adicional MUST justificarse por escrito en el plan de
  la feature. Si no aporta a la demo o a un test, se rechaza.

Rationale: el valor del proyecto es pedagógico. Una arquitectura elegante pero inexplicable
es un fracaso del objetivo, aunque sea correcta.

### II. Evaluación del Agente como Test (NON-NEGOTIABLE)

El comportamiento del agente MUST tratarse como código testeable, no como salida impredecible.

- MUST existir un conjunto versionado de preguntas de referencia con su respuesta esperada,
  representativo de lo que preguntarían usuarios reales en producción.
- Cada caso MUST llevar asserts explícitos sobre el resultado: tipo de dato (p. ej. "total de
  ventas" MUST ser numérico), ausencia de `NaN`/`None`, rango o valor esperado, y SQL
  sintácticamente válido y ejecutable.
- Los tests MUST escribirse o actualizarse **antes** del cambio que pretenden validar.
- Ningún cambio en prompts del sistema, semantic views o lógica del agente puede fusionarse ni
  desplegarse sin pasar la suite de evaluación completa.
- Un fallo de evaluación bloquea el despliegue. Cualquier excepción MUST quedar justificada por
  escrito en la PR.

Rationale: un agente sobre datos que responde mal es peor que no tener agente. La confianza en
los números es el requisito de negocio, no un extra.

### III. CI/CD Es el Producto

El pipeline no es infraestructura auxiliar: es exactamente lo que este proyecto demuestra.
MUST existir y mantenerse operativa la cadena completa:

1. **pre-commit local** → lint, formato y evaluación rápida del agente.
2. **Pull Request** → suite completa de tests contra Snowflake.
3. **Merge a `main`** → despliegue automático a Snowflake.
4. **Post-deploy** → re-ejecución de la evaluación contra el entorno ya desplegado.
5. **Fallo post-deploy** → rollback automático a la última versión buena conocida.

- Todo artefacto desplegable (prompts del sistema, semantic views, configuración del agente)
  MUST vivir en Git. Ningún cambio se aplica a mano en la consola de Snowflake.
- Cada despliegue MUST ser identificable por commit SHA y MUST ser reversible.
- El mecanismo de rollback MUST estar probado, no solo documentado.

Rationale: si el pipeline no es fiable, la demo no demuestra nada. Un rollback que nunca se ha
ejecutado no es un rollback.

### IV. Observabilidad y Control de Coste

Cada invocación del agente MUST quedar registrada de forma persistente y consultable.

- Registro mínimo por invocación: timestamp, origen, pregunta, SQL generado, respuesta, tokens
  de entrada y salida, coste estimado, latencia, estado (éxito/error), versión del agente
  (commit SHA), y proveedor y modelo usados para la orquestación.
- El coste MUST registrarse indicando su unidad y proveedor (créditos de Snowflake o USD de
  OpenAI), de forma que sea comparable entre despliegues aunque se cambie de proveedor.
- La telemetría MUST almacenarse en Snowflake, para poder consultarse con SQL como cualquier
  otra tabla del proyecto.
- MUST existir una vista o panel que responda a: qué se ha preguntado, cuánto ha costado y si
  la respuesta fue correcta.
- Ningún cambio que incremente el consumo de tokens se fusiona sin medir y reportar el delta de
  coste en la PR.

Rationale: un agente en producción sin control de coste es un riesgo económico abierto. Medir
antes de escalar es innegociable.

### V. Reproducibilidad y Gestión de Secretos

- Las dependencias MUST gestionarse con Poetry y estar fijadas en `poetry.lock`.
- Las credenciales (Snowflake, tokens de modelo) MUST leerse de variables de entorno y NUNCA
  commitearse. `.env` MUST estar en `.gitignore` y MUST existir un `.env.example` que documente
  cada variable requerida sin valores reales.
- CI MUST obtener sus credenciales de GitHub Secrets, nunca del repositorio.
- El acceso a Snowflake desde CI MUST usar un usuario y rol dedicados con los permisos mínimos
  necesarios, no la cuenta personal de desarrollo.
- Poner en marcha el proyecto en una máquina nueva MUST requerir únicamente: clonar,
  `poetry install`, y rellenar `.env`.

Rationale: un secreto filtrado en un repo de demo es igual de grave que en producción, y una
demo que solo funciona en un portátil concreto no se puede enseñar.

## Restricciones Tecnológicas

- **Lenguaje**: Python, gestionado con Poetry. `pyproject.toml` es la única fuente de verdad de
  dependencias.
- **Datos**: Snowflake. Las tablas de negocio se exponen al agente mediante **semantic views**
  versionadas en el repositorio.
- **Traducción a SQL**: **Cortex Analyst** (`POST /api/v2/cortex/analyst/message`) MUST ser el
  único componente que traduce lenguaje natural a SQL, y siempre contra una semantic view
  versionada en el repositorio. El SQL resultante MUST ejecutarse dentro de Snowflake. Esta
  pieza no es negociable: es la que hace que la demo trate sobre Snowflake.
- **Orquestación**: la capa que razona y redacta la respuesta final usa el **SDK de OpenAI**.
  Se permite apuntarlo a la **API pública de OpenAI** (`OPENAI_API_KEY`) o al endpoint de
  Cortex, según lo que la cuenta tenga habilitado. El `base_url` y el modelo MUST ser
  configurables por variable de entorno, de modo que cambiar de proveedor no requiera tocar
  código ni tests.
- **Salida de datos**: cuando el orquestador sea un proveedor externo, lo único que MUST salir
  de Snowflake es la pregunta del usuario y las filas del resultado de la consulta, acotadas a
  un máximo documentado. MUST NOT enviarse credenciales, tokens ni volcados de tablas
  completas. Este proyecto usa datos ficticios; reutilizar esta arquitectura con datos reales
  MUST revisarse antes.
- **Agente**: el framework queda a elección, priorizando el más simple de explicar. La versión
  inicial es un agente de un solo turno sin contexto previo.
- **CI/CD**: GitHub Actions.
- **Calidad**: pre-commit con linter y formateador; `pytest` como runner de tests.

Introducir cualquier tecnología fuera de esta lista MUST documentarse y justificarse en el plan
de la feature correspondiente.

## Flujo de Desarrollo

**Ciclo obligatorio para todo cambio:**

1. Rama creada desde `main`.
2. `pre-commit` en local: lint, formato y evaluación rápida del agente. Bloquea el commit si falla.
3. Pull Request: GitHub Actions ejecuta la suite completa de tests contra Snowflake.
4. Revisión: MUST haber al menos una aprobación de otro miembro del equipo antes del merge.
5. Merge a `main`: dispara el despliegue a Snowflake y la re-ejecución de la evaluación post-deploy.
6. Si la evaluación post-deploy falla: rollback automático y notificación al equipo.

**Reglas de gate:**

- `main` MUST estar siempre en estado desplegable.
- MUST NOT usarse `--no-verify` ni saltarse checks de CI para acelerar un merge.
- Un cambio en un prompt del sistema es un cambio de producción y recorre el ciclo completo,
  igual que un cambio de código.
- Los tests que fallan se arreglan; no se desactivan ni se marcan como *skip* sin una issue
  abierta que lo justifique.

## Governance

Esta constitución prevalece sobre cualquier otra práctica o preferencia individual dentro del
repositorio.

- Toda PR MUST verificar el cumplimiento de estos principios; una PR que los contradiga sin
  justificación explícita se rechaza.
- **Enmiendas**: se proponen mediante una PR que modifique este documento, incluyendo
  justificación y, si aplica, plan de migración. Requiere la aprobación de otro miembro del
  equipo.
- **Versionado semántico** de esta constitución:
  - MAJOR: retirada o redefinición incompatible de un principio.
  - MINOR: nuevo principio o sección, o ampliación material de la guía existente.
  - PATCH: aclaraciones, redacción y correcciones no semánticas.
- La complejidad MUST justificarse frente al Principio I; ante la duda, gana la opción más
  simple.
- Los artefactos de `specs/` (spec, plan, tasks) son la guía operativa en tiempo de ejecución y
  MUST ser coherentes con este documento.

**Version**: 2.0.0 | **Ratified**: 2026-08-31 | **Last Amended**: 2026-09-02

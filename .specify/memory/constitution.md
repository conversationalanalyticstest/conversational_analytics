<!--
SYNC IMPACT REPORT
Version change: 2.0.0 → 3.0.0
Bump rationale: MAJOR. Se retira el paso "pre-commit local" de la cadena de CI/CD
que el Principio III declaraba MUST mantener operativa, y se elimina la mención
a `pre-commit` como herramienta de calidad obligatoria. Es la retirada de una
obligación normativa ya vinculante (no una aclaración ni una ampliación), de ahí
el MAJOR.

Causa: al diseñar la feature 004-ci-cd-pipeline (speckit-analyze), se detectó que
ninguna spec/plan/tasks del proyecto implementaba el paso de pre-commit, y que
añadirlo no había sido pedido por el equipo. Se decide formalmente no exigirlo a
nivel de constitución en esta fase del proyecto, en vez de mantener una regla
MUST incumplida de forma permanente.

Principios modificados:
  - III. CI/CD Es el Producto — la cadena obligatoria pasa de 5 a 4 pasos (se
    retira "1. pre-commit local"); los pasos restantes se renumeran.

Principios sin cambios: I, II, IV, V.

Secciones modificadas:
  - Restricciones Tecnológicas — la viñeta "Calidad" ya no exige `pre-commit`.
  - Flujo de Desarrollo — el ciclo obligatorio pasa de 6 a 5 pasos (se retira el
    paso de pre-commit local); se ajusta la regla de gate sobre `--no-verify`
    (ya no aplica: no hay hook local que saltarse).

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

1. **Pull Request** → suite completa de tests contra Snowflake.
2. **Merge a `main`** → despliegue automático a Snowflake.
3. **Post-deploy** → re-ejecución de la evaluación contra el entorno ya desplegado.
4. **Fallo post-deploy** → rollback automático a la última versión buena conocida.

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
- **Calidad**: `pytest` como runner de tests.

Introducir cualquier tecnología fuera de esta lista MUST documentarse y justificarse en el plan
de la feature correspondiente.

## Flujo de Desarrollo

**Ciclo obligatorio para todo cambio:**

1. Rama creada desde `main`.
2. Pull Request: GitHub Actions ejecuta la suite completa de tests contra Snowflake.
3. Revisión: MUST haber al menos una aprobación de otro miembro del equipo antes del merge.
4. Merge a `main`: dispara el despliegue a Snowflake y la re-ejecución de la evaluación post-deploy.
5. Si la evaluación post-deploy falla: rollback automático y notificación al equipo.

**Reglas de gate:**

- `main` MUST estar siempre en estado desplegable.
- MUST NOT saltarse checks de CI para acelerar un merge.
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

**Version**: 3.0.0 | **Ratified**: 2026-08-31 | **Last Amended**: 2026-09-03

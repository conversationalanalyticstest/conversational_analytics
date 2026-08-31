# Instrucciones del proyecto — conversational_analytics

Responde siempre en **español**.

## Contexto

Demo pedagógica de **CI/CD sobre Snowflake con Git**. Un agente conversacional consulta tablas
de Snowflake vía *semantic views*, usando Cortex a través del **SDK de OpenAI apuntando al
endpoint de Cortex** (NO la API pública de OpenAI). Equipo de 2-5 personas.

La [constitución del proyecto](../.specify/memory/constitution.md) es **vinculante**. Léela antes
de planificar o implementar y señala cualquier conflicto en vez de resolverlo por tu cuenta.

## Restricciones del entorno (Windows corporativo)

- Los scripts `.ps1` **no se pueden ejecutar** (Group Policy fuerza `AllSigned`, sin bypass).
  Usa siempre `.specify/scripts/python/*.py`. Ignora `.specify/scripts/powershell/`.
- `python` en PATH está roto. Usa el intérprete que indican las skills:
  `C:\Users\dsanchezramos\AppData\Roaming\uv\tools\specify-cli\Scripts\python.exe`.
- Si ejecutas Python a mano con `py`, exporta antes `$env:PYTHONIOENCODING="utf-8"`
  (la consola es cp1252 y los scripts imprimen UTF-8).

## Flujo SDD — orden y gates

El desarrollo sigue Spec Kit. Fases, en orden:

| Fase | Skill | Produce |
|---|---|---|
| 0 | `speckit-constitution` | `.specify/memory/constitution.md` — hecho, v1.0.0 |
| 1 | `speckit-specify` | `specs/<NNN-slug>/spec.md` |
| 1b | `speckit-clarify` *(opcional)* | actualiza `spec.md` |
| 2 | `speckit-plan` | `plan.md` y artefactos de diseño |
| 2b | `speckit-checklist` *(opcional)* | `checklists/` |
| 3 | `speckit-tasks` | `tasks.md` |
| 3b | `speckit-analyze` *(opcional)* | informe de consistencia |
| 4 | `speckit-implement` | código |
| 5 | `speckit-converge` | tareas restantes en `tasks.md` |

### Reglas de ejecución (obligatorias)

1. **Una fase por turno.** Al terminar una fase, PARA. No encadenes automáticamente con la
   siguiente aunque parezca el paso obvio.
2. **Verifica el artefacto previo antes de empezar.** No ejecutes `speckit-plan` sin `spec.md`,
   ni `speckit-tasks` sin `plan.md`, ni `speckit-implement` sin `tasks.md`. Si falta, dilo y
   propón la fase correcta.
3. **No saltes fases** aunque el usuario pida algo que suene a implementación. Si pide código y
   no hay `spec.md`, redirige a `speckit-specify`.
4. Si el usuario dice **"siguiente paso"**, "continúa" o similar: identifica en qué fase está el
   proyecto mirando qué artefactos existen en `specs/`, y ejecuta la siguiente.
5. Cuando invoques una skill, léela con `read_file` y **sigue sus instrucciones al pie de la
   letra**, incluidos los scripts que manda ejecutar.

### Ramas: una por feature

No hay `.specify/extensions.yml`, así que **ninguna skill crea ramas**. Lo haces tú a mano:

- Al empezar una feature nueva (fase 1, `speckit-specify`), crea la rama desde `main` con el
  **mismo nombre que el directorio de la spec**: `specs/001-mock-sales-dataset` →
  rama `001-mock-sales-dataset`.
- Todas las fases siguientes de esa feature (plan, tasks, implement, converge) se trabajan
  **en esa misma rama**. No crees una rama por fase.
- Antes de crear la rama, comprueba que lo que hay sin commitear en `main` pertenece de verdad
  a la feature. Lo que sea infraestructura común (scaffolding, config, tooling) se commitea a
  `main` primero.
- La feature activa está apuntada en `.specify/feature.json`; ese fichero vive en la rama de
  la feature, no en `main`.
- Commitea el artefacto al final de cada fase, con mensaje `<fase>: <qué>`
  (p. ej. `spec: dataset mock de ventas farma`).
- **Nunca hagas `push`, ni abras PR, ni hagas merge sin que el usuario te lo pida.**

## Cierre obligatorio de cada fase

Al terminar **cualquier** fase, termina la respuesta con este bloque:

```markdown
## ✅ Fase completada: <nombre>

**Artefacto generado:** <ruta al fichero, como enlace>

## 🔍 Qué tienes que revisar

- <punto concreto 1>
- <punto concreto 2>
- ...

## ⚠️ Decisiones que he tomado por ti
- <asunción o decisión que el usuario no confirmó explícitamente>
  (omite esta sección si no hay ninguna)

## ➡️ Siguiente paso
`<skill>` — <qué hará>. Dime "adelante" cuando hayas revisado.
```

Los puntos de revisión MUST ser **específicos de lo generado**, no genéricos. Adáptalos a la fase:

- **specify** → alcance incluido/excluido, criterios de aceptación medibles, historias de usuario
  que falten, cualquier `[NEEDS CLARIFICATION]` pendiente.
- **plan** → stack elegido y por qué, cumplimiento de la constitución (sobre todo Principio I:
  simplicidad, y las restricciones tecnológicas), dependencias nuevas, riesgos.
- **tasks** → orden y dependencias, granularidad, que cada tarea tenga criterio de "hecho",
  que los tests aparezcan antes que la implementación (Principio II).
- **implement** → qué tareas quedaron hechas y cuáles no, tests que pasan y que fallan, ficheros
  tocados, deuda técnica introducida.
- **converge** → qué falta respecto a la spec y por qué.

## Estilo

- Marca explícitamente lo que es **asunción tuya** frente a lo que el usuario confirmó.
- Si detectas un conflicto con la constitución, **para y pregunta**; no lo resuelvas en silencio.
- Prefiere la opción más simple: el objetivo del repo es que la demo sea explicable en cinco
  minutos.

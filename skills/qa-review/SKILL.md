---
name: qa-review
description: Revisión de QA de un proyecto o cambio: corre tests y chequeos, busca bugs y problemas de seguridad, verifica cada hallazgo y entrega un reporte de QA con severidades, pasos de reproducción y plan de remediación.
---

# Revisión de QA (`qa-review`)

Activa esta skill cuando el usuario pida "QA", "reporte de QA", "revisá la calidad", "¿está listo para release?", "auditá este proyecto" o invoque `/boost` sobre código.

El entregable es un **artifact `qa_report.md`** en el directorio de la conversación. Nunca escribas el reporte dentro de la carpeta del usuario salvo que lo pida.

## Reglas

- **Solo lectura por defecto.** No edites archivos del proyecto durante la revisión. Los arreglos van después, y solo si el usuario los aprueba.
- **Cada hallazgo debe estar verificado.** Para cada uno, citá archivo y línea, explicá un escenario concreto (entrada → resultado incorrecto) y aclará cómo lo comprobaste: ejecutándolo o leyendo el código. Si no lo pudiste confirmar, marcalo como "Sin confirmar" o descartalo.
- **Nada de hallazgos genéricos.** "Faltan tests" o "mejorar el manejo de errores" no valen sin un caso puntual.
- **Comandos seguros.** Usá `run_command` solo para tests, linters, typecheck y comandos de solo lectura. Nunca ejecutes ataques contra servicios reales ni comandos destructivos para "probar" un hallazgo.
- **Credenciales.** Si encontrás un secreto en el código, informá archivo y línea, pero nunca copies el valor en el reporte.

## Pasos

### 1. Alcance
1. Identificá el commit o la rama (`git rev-parse --short HEAD`, `git status`) y si la revisión es del proyecto completo o de un diff (`git diff <base>...HEAD`).
2. Mapeá la estructura con `find_by_name` y leé `README.md`, los manifiestos de dependencias (`package.json`, `requirements.txt`, `pyproject.toml`) y la configuración de tests.
3. Si el alcance es ambiguo (qué módulos, qué ambiente, si importa la seguridad), preguntá con `ask_question` antes de seguir.

### 2. Chequeos automáticos
Corré lo que el proyecto ya tenga y registrá el resultado exacto (pasan / fallan / cuántos):
- Tests: `pytest -q`, `npm test`, etc.
- Typecheck: `npx tsc --noEmit`, `mypy`.
- Linters: `ruff check`, `eslint`.
- Build: `npm run build`, si es rápido.

Si un comando tarda, dejalo en background (`WaitMsBeforeAsync`) y seguí con el paso 3.

### 3. Revisión manual por dimensión
Recorré el código con `read_file` y `grep_search`. Para proyectos grandes usá `/teamwork`: un subagente por dimensión con `invoke_subagent`, cada uno devolviendo hallazgos con archivo, línea y escenario.

| Dimensión | Qué buscar |
| --- | --- |
| Seguridad | Servidores locales sin autenticación, CORS `*`, WebSockets sin validar `Origin`, rutas de archivo sin validar (`..`, absolutas, symlinks), `eval`/`exec`/`shell=True`/`os.startfile` con datos externos, secretos en el código, listas blancas evitables con `;`, `\|` o `&&` |
| Correctitud | Imports faltantes, condiciones invertidas, casos borde (vacío, `None`, unicode, rutas de Windows), errores tragados con `except: pass` |
| Concurrencia | Estado compartido sin lock, eventos enviados a destinatarios equivocados, futures que nunca se resuelven, tareas en background sin cancelar |
| Estados de la UI | Spinners que nunca terminan, reconexiones, errores que no se muestran, estado perdido al recargar |
| Ciclo de vida | Procesos hijos sin matar, arranque que no espera dependencias, fallas silenciosas si falta un runtime |
| Datos y persistencia | Escrituras sin atomicidad, historiales truncados que quedan inválidos, migraciones de config |
| Mantenibilidad | Archivos de más de 800 líneas, duplicación, URLs y puertos fijos en el código, dependencias sin versión fija |
| Tests | Rutas críticas sin test, tests que no verifican nada, falta de CI |

### 4. Verificación
Antes de escribir el reporte, repasá cada hallazgo como lo haría un revisor escéptico:
- ¿El código realmente hace eso? Releé la función entera, no solo la línea.
- ¿Existe una protección en otra capa que lo evita?
- ¿El escenario es alcanzable desde una entrada real?

Cuando puedas, confirmalo con un test mínimo en el directorio `scratch/` de la sesión, nunca en la carpeta del usuario.

### 5. Severidad

| Severidad | Criterio |
| --- | --- |
| Crítica | Ejecución remota, fuga de credenciales o pérdida de datos explotable sin interacción del usuario |
| Alta | Acceso o escritura fuera de los límites esperados, o un control de seguridad que se puede evitar |
| Media | Bug funcional que el usuario va a encontrar en uso normal, o corrupción de estado |
| Baja | Bug latente, mantenibilidad, dependencias, documentación |

### 6. Reporte
Escribí `qa_report.md` con `write_file` y `ArtifactMetadata` (`UserFacing=true`, `RequestFeedback=true`), con esta estructura:

```markdown
# Reporte de QA — <proyecto>
Fecha · commit `<sha>` · alcance

## Resumen ejecutivo
Veredicto (apto / apto con reservas / no apto) en la primera oración.
Tabla: severidad | cantidad | área principal.

## Alcance y metodología
Qué se revisó, qué comandos se corrieron y su resultado, qué NO se cubrió.

## Hallazgos
Por cada uno: ID (SEC-01, BUG-01, QA-01) · severidad · dónde (archivo:línea) · problema ·
reproducción · impacto · fix · verificado (ejecutado / por inspección / sin confirmar).

## Cobertura de tests
Tests existentes y casos a agregar, priorizados.

## Plan de remediación y criterios de salida
Fases con checklist; condiciones concretas para habilitar el release.
```

Escribí en el idioma del usuario, con oraciones cortas, y poné primero lo más grave.

### 7. Cierre
1. Detenete y esperá la aprobación del reporte (el artifact pide feedback).
2. Si el usuario lo pide, creá tickets con `jira_create_issue` (uno por hallazgo Crítico o Alto) o issues con `github_create_issue`, y agregá el link de cada uno al reporte.
3. Si el usuario aprueba arreglar, empezá por la Fase 1 y agregá un test por cada hallazgo corregido.

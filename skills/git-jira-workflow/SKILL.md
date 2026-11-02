---
name: git-jira-workflow
description: Flujo automatizado entre Jira Cloud, Confluence y GitHub.com usando los conectores MCP de Micelio Desktop.
---

# Flujo Integrado Jira + Confluence + GitHub (`git-jira-workflow`)

Activa esta skill cuando el usuario pida tomar un ticket de Jira, investigar su contexto en Confluence y abrir un Pull Request en GitHub.

## Pasos Recomendados
1. **Inspección del Ticket**: Llama a `jira_get_issue` o `jira_search_issues` para obtener los criterios de aceptación.
2. **Contexto Arquitectónico**: Si el ticket menciona un diseño o microservicio, busca páginas relacionadas con `confluence_search_pages`.
3. **Planificación**: Crea un artifact `implementation_plan.md` con `RequestFeedback=true` para validar el enfoque con el ingeniero.
4. **Implementación y Verificación**: Edita los archivos necesarios y corre los tests con `run_command`.
5. **Pull Request y Actualización de Jira**: Crea el PR con `github_create_pull_request` y deja el enlace en el ticket de Jira usando `jira_add_comment`.

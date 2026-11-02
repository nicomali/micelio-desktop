# Micelio Desktop — Santander Agentic Coding Harness

**Micelio Desktop** es un entorno y *harness* agéntico de programación para escritorio inspirado en **Google Antigravity**, diseñado para uso interno de **Santander**.

## Características Principales

1. **Gateway Multi-LLM (`Phoenix` + `AWS Boto3` + `Anthropic`)**:
   - **`PhoenixProvider`** ([engine/llm/phoenix_provider.py](file:///c:/Users/nico_/OneDrive/Escritorio/Proyectos/micelio-desktop/engine/llm/phoenix_provider.py)): Conecta de forma nativa con la librería corporativa `phoenix` de Santander (`import phoenix`).
   - **`Boto3LambdaBedrockProvider`** ([engine/llm/boto3_provider.py](file:///c:/Users/nico_/OneDrive/Escritorio/Proyectos/micelio-desktop/engine/llm/boto3_provider.py)): Soporta tanto invocación directa a **AWS Bedrock Runtime (`converse`)** como invocación de una **AWS Lambda corporativa (`lambda.invoke`)** vía `boto3`.
   - **`AnthropicDirectProvider`** ([engine/llm/anthropic_provider.py](file:///c:/Users/nico_/OneDrive/Escritorio/Proyectos/micelio-desktop/engine/llm/anthropic_provider.py)): Soporte directo con API Key de Anthropic para desarrollo y pruebas en local.
   - **Protocolo de Tool Calling Universal**: Si la Lambda corporativa o `phoenix` responden en texto plano sin bloques `tool_use` nativos, el parser estructurado XML/JSON traduce automáticamente las llamadas a herramientas y bloques `<thinking>`.

2. **Integración Nativa con el Administrador de Credenciales de Windows (`WinCred`)**:
   - Módulo [engine/credentials.py](file:///c:/Users/nico_/OneDrive/Escritorio/Proyectos/micelio-desktop/engine/credentials.py) conectado directamente a `advapi32.dll` (`CredReadW`, `CredWriteW`, `CredDeleteW`, `CredEnumerateW`).
   - Permite **guardar nuevas credenciales** cifradas con Windows DPAPI (`micelio-desktop/*`) o **vincular credenciales genéricas que ya existan** en tu Administrador de Credenciales de Windows.

3. **Conectores MCP Integrados (Atlassian Cloud & GitHub.com)**:
   - Módulo [engine/mcp_host/manager.py](file:///c:/Users/nico_/OneDrive/Escritorio/Proyectos/micelio-desktop/engine/mcp_host/manager.py):
     - **Jira Cloud**: `jira_search_issues` (JQL), `jira_get_issue`, `jira_create_issue`, `jira_add_comment`.
     - **Confluence Cloud**: `confluence_search_pages` (CQL), `confluence_get_page`.
     - **GitHub.com**: `github_search_repositories`, `github_list_pull_requests`, `github_create_pull_request`, `github_list_issues`, `github_create_issue`, `github_get_file_contents`.
     - **Host MCP Extensible (`stdio`)**: Soporta levantar cualquier servidor MCP adicional inyectando secretos desde Windows Credential Manager en memoria.

4. **Paridad Completa de Herramientas con Antigravity**:
   - `read_file`, `write_file` (con `ArtifactMetadata`), `edit_file`, `find_by_name`, `grep_search`.
   - `run_command` y `manage_task` (transición automática a background y *Reactive Wakeup*).
   - `define_subagent`, `invoke_subagent` (`self`, `research` y custom) y `manage_subagents`.
   - `schedule` (timers y cron jobs con `croniter` y *Reactive Wakeup*).
   - `ask_question` y aprobaciones *Human-in-the-Loop (HITL)*.

---

## Cómo Ejecutar Micelio Desktop

### 1. Instalar dependencias
```powershell
python -m pip install -r engine/requirements.txt
npm install
```

### 2. Iniciar en modo Desarrollo (Motor Python + UI React)
```powershell
npm run dev
```
O abrir directamente la ventana nativa de **Electron**:
```powershell
npm run dev:electron
```

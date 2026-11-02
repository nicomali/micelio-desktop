---
name: santander-standards
description: Estándares de ingeniería, seguridad, uso de la librería corporativa phoenix, AWS Bedrock/Lambda y gestión de secretos con Windows Credential Manager en Santander.
---

# Santander Engineering & Security Standards (`santander-standards`)

Usa esta skill cuando diseñes o modifiques aplicaciones internas, lambdas, pipelines o integraciones con LLMs dentro del ecosistema de **Santander**.

## 1. Gestión de Credenciales (Cero Secretos en Disco)
- **Prohibido** escribir API keys, tokens PAT de GitHub, tokens de Atlassian o llaves IAM de AWS en archivos `.env`, `config.json` o código fuente.
- Todas las credenciales locales deben almacenarse y leerse desde el **Administrador de Credenciales de Windows (WinCred)** a través de `engine.credentials.WindowsCredentialVault` (`micelio-desktop/*`).

## 2. Consumo de Modelos LLM (`phoenix` & `boto3`)
- En entornos corporativos de Santander, prioriza el proveedor `phoenix` (`PhoenixProvider`) o invocación vía `boto3` contra la Lambda/Bedrock corporativa.
- Cuando uses certificados corporativos de Santander, configura `ca_bundle_path` apuntando al bundle `.pem` corporativo.

## 3. Trazabilidad y Auditoría
- Todo cambio de código debe vincularse a un ticket de Jira (`SAN-XXX`) en el título del Pull Request y en los commits.
- Documenta las decisiones de arquitectura en un Artifact (`architecture_plan.md` o `implementation_plan.md`) antes de ejecutar cambios masivos.

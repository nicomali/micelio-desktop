---
name: santander-standards
description: Estándares operativos, de gobernanza, seguridad de datos, conciliación Excel y trazabilidad en Jira/Confluence para entornos productivos de Operaciones de Santander.
---

# Estándares de Operaciones y Gobernanza Santander (`santander-standards`)

Usa esta skill en todas las tareas operativas, cruces de bases de datos, reportes regulatorios/ejecutivos y automatizaciones dentro de **Santander**.

## 1. Higiene de la Carpeta Operativa (Cero Scripts Basura)
- El usuario trabaja en una **carpeta operativa de negocio** (con archivos `.xlsx`, `.csv`, `.pptx`, `.pdf` o scripts productivos propios del área).
- **Regla estricta**: Jamás dejes scripts auxiliares temporales (`.py`) sueltos en la carpeta del usuario. Todo script temporal para generar un Excel, cruzar datos o armar un PowerPoint debe crearse y ejecutarse desde el directorio aislado `scratch/` de la sesión, dejando en la carpeta del usuario **únicamente el archivo entregable final**.

## 2. Calidad en Entregables Excel (`.xlsx`)
- Cuando generes o edites planillas Excel para Operaciones:
  - Ajusta siempre el ancho de todas las columnas automáticamente para que ningún dato ni título quede cortado (`###`).
  - Aplica formato de cabecera corporativo (fondo oscuro `#0F172A` o rojo Santander `#EC0000` con texto blanco en negrita).
  - Formatea montos con separador de miles y moneda (`$#,##0.00`), porcentajes (`0.0%`) y fechas (`YYYY-MM-DD` o `DD/MM/YYYY`).
  - Si es una conciliación o control, incluye una hoja de **Resumen Ejecutivo / KPIs** además del detalle.

## 3. Seguridad y Credenciales (`WinCred`)
- Ninguna clave, token de Jira/Confluence ni credencial de AWS/Phoenix puede escribirse en archivos dentro de la carpeta operativa. Todo se lee desde el **Administrador de Credenciales de Windows**.

---
name: santander-pptx-designer
description: Diseña y genera presentaciones ejecutivas PowerPoint (.pptx) de alta calidad visual con python-pptx, grillas KPI, tablas estilizadas, gráficos y paleta corporativa Santander.
---

# Santander Executive PowerPoint Designer (`santander-pptx-designer`)

Usa esta skill siempre que el usuario te pida crear una **presentación PowerPoint (`.pptx`)**, deck ejecutivo, reporte de comité o slides.

## Reglas de Oro para que el PowerPoint quede Impecable

1. **Formato Widescreen 16:9 obligatorio**:
   - Configura siempre `prs.slide_width = Inches(13.333)` y `prs.slide_height = Inches(7.5)`.
   - Usa el layout en blanco (` prs.slide_layouts[6] `) y construye las formas, fondos, cabeceras y tarjetas programáticamente para tener control total del diseño (nunca uses los bullets grises por defecto de PowerPoint).
2. **Paleta de Colores Ejecutiva (Santander High-Craft)**:
   - **Portada y Slides de Impacto (Dark Theme)**: Fondo `#0B0E14` (`RGBColor(11, 14, 20)`), acento principal Rojo Santander `#EC0000` (`RGBColor(236, 0, 0)`), texto primario Blanco `#FFFFFF` y subtítulos `#94A3B8`.
   - **Slides de Contenido / Datos (Clean Light o Dark Card)**: Fondo `#F8FAFC` (`RGBColor(248, 250, 252)`), tarjetas blancas `#FFFFFF` con borde fino `#E2E8F0` y barra superior de acento `#EC0000`, textos oscuros `#0F172A`.
3. **Componentes Visuales Ricos**:
   - **Header consistente en cada slide**: Barra superior fina de `0.08"` en `#EC0000`, categoría en mayúsculas pequeñas (`10pt` bold `#EC0000`) y título principal en `24pt` bold (`Segoe UI` o `Arial`).
   - **Tarjetas KPI (Metric Cards)**: Usa `MSO_SHAPE.ROUNDED_RECTANGLE` con números grandes (`32pt` bold `#EC0000`), etiqueta (`11pt` `#64748B`) y bajada explicativa.
   - **Gráficos y Tablas**: Si hay series de datos, genera gráficos limpios en alta resolución (`dpi=220`) con `matplotlib` guardados en el directorio `scratch/` y embébelos con `slide.shapes.add_picture(...)`, o usa tablas con cabecera en `#0F172A` y filas alternadas.
4. **Script Generador en `scratch/`**:
   - Recuerda guardar el script `.py` que construye el `.pptx` dentro del directorio `scratch` de la conversación y guardar el archivo `.pptx` final directamente en el Workspace del usuario.

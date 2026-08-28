# Normativa de la memoria — reglas operativas

Destilado de `TFM-MUIoT-Guía para a memoria.pdf` (en este mismo directorio) y de la
plantilla oficial. **Esta es la checklist a aplicar al redactar; no hay que releer el PDF.**
Si algo de aquí contradice al PDF, manda el PDF.

## Formato del documento
| Aspecto | Requisito |
| :--- | :--- |
| Formato | DIN A4, **doble cara**, impresión a doble cara |
| Márgenes | ≥ 25 mm en los cuatro lados |
| Fuente | Times New Roman o Baskerville, **estilo recto**, ≥ 12 pt |
| Espaciado | Sencillo, con **línea en blanco entre párrafos** |
| Justificación | Texto justificado por ambos márgenes |
| Numeración | Todas las páginas en cifras árabes, salvo la portada |
| Extensión | **25–50 páginas** sin contar anexos, incluyendo tablas, gráficos y portada |

La plantilla (`memoria_TFM/tfm-muiot.sty`) ya impone márgenes, fuente y tamaño. **No hay
que ajustar formato a mano: si algo se sale de norma, es un error de contenido.**

## Títulos y jerarquía
- Títulos de sección y subsección: **alineados a la izquierda, en negrita, numerados**.
- **Máximo dos niveles jerárquicos.** En la práctica: `\chapter` + `\section`.
  **No usar `\subsection`.** Si un tema pide un tercer nivel, es señal de que debe ser una
  sección independiente o una lista.
- Se prefieren encabezados de página que indiquen el título del documento o de la sección
  (activado con `\headers{true}`).

## Cursiva — uso restringido
Solo en tres casos, sin abuso:
1. Énfasis de una palabra o frase dentro de un párrafo.
2. Neologismos o extranjerismos no adoptados ampliamente (*edge*, *broker*, *dataset*).
3. Nombres propios en otras lenguas, si las convenciones lo requieren.

## Figuras y tablas
- Colocadas preferiblemente arriba o abajo de la página, o en página completa.
- **Siempre** etiqueta numerada de referencia (`\label`) + título o leyenda explicativa.
- Los títulos de las **tablas van arriba** (la plantilla lo impone con `captions=tableabove`).
- Han de ser claras y legibles: comprobar tamaño de fuente en las gráficas exportadas.
- Toda figura y tabla debe estar **citada en el texto** (`\ref{...}`), no colgada suelta.
- Leyendas y notas al pie: misma tipografía que el cuerpo, admitido tamaño menor.

## Ecuaciones, símbolos y unidades
- Ecuaciones no triviales: **centradas** y en línea propia; numeradas si se referencian.
- Notación matemática libre, pero **coherente en todo el documento**. No introducir símbolos
  u operadores propios sin definirlos antes.
- **Unidades:** son símbolos, no abreviaturas → **sin punto** y **con espacio** tras la
  cifra: `10 m`, `3 GHz`, `2,4 GHz`, `750 ms`. Nunca `10m.` ni `3Ghz`.
- Notación científica para cantidades numéricas; **evitar cifras con muchos decimales**.
  Ejemplo: reportar `4,3 °C`, no `4,31245 °C`.
- El paquete `siunitx` **no** está cargado por la plantilla: escribir las unidades como
  texto (con `\mbox{}` para evitar cortes de línea) o cargarlo explícitamente.

## Bibliografía
- Estilo **IEEE** (la plantilla usa `IEEEtran.bst`) u Harvard. Se ha fijado IEEE.
- Cada entrada debe permitir identificar: **autores, título, publicación y año**.
- Documentos electrónicos: incluir **URL de acceso y fecha de consulta**.
- Todas las entradas van en `memoria_TFM/referencias.bib` en formato BibTeX.
- Regla del proyecto: **cita sin entrada en el `.bib` = error**. Nunca inventar una
  referencia; si no se ha leído la fuente, dejar un `% TODO` y no citarla.

## Estilo de redacción
- **La claridad prevalece** sobre cualquier consideración estilística.
- Documento **autónomo**: comprensible sin recurrir al contexto ni a fuentes externas.
- Estilo **neutro y objetivo**. **Evitar la primera persona** (ni "he implementado" ni
  "hemos diseñado" → "se implementó", "el sistema implementa").
- Párrafos ni excesivamente largos ni mal estructurados.
- Terminología técnica con rigor y precisión; **sin lenguaje informal**.
- Siglas y acrónimos: desarrollar en su primera aparición, con el término original si es
  inglés (p. ej. "*Message Queuing Telemetry Transport* (MQTT)").

## Estructura obligatoria (mínimo exigido)
| # | Contenido | Fichero |
| :--- | :--- | :--- |
| A | Introducción al problema | `capitulos/01-introduccion.tex` |
| B | Análisis de necesidades y estado del arte | `capitulos/02-estado-del-arte.tex` |
| C | Objetivos | `capitulos/03-objetivos.tex` |
| D | Metodología desarrollada **de forma sucesiva** | `capitulos/04-metodologia.tex` |
| E | Decisiones técnicas, incluido el uso de normas y estándares **o la justificación de su ausencia** | `capitulos/05-diseno.tex` |
| F | Resultados obtenidos, **justificando los objetivos no alcanzados** | `capitulos/06-resultados.tex` |
| G | Discusión y conclusiones, valorando el impacto en responsabilidad legal, ética y profesional (privacidad, seguridad) y su influencia en los resultados | `capitulos/07-conclusiones.tex` |
| H | Bibliografía | `referencias.bib` |
| I | Anexos técnicos | `capitulos/A*-anexo-*.tex` |

Dos exigencias que suelen olvidarse y que la Guía pide explícitamente:
- **F**: justificar por qué no se alcanzaron los objetivos que no se alcanzaron.
- **G**: valorar responsabilidad legal, ética y profesional (aquí: privacidad del micrófono,
  seguridad del canal MQTT).

## Datos administrativos (portada)
| Campo | Valor |
| :--- | :--- |
| Título | Sistema IoT Edge para mantenimiento predictivo de compresores de refrigeración |
| Autor | Sergio Villodas Zapata |
| Tutor | Tiago Manuel Fernández Caramés |
| Universidad | UDC (opción `udc` del paquete `tfm-muiot`) |
| Curso | 2025/2026 |
| Idioma | castellano (`\usepackage[spanish]{babel}`; la solicitud admite galego/castelán/inglés) |
| Duración | 6 ECTS (1 ECTS = 25 h) → ≈ 150 h |

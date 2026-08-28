#!/usr/bin/env bash
# Compila la memoria del TFM y deja memoria_TFM.pdf en este directorio.
#
# La plantilla usa fontspec, por lo que requiere XeLaTeX o LuaLaTeX (no pdflatex).
# En este equipo el binario 'xelatex' es un envoltorio de tectonic y latexmk falla al no
# encontrar el .log esperado, así que se invoca tectonic directamente.
set -euo pipefail
cd "$(dirname "$0")"

if command -v tectonic >/dev/null 2>&1; then
    tectonic -X compile memoria_TFM.tex --keep-intermediates --reruns 2
elif command -v latexmk >/dev/null 2>&1; then
    latexmk -xelatex -interaction=nonstopmode memoria_TFM.tex
else
    echo "No se encontró tectonic ni latexmk. Instala uno de los dos." >&2
    exit 1
fi

echo
echo "PDF generado: $(pwd)/memoria_TFM.pdf"

# El recuento de páginas se toma de pdfinfo y no de mdls: los metadatos de
# Spotlight se sirven de una caché que puede devolver el valor de la
# compilación anterior justo después de reescribir el PDF.
if command -v pdfinfo >/dev/null 2>&1; then
    paginas=$(pdfinfo memoria_TFM.pdf | awk '/^Pages:/ {print $2}')
    echo "Páginas: ${paginas}  (objetivo: 25-50 sin contar anexos ni bibliografía)"
else
    echo "Instala poppler (brew install poppler) para conocer el número de páginas."
fi

# Avisos que conviene no dejar pasar
if [ -f memoria_TFM.log ]; then
    citas_sin_resolver=$(grep -c 'LaTeX Warning: Citation' memoria_TFM.log 2>/dev/null || true)
    if [ "${citas_sin_resolver:-0}" -gt 0 ]; then
        echo "AVISO: hay citas sin resolver (revisa referencias.bib)."
    fi
fi
pendientes=$(grep -rc '% TODO' capitulos/*.tex 2>/dev/null | awk -F: '{s+=$2} END {print s+0}' || true)
echo "Marcas % TODO pendientes en los capítulos: ${pendientes}"


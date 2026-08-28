#!/usr/bin/env bash
# =====================================================================
# Trae los CSV de un concentrador y los integra en la serie que le
# corresponde, sin sobrescribir ni borrar nada.
#
# Se ejecuta en el EQUIPO DE DESARROLLO.
#
#   ./server/traer-datos.sh 10.42.0.1 iiot-c nodo-a-nevera-buena/fw-46col
#   ./server/traer-datos.sh 10.45.127.20 admin nodo-b-otro-compresor/fw-46col
#
# Por que no un rsync directo: el concentrador solo tiene la captura en
# curso, mientras que en local las series estan consolidadas a partir de
# varios fragmentos. Un rsync espejo con --delete se lleva todo lo demas
# (ya ocurrio), y una copia directa encima descarta la consolidacion.
#
# Este procedimiento copia a un area de entrada, mezcla por marca de
# tiempo y solo entonces escribe la serie. Es idempotente: traer dos veces
# los mismos datos no duplica filas.
# =====================================================================
set -euo pipefail

HOST="${1:-}"
USER_PI="${2:-}"
SERIE="${3:-}"
REMOTO="${REMOTO:-TFM/server/data}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
ENTRADA="$REPO_DIR/server/data/_entrada"

log() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[[ -n "$HOST" && -n "$USER_PI" && -n "$SERIE" ]] || die "faltan argumentos.
       Uso:  ./server/traer-datos.sh <direccion> <usuario> <serie>
       Series disponibles (ver server/data/manifiesto.json):
         nodo-a-nevera-buena/fw-46col
         nodo-b-otro-compresor/fw-46col"

DESTINO="$REPO_DIR/server/data/$SERIE"
[[ -d "$DESTINO" ]] || die "la serie '$SERIE' no existe en server/data/.
       Crea el directorio primero si es una serie nueva."

log "Copiando de $USER_PI@$HOST:~/$REMOTO"
rm -rf "$ENTRADA"; mkdir -p "$ENTRADA"
# scp y no rsync: sin opcion de borrado, no puede vaciar nada.
scp "$USER_PI@$HOST:$REMOTO/*.csv" "$ENTRADA/" || die "no se copio nada.
       Comprueba la direccion, el usuario y que existan CSV en ~/$REMOTO
       (si DATA_DIR apunta a un subdirectorio, indicalo con REMOTO=...)"
ls -la "$ENTRADA"

log "Integrando en $SERIE"
"$REPO_DIR/.venv/bin/python" - "$ENTRADA" "$DESTINO" <<'PYEOF'
import csv, io, sys
from pathlib import Path
entrada, destino = Path(sys.argv[1]), Path(sys.argv[2])

def leer(p):
    raw = open(p, 'rb').read()
    nul = raw.count(b'\x00')
    rows = list(csv.reader(io.StringIO(raw.replace(b'\x00', b'').decode('utf-8', errors='replace'))))
    if not rows:
        return None, [], nul
    return rows[0], [r for r in rows[1:] if r and r[0].startswith('20')], nul

for nuevo in sorted(entrada.glob('*.csv')):
    actual = destino / nuevo.name
    cab_n, filas_n, nul = leer(nuevo)
    if cab_n is None:
        print(f"  {nuevo.name}: vacio, se omite"); continue
    # Solo se aceptan filas cuya anchura coincida con la cabecera: una fila
    # mas ancha significa que el registrador se actualizo a mitad de fichero
    # y sus columnas estan desplazadas.
    desal = [r for r in filas_n if len(r) != len(cab_n)]
    filas_n = [r for r in filas_n if len(r) == len(cab_n)]

    filas = {}
    antes = 0
    if actual.exists():
        cab_a, filas_a, _ = leer(actual)
        if cab_a != cab_n:
            print(f"  {nuevo.name}: CABECERAS DISTINTAS ({len(cab_a)} vs {len(cab_n)} col)."
                  f" No se mezcla: pertenecen a firmwares distintos.")
            continue
        filas = {r[0]: r for r in filas_a}
        antes = len(filas)
    filas.update({r[0]: r for r in filas_n})

    with open(actual, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(cab_n)
        for ts in sorted(filas):
            w.writerow(filas[ts])
    print(f"  {nuevo.name}: {antes} -> {len(filas)} filas (+{len(filas)-antes} nuevas)"
          + (f"  [{nul} bytes NUL retirados]" if nul else "")
          + (f"  [{len(desal)} filas desalineadas OMITIDAS]" if desal else ""))
PYEOF

rm -rf "$ENTRADA"
log "Estado de la serie"
wc -l "$DESTINO"/*.csv

#!/usr/bin/env bash
# =====================================================================
# Sincroniza el proyecto con el concentrador y lo actualiza, en un paso.
#
# Se ejecuta en el EQUIPO DE DESARROLLO, no en la Raspberry Pi.
#
#   ./server/sync-pi.sh 10.42.0.1 iiot-c
#   ./server/sync-pi.sh 10.45.127.17 admin
#
# El usuario es OBLIGATORIO y no tiene valor por omision a proposito: los
# concentradores de este proyecto no comparten usuario (10.42.0.1 usa iiot-c y
# 10.45.127.x usa admin), de modo que cualquier valor por omision es el
# equivocado la mitad de las veces y el sintoma es una peticion de contrasena
# que parece un problema de red.
#
# Por qué existe: escribir el rsync a mano es propenso a dos errores que
# ya se han producido en este proyecto.
#
#   1. Anidar directorios. Un desajuste en las barras finales produce
#      server/data/data o server/data/server, y entonces el registrador
#      escribe en un sitio y el analisis lee de otro.
#   2. Sobrescribir la configuracion del concentrador. server/.env
#      contiene la direccion del intermediario y server/data los datos
#      capturados: ambos viven en la Pi y copiarlos desde el portatil
#      destruye lo que hay. Ya ocurrio una vez, y el registrador quedo
#      suscrito al prefijo de topic del intermediario publico.
#
# Las exclusiones y las barras finales quedan fijadas aqui para que no
# haya que recordarlas.
# =====================================================================
set -euo pipefail

HOST="${1:-}"
USER_PI="${2:-}"
DEST_DIR="${DEST_DIR:-TFM}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

log() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[[ -n "$HOST" && -n "$USER_PI" ]] || die "faltan argumentos.
       Uso:  ./server/sync-pi.sh <direccion> <usuario>

       Concentradores conocidos del proyecto:
         10.42.0.1        iiot-c    (nodo A, el del punto de acceso)
         10.45.127.17     admin
         10.45.127.20     admin

       Si pide contraseña, lo mas probable es que el usuario no sea ese: la
       clave publica solo esta autorizada para el usuario correcto."

[[ -f "$REPO_DIR/server/mqtt_logger.py" ]] || die "no encuentro el proyecto en $REPO_DIR"

log "Sincronizando $REPO_DIR -> $USER_PI@$HOST:~/$DEST_DIR"
echo "Se excluyen (viven en el concentrador, no en el portátil):"
echo "  .venv         entorno virtual, propio de la arquitectura de la Pi"
echo "  server/.env   configuración del intermediario"
echo "  server/data   datos capturados"
echo

# La barra final en origen y destino es lo que evita el anidamiento: con
# ella se copia el CONTENIDO del directorio, no el directorio en si.
rsync -av --human-readable \
  --exclude '.venv' \
  --exclude 'server/.env' \
  --exclude 'server/data' \
  --exclude '.DS_Store' \
  --exclude '__pycache__' \
  "$REPO_DIR/" "$USER_PI@$HOST:$DEST_DIR/"

log "Actualizando el concentrador"
# La fase 'actualizar' reinstala dependencias si cambiaron y archiva los
# CSV cuya cabecera ya no corresponde al codigo, porque el registrador
# solo escribe la cabecera al crear el fichero: sin esto, los campos
# nuevos se descartarian en silencio durante el resto de la jornada.
ssh -t "$USER_PI@$HOST" "cd $DEST_DIR && chmod +x server/provision-pi.sh && sudo ./server/provision-pi.sh actualizar"

log "Comprobando la cadena"
ssh -t "$USER_PI@$HOST" "cd $DEST_DIR && ./server/provision-pi.sh comprobar"

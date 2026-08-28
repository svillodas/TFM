#!/usr/bin/env bash
# =====================================================================
# Aprovisionamiento del hub (Raspberry Pi) para las campañas de medida.
#
# Deja la Pi actuando como punto de acceso Wi-Fi propio, de forma que el
# nodo ESP32 se conecte directamente a ella sin router intermedio. Eso
# resuelve tres problemas de golpe:
#
#   - La IP del broker deja de depender del DHCP de un router ajeno:
#     NetworkManager fija siempre 10.42.0.1 en modo compartido, así que
#     MQTT_SERVER queda constante y no hay que reflashear el nodo cada vez
#     que cambia la red.
#   - El montaje es portátil: funciona en cualquier sitio donde haya un
#     enchufe, sin depender de la Wi-Fi del local.
#   - La red queda aislada, lo que reduce el riesgo de que alguien
#     publique tramas falsas en los topics y contamine el dataset.
#
# ORDEN DE EJECUCIÓN. Las fases están separadas a propósito:
#
# El usuario y el directorio del proyecto se detectan solos: el proyecto a
# partir de la ubicacion de este script, y el usuario a partir de quien
# invoca sudo. Ambos pueden forzarse por variable de entorno (RUN_USER,
# REPO_DIR) si hiciera falta.
#
#   sudo ./provision-pi.sh paquetes    # necesita Internet
#   sudo ./provision-pi.sh broker
#   sudo ./provision-pi.sh logger
#   sudo ./provision-pi.sh ap          # ÚLTIMA: corta la Wi-Fi actual
#
# La fase "ap" convierte wlan0 en punto de acceso. Si estabas conectado
# por SSH sobre Wi-Fi, PIERDES la sesión en ese momento y solo podrás
# volver a entrar uniéndote a la red del propio punto de acceso, o por
# cable, o con teclado y monitor. Instala todo antes de lanzarla: una vez
# activa, la Pi ya no tiene salida a Internet por Wi-Fi.
# =====================================================================
set -euo pipefail

# Ajustar antes de ejecutar la fase "ap".
AP_SSID="${AP_SSID:-TFM-NODO}"
AP_PASS="${AP_PASS:-}"          # obligatoria, mínimo 8 caracteres
AP_IP="10.42.0.1/24"
AP_IFACE="${AP_IFACE:-wlan0}"

# El directorio del proyecto se deduce de la ubicación de este propio
# script, que vive en <proyecto>/server/, de modo que funciona con
# independencia de dónde se haya copiado el proyecto y en qué equipo.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(dirname "$SCRIPT_DIR")}"

# El usuario que ejecutará el registrador es el que invocó sudo. Si no
# hubiera invocación por sudo, se toma el propietario del directorio del
# proyecto. No se codifica ningún nombre concreto: el concentrador puede
# ser cualquier equipo, con cualquier usuario.
if [[ -z "${RUN_USER:-}" ]]; then
  RUN_USER="${SUDO_USER:-}"
  [[ -z "$RUN_USER" ]] && RUN_USER="$(stat -c '%U' "$REPO_DIR" 2>/dev/null || true)"
fi
RUN_USER="${RUN_USER:-root}"

# Directorio personal real del usuario, en lugar de suponer /home/<usuario>.
RUN_HOME="$(getent passwd "$RUN_USER" 2>/dev/null | cut -d: -f6)"
[[ -n "$RUN_HOME" && -d "$RUN_HOME" ]] || RUN_HOME="$REPO_DIR"

log() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# Solo las fases que modifican el sistema exigen root; la ayuda y el
# diagnóstico de estado deben poder consultarse sin privilegios.
need_root() { [[ $EUID -eq 0 ]] || die "la fase '$1' necesita sudo"; }

# ---------------------------------------------------------------------
# Diagnóstico del entorno. Se ejecuta siempre, antes de cualquier cambio.
# ---------------------------------------------------------------------
diagnostico() {
  log "Entorno"
  echo "Proyecto: $REPO_DIR"
  echo "Usuario:  $RUN_USER   (directorio personal: $RUN_HOME)"
  echo "Sistema:  $(. /etc/os-release && echo "$PRETTY_NAME")"
  echo "Modelo:   $(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo desconocido)"

  if command -v nmcli >/dev/null 2>&1 && systemctl is-active --quiet NetworkManager; then
    echo "Red:      NetworkManager activo (la fase 'ap' usará nmcli)"
  else
    die "NetworkManager no está activo. Este script asume Raspberry Pi OS
       Bookworm o posterior. En versiones con dhcpcd hay que montar el
       punto de acceso con hostapd y dnsmasq, que es otro procedimiento."
  fi

  echo
  echo "Interfaces con dirección:"
  ip -brief address show | grep -v '^lo' || true
  echo

  # No todos los chips Wi-Fi admiten modo punto de acceso. Comprobarlo
  # antes evita dejar la interfaz a medio configurar.
  if iw list 2>/dev/null | grep -A12 'Supported interface modes' | grep -qw 'AP'; then
    echo "Wi-Fi:    el chip admite modo punto de acceso"
  else
    echo "AVISO: no se confirma que el chip admita modo punto de acceso."
    echo "La fase 'ap' puede fallar. Revisa 'iw list'."
  fi
  echo
  if ip link show eth0 >/dev/null 2>&1 && ip -brief address show eth0 | grep -q UP; then
    echo "Cable Ethernet CONECTADO: podrás mantener el acceso de gestión"
    echo "por cable mientras wlan0 hace de punto de acceso. Es el escenario"
    echo "recomendado."
  else
    echo "AVISO: sin cable Ethernet. Al activar el punto de acceso perderás"
    echo "el acceso actual y tendrás que entrar por la red '$AP_SSID'"
    echo "(la Pi estará en ${AP_IP%/*}) o con teclado y monitor."
  fi
}

# ---------------------------------------------------------------------
fase_paquetes() {
  log "Instalando paquetes (requiere Internet)"
  apt-get update
  apt-get install -y mosquitto mosquitto-clients python3-venv python3-pip rsync
  systemctl stop mosquitto || true    # se arranca ya configurado en la fase siguiente
  echo "Hecho. Copia ahora el repositorio a $REPO_DIR si no está ya."
}

# ---------------------------------------------------------------------
fase_broker() {
  local main_conf=/etc/mosquitto/mosquitto.conf
  local our_conf=/etc/mosquitto/conf.d/tfm.conf

  # Configuración efectiva del broker, excluyendo nuestro propio fichero de
  # ejecuciones anteriores: interesa saber qué había antes de tocar nada.
  # En una máquina compartida es habitual que Mosquitto ya esté configurado
  # para otro uso, y pisarlo rompería el trabajo de otra persona.
  efectiva() {
    cat "$main_conf" 2>/dev/null || true
    local f
    for f in /etc/mosquitto/conf.d/*.conf; do
      [[ -f "$f" && "$f" != "$our_conf" ]] && cat "$f" || true
    done
    return 0
  }

  log "Inspeccionando la configuración existente de Mosquitto"
  echo "Ficheros de configuración presentes:"
  ls -1 "$main_conf" /etc/mosquitto/conf.d/*.conf 2>/dev/null | grep -v 'tfm\.conf' || true
  echo
  echo "Directivas relevantes:"
  efectiva | grep -nE '^[[:space:]]*(listener|allow_anonymous|bind_address|password_file|per_listener_settings)' \
    || echo "  (ninguna: Mosquitto usaría sus valores por omisión)"
  echo

  local l1883 l1883_local anon
  l1883=$(efectiva | grep -cE '^[[:space:]]*listener[[:space:]]+1883([[:space:]]|$)' || true)
  l1883_local=$(efectiva | grep -E '^[[:space:]]*listener[[:space:]]+1883([[:space:]]|$)' \
                | grep -cE '(localhost|127\.0\.0\.1)' || true)
  anon=$(efectiva | grep -cE '^[[:space:]]*allow_anonymous[[:space:]]+true' || true)

  # Un fichero nuestro de una ejecución anterior solo puede estorbar: la
  # decisión se toma siempre sobre la configuración ajena.
  rm -f "$our_conf"

  if (( l1883 > 0 && l1883_local == 0 && anon > 0 )); then
    # Mejor resultado posible en una máquina compartida: cero cambios.
    log "La configuración existente ya sirve: no se escribe nada"
    echo "Hay un listener en el 1883 abierto a la red y conexiones anónimas"
    echo "permitidas, que es justo lo que necesita el nodo."

  elif (( l1883 > 0 && l1883_local > 0 )); then
    # No se reescribe un fichero ajeno sin permiso: solo se informa.
    die "hay un listener en el 1883 restringido a localhost, puesto por otra
       configuración. El ESP32 no podría conectarse, pero ese fichero no es
       nuestro y no lo voy a modificar. Localízalo con:
         grep -rn 'listener' /etc/mosquitto/
       y cambia 'localhost' por '0.0.0.0', o dime qué fichero es."

  elif (( l1883 > 0 && anon == 0 )); then
    log "Hay listener en el 1883, pero falta permitir conexiones anónimas"
    # Solo se añade lo que falta. No se declara un segundo listener: dos
    # 'listener 1883' colisionan en el puerto y Mosquitto no arranca.
    printf '%s\n' 'allow_anonymous true' > "$our_conf"

  else
    log "Sin listener declarado: se crea uno"
    # Mosquitto 2.x, sin listener explícito, solo escucha en localhost y
    # rechaza conexiones anónimas.
    cat > "$our_conf" <<'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF
  fi

  systemctl enable mosquitto >/dev/null 2>&1 || true
  systemctl restart mosquitto 2>/dev/null || true
  sleep 2

  if ! systemctl is-active --quiet mosquitto; then
    log "Mosquitto no arranca. Error real que devuelve"
    rm -f "$our_conf"
    timeout 4 mosquitto -c "$main_conf" 2>&1 | grep -iE 'error|warn' | head -10 || true
    systemctl restart mosquitto 2>/dev/null || true
    die "nuestro fichero se ha retirado, así que el broker queda como estaba.
       Pásame la salida de arriba."
  fi

  log "Mosquitto activo"
  ss -lntp 2>/dev/null | grep 1883 || echo "  (el 1883 no aparece: revísalo)"
  # El nodo necesita que escuche en todas las interfaces, no solo en local.
  if ss -lnt 2>/dev/null | grep -qE '(0\.0\.0\.0|\*):1883'; then
    echo "Correcto: acepta conexiones de la red."
  else
    die "parece escuchar solo en localhost; el ESP32 no podrá conectarse.
       Revisa 'grep -rn listener /etc/mosquitto/'"
  fi
}

# ---------------------------------------------------------------------
fase_logger() {
  log "Preparando el logger como servicio"
  [[ -f "$REPO_DIR/server/mqtt_logger.py" ]] || die "no encuentro $REPO_DIR/server/mqtt_logger.py.
       Copia el repositorio a la Pi antes de esta fase, por ejemplo desde el Mac:
         rsync -av --exclude .venv <ruta-local>/TFM/ $RUN_USER@<ip-de-la-pi>:$REPO_DIR/"

  sudo -u "$RUN_USER" python3 -m venv "$REPO_DIR/.venv"
  sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/server/requirements.txt"

  # El broker corre en la propia Pi, así que el logger se conecta a
  # localhost. Prefijo vacío: los topics van tal cual, sin el prefijo que
  # solo hacía falta contra el broker público.
  cat > "$REPO_DIR/server/.env" <<EOF
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_TOPIC_PREFIX=
MQTT_USER=
MQTT_PASSWORD=
DATA_DIR=$REPO_DIR/server/data
EOF
  chown "$RUN_USER":"$RUN_USER" "$REPO_DIR/server/.env"
  chmod 600 "$REPO_DIR/server/.env"

  # Restart=always para que una campaña de 24 h sobreviva a un fallo
  # puntual del proceso. Los datos crudos son irrecuperables si se
  # pierden, así que el servicio no debe rendirse.
  cat > /etc/systemd/system/tfm-logger.service <<EOF
[Unit]
Description=Logger MQTT a CSV del TFM
After=mosquitto.service
Wants=mosquitto.service

[Service]
User=$RUN_USER
WorkingDirectory=$REPO_DIR
ExecStart=$REPO_DIR/.venv/bin/python server/mqtt_logger.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable tfm-logger
  systemctl restart tfm-logger
  sleep 2
  systemctl is-active --quiet tfm-logger || die "el logger no arrancó; mira 'journalctl -u tfm-logger -n 40'"

  log "Comprobación extremo a extremo con una trama sintética"
  mosquitto_pub -h localhost -t 'fridge/sensors' \
    -m '{"tempExt":4.3,"accX":9.6,"accY":0.1,"accZ":4.2,"gyroX":-0.1,"gyroY":-0.07,"gyroZ":0.01,"motorTemp":27.2,"noise":150}'
  sleep 2
  if ls "$REPO_DIR/server/data/"*.csv >/dev/null 2>&1; then
    echo "CSV escrito correctamente:"
    tail -2 "$REPO_DIR"/server/data/*.csv
    echo
    echo "OJO: esa fila es de prueba, no una medida. Bórrala del CSV antes"
    echo "de dar comienzo a la campaña, o anótalo en docs/EXPERIMENTOS.md."
  else
    die "no se escribió ningún CSV; mira 'journalctl -u tfm-logger -n 40'"
  fi
}

# ---------------------------------------------------------------------
fase_ap() {
  [[ -n "$AP_PASS" ]] || die "define AP_PASS antes de esta fase:
         sudo AP_PASS='una-clave-buena' ./provision-pi.sh ap
       Esa contraseña es lo único que impide que un tercero publique
       tramas falsas en los topics: no uses una trivial."
  (( ${#AP_PASS} >= 8 )) || die "WPA2 exige al menos 8 caracteres"

  log "Configurando '$AP_SSID' como punto de acceso en $AP_IFACE"
  echo "A partir de aquí se corta la conexión Wi-Fi actual."
  echo "Pulsa Ctrl+C en 10 segundos para abortar."
  sleep 10

  crear_ap
  nmcli connection up "$AP_SSID"

  log "Punto de acceso activo"
  echo "SSID:            $AP_SSID"
  echo "IP de la Pi:     ${AP_IP%/*}   <-- este valor va en MQTT_SERVER"
  echo "Banda:           2,4 GHz, canal 6"
  echo
  echo "Siguiente paso: pon ${AP_IP%/*} en device/secrets.h y reflashea el ESP32."
}

# Define la conexión del punto de acceso sin activarla.
crear_ap() {
  nmcli connection delete "$AP_SSID" 2>/dev/null || true
  nmcli connection add type wifi ifname "$AP_IFACE" con-name "$AP_SSID" \
    autoconnect yes ssid "$AP_SSID"
  nmcli connection modify "$AP_SSID" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel 6 \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.proto rsn \
    wifi-sec.pairwise ccmp \
    wifi-sec.psk "$AP_PASS" \
    ipv4.method shared \
    ipv4.addresses "$AP_IP" \
    ipv6.method disabled \
    connection.autoconnect-priority 999
  # banda bg y canal 6: el ESP32 solo opera en 2,4 GHz.
  #
  # autoconnect-priority alta y desactivación del resto de perfiles Wi-Fi:
  # wlan0 no puede ser cliente y punto de acceso a la vez, así que si la Pi
  # tiene guardada la red de la empresa competiría con el punto de acceso al
  # arrancar. Si ganase la red de empresa, el nodo se quedaría sin broker y
  # la campaña moriría en silencio.
  local otras
  otras=$(nmcli -t -f NAME,TYPE connection show 2>/dev/null \
          | awk -F: -v ap="$AP_SSID" '$2=="802-11-wireless" && $1!=ap {print $1}')
  if [[ -n "$otras" ]]; then
    echo "Desactivando el arranque automático de otros perfiles Wi-Fi:"
    while IFS= read -r c; do
      [[ -z "$c" ]] && continue
      nmcli connection modify "$c" connection.autoconnect no 2>/dev/null \
        && echo "  - $c (se conserva; reactivable con: nmcli connection modify '$c' connection.autoconnect yes)"
    done <<< "$otras"
  fi
}

# ---------------------------------------------------------------------
# Actualización tras cambiar el código. Se ejecuta en el concentrador,
# después de haber sincronizado los ficheros desde el equipo de desarrollo.
#
# Resuelve un problema que no es evidente: el registrador escribe la
# cabecera del CSV solo cuando crea el fichero, de modo que si se añaden
# columnas a mitad de jornada el fichero en curso conserva la cabecera
# antigua y los campos nuevos se descartan en silencio. Esta fase compara
# la cabecera real con la que corresponde al código actual y, si difieren,
# archiva el fichero y deja que el registrador lo cree de nuevo.
# ---------------------------------------------------------------------
fase_actualizar() {
  log "Actualizando el concentrador"
  [[ -f "$REPO_DIR/server/mqtt_logger.py" ]] || die "no encuentro $REPO_DIR/server/mqtt_logger.py"

  # El registrador no crea su directorio de datos: si se limpió con un
  # rm -rf demasiado amplio, el proceso aborta al primer mensaje.
  if [[ ! -d "$REPO_DIR/server/data" ]]; then
    echo "El directorio de datos no existe; se recrea."
    mkdir -p "$REPO_DIR/server/data"
    chown "$RUN_USER":"$RUN_USER" "$REPO_DIR/server/data"
  fi

  if [[ -x "$REPO_DIR/.venv/bin/pip" ]]; then
    echo "Revisando dependencias..."
    sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/server/requirements.txt" \
      && echo "  al día" \
      || echo "  AVISO: fallo al instalar. El punto de acceso suprime la salida a Internet."
  fi

  # --- Coherencia de la configuración del registrador ---------------
  # El intermediario reside en este mismo equipo, de modo que MQTT_HOST
  # solo puede ser localhost. Un valor distinto significa que el fichero
  # llegó del equipo de desarrollo: ocurrió al sincronizar sin excluir
  # server/.env, y el registrador quedó intentando resolver el nombre de
  # un intermediario público con el punto de acceso activo, que no tiene
  # salida a Internet. El prefijo de tema se toma de lo que el nodo
  # publica realmente, en lugar de suponerlo.
  local envf="$REPO_DIR/server/.env"
  local host_cfg pref_cfg pref_real
  host_cfg=$(grep -E '^MQTT_HOST=' "$envf" 2>/dev/null | cut -d= -f2- || true)
  pref_cfg=$(grep -E '^MQTT_TOPIC_PREFIX=' "$envf" 2>/dev/null | cut -d= -f2- || true)

  # Prefijo observado: se escucha el comodín y se mira qué llega.
  pref_real=$(timeout 6 mosquitto_sub -h localhost -t '#' -v -W 5 2>/dev/null \
              | grep -m1 'fridge/' | sed 's|fridge/.*||' || true)

  local recolocar=0
  [[ "$host_cfg" != "localhost" && "$host_cfg" != "127.0.0.1" ]] && recolocar=1
  [[ "$pref_cfg" != "$pref_real" ]] && recolocar=1

  if (( recolocar )); then
    log "La configuración del registrador no es coherente"
    echo "  MQTT_HOST configurado : '${host_cfg:-(vacío)}'   debe ser localhost"
    echo "  Prefijo configurado   : '${pref_cfg:-(vacío)}'"
    echo "  Prefijo que publica el nodo: '${pref_real:-(vacío)}'"
    echo
    echo "Se reescribe. El anterior queda en ${envf}.bak"
    cp -a "$envf" "${envf}.bak" 2>/dev/null || true
    cat > "$envf" <<ENVEOF
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_TOPIC_PREFIX=${pref_real}
MQTT_USER=
MQTT_PASSWORD=
DATA_DIR=$REPO_DIR/server/data
ENVEOF
    chown "$RUN_USER":"$RUN_USER" "$envf"
    chmod 600 "$envf"
  else
    echo "Configuración del registrador coherente (localhost, prefijo '${pref_cfg:-(vacío)}')."
  fi

  local rota
  rota=$("$REPO_DIR/.venv/bin/python" - "$REPO_DIR" <<'PYCHK'
import re, sys, glob, os
repo = sys.argv[1]
src = open(os.path.join(repo, 'server', 'mqtt_logger.py'), encoding='utf-8').read()

def campos(nombre):
    i = src.index(nombre)
    # [A-Za-z0-9_] y no solo minúsculas: tempExt, accX, motorTemp y el
    # resto del canal lento llevan mayúsculas. Con el patrón anterior la
    # cabecera esperada salía incompleta, el fichero se declaraba desfasado
    # en cada ejecución y se archivaba una y otra vez.
    return re.findall(r'"([A-Za-z0-9_]+)"', src[i:src.index(']', i)])

# Un canal por sufijo. Anadir un canal al registrador OBLIGA a anadirlo aqui:
# si no, sus ficheros se comparan contra la cabecera del canal lento, no cuadran
# y se ARCHIVAN. Ocurrio al aparecer -status.csv, y archivar es destructivo.
esperado = {
    '': ['ts'] + campos('SENSOR_FIELDS'),
    '-vibration': ['ts'] + campos('VIBRATION_FIELDS'),
    '-status': ['ts'] + campos('STATUS_FIELDS'),
}
# El canal lento no tiene sufijo propio, de modo que es el unico que hay que
# identificar por exclusion. La lista de sufijos a excluir se deriva de las
# claves y no se escribe a mano: asi un canal nuevo queda cubierto solo.
otros = [k for k in esperado if k]
for suf, cols in esperado.items():
    for f in sorted(glob.glob(os.path.join(repo, 'server', 'data', '*%s.csv' % suf))):
        base = os.path.basename(f)
        if suf == '' and any(o in base for o in otros):
            continue
        with open(f, encoding='utf-8') as fh:
            cab = fh.readline().strip().split(',')
        if cab != cols:
            # Se detalla la diferencia: archivar un fichero es destructivo,
            # así que la discrepancia debe quedar a la vista y no reducirse
            # a un recuento de columnas.
            falta = [c for c in cols if c not in cab]
            sobra = [c for c in cab if c not in cols]
            det = []
            if falta: det.append('faltan: ' + ','.join(falta[:6]))
            if sobra: det.append('sobran: ' + ','.join(sobra[:6]))
            if not det: det.append('mismo conjunto, distinto orden')
            print('%s\t%d\t%d\t%s' % (f, len(cab), len(cols), '; '.join(det)))
PYCHK
)

  if [[ -z "$rota" ]]; then
    echo
    echo "Las cabeceras de los CSV ya corresponden al código actual."
  else
    echo
    echo "Ficheros con cabecera desfasada:"
    printf '%s\n' "$rota" | while IFS=$'\t' read -r f tiene toca det; do
      [[ -n "$f" ]] && echo "  $(basename "$f"): $tiene columnas, corresponden $toca  ($det)"
    done
    echo
    echo "Se archivan para que el registrador los cree con la cabecera nueva."
    echo "Los datos NO se borran."

    # Detener antes de mover: un proceso conserva el acceso al fichero
    # movido y seguiría escribiendo en un destino invisible.
    systemctl stop tfm-logger 2>/dev/null || true
    local dest="$REPO_DIR/server/data/descartes-cabecera-$(date +%Y%m%d-%H%M)"
    mkdir -p "$dest"
    printf '%s\n' "$rota" | while IFS=$'\t' read -r f tiene toca det; do
      [[ -n "$f" ]] && mv "$f" "$dest"/ && echo "  archivado: $(basename "$f")"
    done
    chown -R "$RUN_USER":"$RUN_USER" "$dest"
  fi

  log "Reiniciando el registrador"
  # Se comprueba el fichero de la unidad y, como respaldo, que systemd la
  # conozca. 'systemctl list-unit-files' sin patrón no es fiable aquí: no
  # siempre lista la unidad en la forma esperada y daba un falso negativo
  # sobre un servicio que sí existía.
  if [[ ! -f /etc/systemd/system/tfm-logger.service ]] \
     && ! systemctl cat tfm-logger.service >/dev/null 2>&1; then
    die "el servicio tfm-logger no existe en este equipo. Este concentrador no
       se ha aprovisionado todavía; ejecuta primero:
         sudo AP_PASS='<clave>' $0 todo
       o, si el punto de acceso ya está montado, solo la fase del registrador:
         sudo $0 logger"
  fi

  systemctl restart tfm-logger 2>/dev/null || true
  sleep 3
  if systemctl is-active --quiet tfm-logger; then
    echo "tfm-logger activo"
  else
    # Mostrar el motivo aquí mismo: pedir que se ejecute otro comando
    # obliga a una vuelta más y el error ya está disponible.
    log "El registrador NO arrancó. Motivo"
    systemctl status tfm-logger --no-pager -n 0 2>&1 | sed -n '1,6p' || true
    echo
    journalctl -u tfm-logger -n 25 --no-pager 2>&1 | tail -25 || true
    echo
    echo "Comprobaciones habituales:"
    echo "  - ¿existe el directorio de datos?   ls -la $REPO_DIR/server/data"
    echo "  - ¿existe la configuración?         ls -la $REPO_DIR/server/.env"
    echo "  - ¿el intérprete del entorno?       ls -la $REPO_DIR/.venv/bin/python"
    echo "  - ¿el usuario de la unidad existe?  grep User= /etc/systemd/system/tfm-logger.service"
    die "revisa el detalle de arriba."
  fi

  echo
  echo "Comprueba la cadena con:  $0 comprobar"
}

# ---------------------------------------------------------------------
# Comprobación de la cadena completa, eslabón por eslabón. Se ejecuta en la
# Pi y no necesita privilegios. Recorre el camino del dato en el mismo orden
# en que fluye, de forma que el primer fallo señala dónde se corta.
# ---------------------------------------------------------------------
fase_comprobar() {
  local fallos=0
  ko() { printf '  \033[31mFALLO\033[0m  %s\n' "$*"; fallos=$((fallos+1)); }
  ok() { printf '  \033[32mOK\033[0m     %s\n' "$*"; }
  av() { printf '  AVISO  %s\n' "$*"; }

  log "1. Punto de acceso"
  if nmcli -t -f NAME,DEVICE,STATE connection show --active 2>/dev/null | grep -q "^$AP_SSID:"; then
    ok "'$AP_SSID' activo en $AP_IFACE"
    local ip
    ip=$(ip -4 -brief address show "$AP_IFACE" 2>/dev/null | awk '{print $3}')
    [[ "$ip" == "$AP_IP" ]] && ok "dirección $ip" || av "dirección $ip (se esperaba $AP_IP)"
  else
    ko "'$AP_SSID' no está activo. El nodo no tiene a qué conectarse.
         Mira: nmcli connection show; nmcli device status"
  fi

  log "2. Nodo asociado a la red"
  local macs
  macs=$(iw dev "$AP_IFACE" station dump 2>/dev/null | grep -c '^Station' || true)
  if (( macs > 0 )); then
    ok "$macs equipo(s) asociado(s)"
    iw dev "$AP_IFACE" station dump 2>/dev/null | awk '/^Station/{print "         "$2}'
    ip neigh show dev "$AP_IFACE" 2>/dev/null | awk '{print "         "$1" -> "$5}'
  else
    ko "ningún equipo asociado. El ESP32 no ha entrado en la red.
         Revisa en el monitor serie si conecta al Wi-Fi, y que WIFI_SSID y
         WIFI_PASSWORD de secrets.h coincidan con '$AP_SSID'."
  fi

  log "3. Broker"
  if systemctl is-active --quiet mosquitto; then
    ok "mosquitto activo"
    if ss -lnt 2>/dev/null | grep -qE '(0\.0\.0\.0|\*):1883'; then
      ok "escucha en el 1883 abierto a la red"
    else
      ko "el 1883 no escucha en todas las interfaces; el nodo no podrá conectar"
    fi
  else
    ko "mosquitto no está activo: systemctl status mosquitto"
  fi

  log "4. Tramas en vivo (hasta 40 s: la ráfaga sale cada 30 s)"
  local lenta rafaga
  lenta=$(timeout 5 mosquitto_sub -h localhost -t "${MQTT_PREFIX:-}fridge/sensors" -C 1 2>/dev/null || true)
  if [[ -n "$lenta" ]]; then ok "canal lento recibido"; echo "         $lenta"
  else ko "no llega el canal lento (debería a 1 Hz)"; fi

  rafaga=$(timeout 40 mosquitto_sub -h localhost -t "${MQTT_PREFIX:-}fridge/vibration" -C 1 2>/dev/null || true)
  if [[ -n "$rafaga" ]]; then ok "canal de ráfaga recibido"
  else ko "no llega ninguna ráfaga en 40 s"; fi

  # El veredicto del detector embarcado. Se distingue de los otros dos: puede no
  # llegar porque el firmware de la placa sea anterior al detector, y eso no es
  # un fallo del concentrador. Se declara como aviso y se dice cual es la causa.
  local estado
  estado=$(timeout 40 mosquitto_sub -h localhost -t "${MQTT_PREFIX:-}fridge/status" -C 1 2>/dev/null || true)
  if [[ -n "$estado" ]]; then
    ok "veredicto del detector recibido"
    echo "         $estado"
  else
    av "no llega ningún veredicto en 40 s. Si el nodo aún tiene un firmware
         anterior al detector embarcado, es lo esperado: flashéalo con
         arduino-cli. Si ya lo tiene, revisa el monitor serie."
  fi

  log "5. El registrador conoce los tres canales"
  # Esta comprobacion existe porque el fallo que evita es SILENCIOSO: si el
  # registrador no esta suscrito a un topic, el nodo publica y el dato se pierde
  # sin que nada proteste. Ocurrio con fridge/status.
  local lg="$REPO_DIR/server/mqtt_logger.py"
  if [[ -f "$lg" ]]; then
    local faltan=0
    for t in fridge/sensors fridge/vibration fridge/status; do
      if grep -q "\"$t\"" "$lg"; then ok "suscrito a $t"
      else ko "el registrador NO conoce $t: los mensajes se perderían en silencio"; faltan=1; fi
    done
    if (( faltan == 0 )); then
      # Y que el codigo en la Pi sea el que se acaba de sincronizar, no uno
      # anterior con el mismo nombre de fichero.
      local sha
      sha=$(sha256sum "$lg" 2>/dev/null | cut -c1-12)
      ok "mqtt_logger.py sha256:$sha (compáralo con el del portátil)"
    fi
  else
    ko "no encuentro $lg"
  fi

  log "6. Logger y ficheros"
  if systemctl is-active --quiet tfm-logger; then ok "tfm-logger activo"
  else ko "tfm-logger parado: journalctl -u tfm-logger -n 40"; fi

  if compgen -G "$REPO_DIR/server/data/*.csv" >/dev/null; then
    local antes despues
    antes=$(cat "$REPO_DIR"/server/data/*.csv 2>/dev/null | wc -l)
    ok "ficheros presentes:"
    wc -l "$REPO_DIR"/server/data/*.csv | sed 's/^/         /'
    echo "         comprobando crecimiento (5 s)..."
    sleep 5
    despues=$(cat "$REPO_DIR"/server/data/*.csv 2>/dev/null | wc -l)
    if (( despues > antes )); then ok "el CSV crece ($((despues-antes)) filas en 5 s)"
    else ko "el CSV no crece: llegan tramas pero no se escriben"; fi
  else
    ko "no hay ningún CSV en $REPO_DIR/server/data/"
  fi

  log "7. Calidad del dato"
  if [[ -n "$rafaga" ]]; then
    printf '%s' "$rafaga" | python3 -c '
import json, sys
d = json.load(sys.stdin)
def linea(estado, txt): print(f"  {estado}  {txt}")
mc = d.get("ms_capture", 0)
linea("OK    " if abs(mc-1024) <= 5 else "FALLO ",
      f"ms_capture = {mc} ms (nominal 1024): la cadencia "
      + ("se sostiene" if abs(mc-1024) <= 5 else "NO se sostiene, el eje de frecuencias queda falseado"))
r, tr = d.get("retries", 0), d.get("total_retries", 0)
linea("OK    " if r <= 2 else "AVISO ",
      f"retries = {r} en esta ráfaga, {tr} acumulados"
      + ("" if r <= 2 else "  <- el bus falla a menudo; conviene soldar antes de las 24 h"))
linea("OK    " if d.get("failed_bursts",0)==0 else "AVISO ",
      f"failed_bursts = {d.get("failed_bursts")}, bad_frames = {d.get("bad_frames")}")
for eje in "xyz":
    k, rms = d.get(f"kurt_{eje}",0), d.get(f"rms_{eje}",0)
    est = "OK    " if 1.4 <= k <= 5 else "AVISO "
    nota = "" if 1.4 <= k <= 5 else "  <- impulsividad anómala; si es en reposo, sospecha del bus"
    linea(est, f"eje {eje.upper()}: rms = {rms:.4f} m/s2, kurtosis = {k:.2f}{nota}")
print()
print("  Recuerda: rms con el compresor EN MARCHA debe estar claramente por")
print("  encima de 1 m/s2. Si no sube, el sensor mide su soporte y no el motor.")
' 2>/dev/null || av "no se pudo analizar la ráfaga"
  else
    av "sin ráfaga que analizar"
  fi

  echo
  if (( fallos == 0 )); then
    log "Todo correcto: la cadena funciona de extremo a extremo"
    echo "Ya puedes dejarlo corriendo. Registra la campaña en docs/EXPERIMENTOS.md."
  else
    log "$fallos comprobación(es) fallida(s)"
    echo "El primer FALLO de la lista marca dónde se corta la cadena."
  fi
}

# ---------------------------------------------------------------------
# Aprovisionamiento completo en un solo paso.
#
# Todas las comprobaciones se hacen ANTES de tocar nada: si falta algo es
# mejor abortar sin haber cambiado el sistema que dejarlo a medias. El
# punto de acceso se activa al final y de forma desacoplada, porque en ese
# instante se corta la red por la que llega esta sesión.
# ---------------------------------------------------------------------
fase_todo() {
  log "Comprobaciones previas"

  [[ -n "$AP_PASS" ]] || die "falta la contraseña del punto de acceso:
         sudo AP_PASS='una-clave-buena' ./provision-pi.sh todo
       Es lo único que impide que un tercero publique tramas falsas en los
       topics y contamine el dataset."
  (( ${#AP_PASS} >= 8 )) || die "WPA2 exige al menos 8 caracteres"
  id "$RUN_USER" >/dev/null 2>&1 || die "el usuario detectado '$RUN_USER' no existe.
       Se deduce de SUDO_USER o del propietario de $REPO_DIR. Puedes forzarlo:
         sudo RUN_USER=<usuario> AP_PASS='...' ./provision-pi.sh todo"
  [[ -f "$REPO_DIR/server/mqtt_logger.py" ]] || die "no encuentro $REPO_DIR/server/mqtt_logger.py.
       Copia el repositorio a la Pi antes de ejecutar esto, desde el Mac:
         rsync -av --exclude .venv <ruta-local>/TFM/ $RUN_USER@<ip-pi>:$REPO_DIR/"
  [[ -f "$REPO_DIR/server/requirements.txt" ]] || die "falta $REPO_DIR/server/requirements.txt"
  ping -c1 -W3 deb.debian.org >/dev/null 2>&1 || die "sin salida a Internet.
       Las dependencias se instalan antes de levantar el punto de acceso, así
       que hace falta conectividad ahora. Conecta el cable o la Wi-Fi."
  echo "Todo en orden."

  diagnostico

  log "Resumen de lo que va a ocurrir"
  cat <<EOF
  1. Instalar mosquitto y el entorno Python
  2. Configurar el broker en el puerto 1883
  3. Dejar el logger como servicio systemd (arranca solo, se reinicia solo)
  4. Probar la cadena completa con una trama sintética
  5. Convertir $AP_IFACE en punto de acceso '$AP_SSID' (${AP_IP%/*})

  El paso 5 corta la Wi-Fi actual. Si has entrado por SSH sobre Wi-Fi,
  perderás esta sesión: se lanza desacoplado para que termine igual.
  El informe queda en $RUN_HOME/tfm-hub-info.txt

EOF
  echo "Pulsa Ctrl+C en 15 segundos para abortar."
  sleep 15

  fase_paquetes
  fase_broker
  fase_logger
  escribir_informe
  fase_ap_desacoplado
}

# ---------------------------------------------------------------------
escribir_informe() {
  local f="$RUN_HOME/tfm-hub-info.txt"
  cat > "$f" <<EOF
Hub del TFM — datos de acceso
=============================
Generado por server/provision-pi.sh

Red del punto de acceso
  SSID:          $AP_SSID
  Banda:         2,4 GHz, canal 6 (el ESP32 no admite 5 GHz)
  IP de la Pi:   ${AP_IP%/*}
  DHCP:          lo sirve NetworkManager en 10.42.0.0/24

En device/secrets.h del nodo
  #define WIFI_SSID     "$AP_SSID"
  #define WIFI_PASSWORD "<la que pasaste en AP_PASS>"
  #define MQTT_SERVER   "${AP_IP%/*}"
  #define MQTT_PORT     1883
  #define MQTT_TOPIC_PREFIX ""
  (requiere reflashear el ESP32 una vez; después la IP ya no cambia)

Acceso desde el portátil
  1. Unirse a la red Wi-Fi '$AP_SSID'
  2. ssh $RUN_USER@${AP_IP%/*}

Vigilar la campaña
  sudo $REPO_DIR/server/provision-pi.sh estado
  journalctl -u tfm-logger -f
  mosquitto_sub -h localhost -t 'fridge/#' -v
  wc -l $REPO_DIR/server/data/*.csv

Tras un corte de corriente
  Todo vuelve solo, sin intervención:
    - NetworkManager levanta el punto de acceso '$AP_SSID' (autoconnect)
    - mosquitto arranca por systemd (enabled)
    - tfm-logger arranca por systemd (enabled) y continúa el CSV del día
  Se pierden únicamente los datos del intervalo sin corriente.

Marcha atrás
  sudo $REPO_DIR/server/provision-pi.sh revertir
EOF
  chown "$RUN_USER":"$RUN_USER" "$f"
  log "Informe escrito en $f"
  cat "$f"
}

# ---------------------------------------------------------------------
fase_ap_desacoplado() {
  log "Activando el punto de acceso"
  crear_ap
  # systemd-run despega la activación de esta sesión: cuando la red se
  # corte, el proceso sigue vivo bajo systemd y termina el trabajo.
  systemd-run --unit=tfm-ap-up --collect \
    /bin/bash -c "sleep 3; nmcli connection up '$AP_SSID'" >/dev/null 2>&1 \
    || nmcli connection up "$AP_SSID" &
  echo
  echo "Lanzado. Esta sesión va a caer en unos segundos."
  echo "Reconecta uniéndote a '$AP_SSID' y luego:  ssh $RUN_USER@${AP_IP%/*}"
  echo "Si algo falla, necesitarás cable o teclado y monitor."
}

# ---------------------------------------------------------------------
# Deshace los cambios. Pensado para un equipo compartido: devuelve wlan0
# a modo cliente y detiene el logger, sin borrar los datos capturados.
# ---------------------------------------------------------------------
fase_revertir() {
  log "Revirtiendo la configuración"

  if nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$AP_SSID"; then
    echo "Eliminando el punto de acceso '$AP_SSID'..."
    nmcli connection down "$AP_SSID" 2>/dev/null || true
    nmcli connection delete "$AP_SSID" 2>/dev/null || true
    echo "wlan0 vuelve a modo cliente."
    # Se devuelve el arranque automático a los perfiles que se desactivaron
    # al crear el punto de acceso: si no, la Pi quedaría sin conectarse a
    # ninguna red al reiniciar.
    local otras
    otras=$(nmcli -t -f NAME,TYPE connection show 2>/dev/null \
            | awk -F: -v ap="$AP_SSID" '$2=="802-11-wireless" && $1!=ap {print $1}')
    if [[ -n "$otras" ]]; then
      echo "Reactivando el arranque automático de:"
      while IFS= read -r c; do
        [[ -z "$c" ]] && continue
        nmcli connection modify "$c" connection.autoconnect yes 2>/dev/null && echo "  - $c"
      done <<< "$otras"
    fi
    echo "Si hace falta, conecta a mano con:"
    echo "  sudo nmcli device wifi connect '<SSID>' password '<clave>'"
  else
    echo "No hay punto de acceso configurado."
  fi

  if systemctl list-unit-files 2>/dev/null | grep -q '^tfm-logger'; then
    echo "Deteniendo el logger..."
    systemctl disable --now tfm-logger 2>/dev/null || true
  fi

  echo
  echo "NO se han tocado los CSV de $REPO_DIR/server/data/ ni la"
  echo "configuración de Mosquitto. Para retirar el broker del arranque:"
  echo "  sudo rm /etc/mosquitto/conf.d/tfm.conf && sudo systemctl restart mosquitto"
}

# ---------------------------------------------------------------------
case "${1:-}" in
  paquetes) need_root paquetes; diagnostico; fase_paquetes ;;
  broker)   need_root broker;   fase_broker ;;
  logger)   need_root logger;   fase_logger ;;
  ap)       need_root ap;       diagnostico; fase_ap ;;
  revertir) need_root revertir; fase_revertir ;;
  todo)     need_root todo;     fase_todo ;;
  actualizar) need_root actualizar; fase_actualizar ;;
  comprobar) fase_comprobar ;;
  estado)   diagnostico
            log "Servicios"
            systemctl is-active mosquitto tfm-logger || true
            log "Datos"
            ls -la "$REPO_DIR/server/data/" 2>/dev/null || echo "sin directorio de datos"
            wc -l "$REPO_DIR"/server/data/*.csv 2>/dev/null || echo "sin CSV todavía"
            log "Clientes conectados al punto de acceso"
            ip neigh show dev "$AP_IFACE" 2>/dev/null || true ;;
  *) sed -n '3,29p' "$0" | sed 's|^# *||'
     echo "Todo de una vez:  sudo AP_PASS='clave' $0 todo"
     echo "Tras cambiar codigo: sudo $0 actualizar"
     echo "Comprobar todo:   $0 comprobar"
     echo "Fases sueltas:    paquetes | broker | logger | ap | estado | revertir" ;;
esac

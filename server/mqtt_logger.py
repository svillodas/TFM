#!/usr/bin/env python3
"""Data logger MQTT -> CSV para el nodo de mantenimiento predictivo.

Se suscribe a los topics de telemetria del ESP32 y vuelca cada trama JSON a un
CSV diario (un fichero por dia natural y por canal). Disenado para ejecutarse
durante dias sin supervision en la Raspberry Pi: cualquier trama malformada se
descarta y se registra, pero nunca detiene el proceso. Los datos crudos no son
reproducibles.

El nodo publica en dos canales con cadencias distintas:

    fridge/sensors     1 Hz. Nueve variables instantaneas.
                       -> server/data/YYYY-MM-DD.csv
    fridge/vibration   Cada 30 s. Caracteristicas espectrales y temporales
                       calculadas en el nodo sobre una rafaga a 1 kHz.
                       -> server/data/YYYY-MM-DD-vibration.csv
                       -> server/data/YYYY-MM-DD-status.csv

Uso:
    cp server/.env.example server/.env   # ajustar host del broker
    python server/mqtt_logger.py
"""

from __future__ import annotations

import csv
import json
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# Orden fijo de columnas por canal. Debe coincidir con docs/DATA_SCHEMA.md y con
# los nombres de campo que publica device/device.ino. Anadir un campo aqui sin
# anadirlo alli (o al contrario) deja columnas vacias en silencio.
SENSOR_FIELDS = [
    "tempExt",
    "accX", "accY", "accZ",
    "gyroX", "gyroY", "gyroZ",
    "motorTemp",
    "noise",
]

VIBRATION_FIELDS = [
    "vib_fs", "vib_n", "ms_capture", "ms_total",
    "failed_bursts", "bad_frames", "retries", "total_retries",
    "cont_rejects", "total_cont_rejects",
    "unpublished_bursts",
    "rms_x", "rms_y", "rms_z",
    "peak_x", "peak_y", "peak_z",
    "kurt_x", "kurt_y", "kurt_z",
    "fdom_x", "fdom_y", "fdom_z",
    "adom_x", "adom_y", "adom_z",
    "f2_x", "f2_y", "f2_z", "a2_x", "a2_y", "a2_z",
    "f3_x", "f3_y", "f3_z", "a3_x", "a3_y", "a3_z",
    "aud_fs", "aud_n", "aud_rms",
    "aud_b0", "aud_b1", "aud_b2", "aud_b3",
]

# Veredicto del detector embarcado. Es el canal que materializa el objetivo del
# TFM: el diagnostico lo emite el nodo, no el concentrador.
#
#   health        nominal | anomaly | not_evaluable
#                 El tercero NO es un estado de salud intermedio: es la
#                 declaracion de que la medida no sirve para decidir, porque los
#                 reintentos del bus fabrican la firma del fallo sobre un activo
#                 sano, o porque el compresor esta detenido.
#   streak        rafagas anomalas consecutivas acumuladas
#   notify        1 solo en la transicion a estado notificable, para no
#                 republicar la misma alarma en cada rafaga
#   lof, env      puntuaciones de los dos modelos. Se registran AMBAS: su
#                 discrepancia es diagnosticable a posteriori, y con una sola no
#   n_peaks       picos espectrales significativos. Dice QUE clase de desviacion
#                 hay y no solo que la hay
#   us_inference  microsegundos de inferencia en el nodo. Es la medida que
#                 respalda la afirmacion de que el diagnostico cabe en el borde
STATUS_FIELDS = [
    "health", "streak", "notify",
    "lof", "env", "n_peaks",
    "us_inference",
]

# topic -> (sufijo del fichero, columnas). El sufijo vacio deja el canal lento
# en el nombre corto YYYY-MM-DD.csv, que es el fichero principal del dataset.
CHANNELS = {
    "fridge/sensors": ("", SENSOR_FIELDS),
    "fridge/vibration": ("-vibration", VIBRATION_FIELDS),
    "fridge/status": ("-status", STATUS_FIELDS),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("logger-mqtt")


class DailyCsvLogger:
    """Escribe filas en un CSV por dia y canal, rotando al cruzar la medianoche."""

    def __init__(self, directory: Path, suffix: str, fields: list[str]) -> None:
        self.directory = directory
        self.suffix = suffix
        self.fields = fields
        self.header = ["ts"] + fields
        self.directory.mkdir(parents=True, exist_ok=True)
        self._date: str | None = None
        self._file = None
        self._writer: csv.writer | None = None
        self.rows = 0
        self.discarded = 0

    def _ensure_file(self, date: str) -> None:
        if date == self._date:
            return
        self.close()
        path = self.directory / f"{date}{self.suffix}.csv"
        # Se comprueba tambien el tamano: un fichero creado a mano con touch
        # o abierto y nunca escrito existe pero esta vacio, y sin esto se
        # quedaria sin cabecera, dejando el CSV inservible para el analisis.
        is_new = not path.exists() or path.stat().st_size == 0
        # newline="" evita lineas en blanco extra en el CSV.
        self._file = path.open("a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if is_new:
            self._writer.writerow(self.header)
        self._date = date
        log.info("Escribiendo en %s", path)

    def write(self, data: dict) -> None:
        now = datetime.now().astimezone()
        self._ensure_file(now.strftime("%Y-%m-%d"))
        # Los campos ausentes quedan vacios en lugar de a cero: un cero es una
        # medida valida y confundirlo con "sin dato" contamina el dataset.
        row = [now.isoformat(timespec="milliseconds")]
        row += [data.get(f, "") for f in self.fields]
        self._writer.writerow(row)
        self._file.flush()  # perdida de datos > coste de I/O a 1 Hz
        self.rows += 1
        if self.rows % 60 == 0:
            log.info("%s: %d filas registradas (%d descartadas)",
                     self.suffix or "sensors", self.rows, self.discarded)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
            self._writer = None


def on_connect(client, userdata, flags, reason_code, properties=None) -> None:
    if reason_code == 0:
        for topic in userdata["loggers"]:
            client.subscribe(topic, qos=0)
            log.info("Suscrito a '%s'", topic)
    else:
        log.error("Fallo de conexion al broker: %s", reason_code)


def on_disconnect(client, userdata, flags, reason_code, properties=None) -> None:
    # reconnect_delay_set() gestiona el reintento; aqui solo se informa.
    if reason_code != 0:
        log.warning("Desconexion inesperada (%s). Reintentando...", reason_code)


def on_message(client, userdata, message) -> None:
    logger = userdata["loggers"].get(message.topic)
    if logger is None:
        log.warning("Trama en topic no registrado '%s', ignorada", message.topic)
        return
    try:
        data = json.loads(message.payload.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("el payload no es un objeto JSON")
        logger.write(data)
    except Exception as exc:  # noqa: BLE001 - el logger no debe caerse nunca
        logger.discarded += 1
        log.warning("Trama descartada de '%s' (%s): %r",
                    message.topic, exc, message.payload[:120])


def main() -> int:
    load_dotenv(Path(__file__).parent / ".env")

    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    user = os.getenv("MQTT_USER") or None
    password = os.getenv("MQTT_PASSWORD") or None
    directory = Path(os.getenv("DATA_DIR", "server/data"))

    # Prefijo opcional de topic. Solo hace falta al probar contra un broker
    # publico, donde "fridge/..." es demasiado generico y se cruzaria con
    # otros usuarios. Debe coincidir con el que use el nodo en secrets.h
    # (MQTT_TOPIC_PREFIX, con la barra final incluida).
    prefix = os.getenv("MQTT_TOPIC_PREFIX", "").strip().strip("/")
    if prefix:
        log.info("Prefijo de topic activo: '%s/'", prefix)

    loggers = {
        (f"{prefix}/{topic}" if prefix else topic):
            DailyCsvLogger(directory, suffix, fields)
        for topic, (suffix, fields) in CHANNELS.items()
    }
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="hub-logger",
        userdata={"loggers": loggers},
    )
    if user:
        client.username_pw_set(user, password)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def stop(signum, frame) -> None:
        total = sum(l.rows for l in loggers.values())
        discarded = sum(l.discarded for l in loggers.values())
        log.info("Senal recibida, cerrando. Total: %d filas, %d descartadas",
                 total, discarded)
        client.disconnect()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    log.info("Conectando a %s:%d ...", host, port)
    try:
        client.connect(host, port, keepalive=60)
    except OSError as exc:
        log.error("No se pudo alcanzar el broker en %s:%d (%s). "
                  "Comprueba que Mosquitto esta arrancado.", host, port, exc)
        return 1

    try:
        client.loop_forever()
    finally:
        for l in loggers.values():
            l.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

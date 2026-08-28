# 🧊 Sistema IoT Edge de Mantenimiento Predictivo para Compresores

Nodo *edge* basado en ESP32 que captura la **firma física** (vibración, temperatura y
acústica) de un motor compresor de refrigeración. Los datos viajan por Wi-Fi mediante MQTT
hacia un hub local (Raspberry Pi) que construye los datasets para entrenar modelos de
Machine Learning orientados a **detección temprana de anomalías**.

> Trabajo Fin de Máster — Máster Universitario en Internet das Cousas (MUIoT), UDC.
> Curso 2025/2026. Autor: Sergio Villodas Zapata. Tutor: Tiago M. Fernández Caramés.

El planteamiento clave es que el diagnóstico ocurre **en el borde de la red**: el objetivo
final es que el nodo decida por sí mismo si el activo se desvía de su comportamiento
nominal, sin enviar un flujo masivo de datos a la nube.

## 🧱 Arquitectura

```
┌──────────────────────────┐         ┌──────────────────────────────┐
│  Nodo Edge (ESP32)       │         │  Hub local (Raspberry Pi)    │
│                          │  MQTT   │                              │
│  MPU-6050  (I2C)         │ ──────► │  Mosquitto (broker :1883)    │
│  DS18B20   (1-Wire)      │  Wi-Fi  │  mqtt_logger.py → CSV diario │
│  INMP441   (I2S)         │         │  Entrenamiento ML (offline)  │
│  ↳ payload JSON 9 vars   │ ◄────── │  ↳ modelo/umbral desplegado  │
└──────────────────────────┘         └──────────────────────────────┘
```

Detalle y decisiones de diseño: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 🛠️ Hardware Utilizado

- **DFRobot FireBeetle 2 ESP32-S3:** placa de desarrollo principal (nodo de cómputo y
  radio). 16 MB de flash y PSRAM OPI. Ojo: su pinout **no** coincide con el del ESP32
  clásico (en el ESP32-S3 no existen los GPIO 22–25 y los GPIO 33–37 los consume la PSRAM
  octal).
- **MPU-6050 (I2C):** acelerómetro y giroscopio de 6 ejes. Mide la vibración anómala del
  chasis y aporta una temperatura superficial próxima al motor.
- **DS18B20 (1-Wire):** sonda de temperatura con recubrimiento de acero. Monitorización
  térmica del entorno/tuberías.
- **INMP441 (I2S):** micrófono digital omnidireccional; extrae la firma acústica del motor
  sin interferencia electromagnética.

## 🔌 Esquema de Conexiones (Pinout)

Placa de referencia: **FireBeetle 2 ESP32-S3**. La columna «Serigrafía» es la etiqueta
impresa en la placa; la columna «GPIO» es el número que aparece en el firmware.

| Componente | Pin Sensor | GPIO | Serigrafía | Notas Adicionales |
| :--- | :--- | :--- | :--- | :--- |
| **Varios** | VCC / VDD | — | 3V3 | Alimentación común |
| **Varios** | GND | — | GND | Tierra común |
| **MPU-6050** | SDA | GPIO 1 | SDA | Bus I2C (por omisión de la placa) |
| **MPU-6050** | SCL | GPIO 2 | SCL | Bus I2C (por omisión de la placa) |
| **DS18B20** | DATA | GPIO 14 | D10 | Bus 1-Wire. Requiere pull-up de ~5 kΩ hacia 3V3. |
| **INMP441** | WS | GPIO 12 | D12 | Selección de canal (I2S) |
| **INMP441** | SD | GPIO 13 | D11 | Datos de audio (I2S) |
| **INMP441** | SCK | GPIO 17 | SCK | Reloj (I2S) |
| **INMP441** | L/R | — | GND | A tierra para canal izquierdo |

> ⚠️ Este pinout es específico del ESP32-S3. El GPIO21/GPIO22 habitual del ESP32 clásico
> **no sirve aquí**: el GPIO22 no existe en el S3 y el GPIO21 es el LED integrado (D13).
> Los pines I2C se declaran de forma explícita en [device/device.ino](device/device.ino)
> (`I2C_SDA`, `I2C_SCL`) para no depender del fichero de variante.

> ⚠️ Pines de *strapping* del ESP32-S3: GPIO0, GPIO3, GPIO45 y GPIO46. Ninguno se usa en
> este montaje. Los GPIO 33–37 están reservados por la PSRAM octal de esta placa y no
> deben cablearse.

## 📦 Dependencias de Software

**Firmware (Arduino IDE / arduino-cli)** — instalar desde el Gestor de Librerías:
- `Adafruit MPU6050` (+ `Adafruit Unified Sensor`, `Adafruit BusIO`)
- `OneWire` (Paul Stoffregen)
- `DallasTemperature` (Miles Burton)
- `PubSubClient` (Nick O'Leary)

**Hub (Raspberry Pi / Python 3.11+)**: ver [server/requirements.txt](server/requirements.txt).

## 🚀 Puesta en marcha

### 1. Nodo ESP32
```bash
cp device/secrets.h.example device/secrets.h   # rellenar SSID, password e IP del broker

# FQBN de la FireBeetle 2 ESP32-S3 (16 MB de flash, PSRAM octal)
FQBN='esp32:esp32:dfrobot_firebeetle2_esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB'
arduino-cli board list                         # localizar el puerto (/dev/cu.usbmodem*)
arduino-cli compile --fqbn "$FQBN" device/
arduino-cli upload  --fqbn "$FQBN" -p /dev/cu.usbmodem101 device/
arduino-cli monitor -p /dev/cu.usbmodem101 -c baudrate=115200
```
Con `CDCOnBoot` activado el puerto serie es el USB nativo del S3, por lo que enumera como
`/dev/cu.usbmodem*` (no `/dev/cu.usbserial-*`, que corresponde a placas con convertidor
CH340/CP210x) y su nombre cambia entre reinicios: comprobarlo con `arduino-cli board list`.
`device/secrets.h` está en `.gitignore`: las credenciales no se versionan.

### 2. Broker MQTT en la Raspberry Pi
```bash
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
mosquitto_sub -h localhost -t 'fridge/#' -v      # verificar que llegan tramas
```

### 3. Data logger
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
cp server/.env.example server/.env               # ajustar host del broker
python server/mqtt_logger.py
```
Genera un CSV por día en `server/data/YYYY-MM-DD.csv`.

## 📊 Formato de datos

El nodo publica en **dos canales** con cadencias distintas.

**Canal lento** — `fridge/sensors`, 9 variables instantáneas cada segundo:

```json
{"tempExt":4.31,"accX":0.12,"accY":-0.05,"accZ":9.79,
 "gyroX":0.01,"gyroY":0.00,"gyroZ":-0.02,"motorTemp":38.6,"noise":142}
```

**Canal de ráfaga** — `fridge/vibration`, cada 30 s, características calculadas en el nodo
a partir de 1024 muestras a 1 kHz:

```json
{"vib_fs":1000,"vib_n":1024,"ms_capture":1031,"rms_z":1.4127,
 "kurt_z":1.502,"fdom_z":48.02,"adom_z":1.9685,"aud_b2":0.7510, ...}
```

Por qué dos canales: para observar una vibración de frecuencia *f* hay que muestrear por
encima de 2*f* (Nyquist). El compresor vibra en torno a los 48 Hz (2900 RPM), así que a 1 Hz
la señal se pliega (*aliasing*) y no admite análisis frecuencial. La ráfaga a 1 kHz sí lo
permite —resolución de 0,98 Hz, banda hasta 500 Hz—, y las características se extraen en el
propio nodo porque transmitir 3000 valores por segundo sería insostenible. El canal lento se
mantiene sin cambios para que los datos ya capturados sigan siendo comparables.

Unidades, rangos y valores centinela: [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md).

### Verificación del procesado de señal

La extracción de características vive en [device/signal_processing.h](device/signal_processing.h), deliberadamente sin
dependencias de Arduino para poder comprobarla en el PC frente a señales de propiedades
conocidas analíticamente:

```bash
g++ -std=c++11 -O2 -o /tmp/test_signal device/test/test_signal_processing.cpp && /tmp/test_signal
```

27 pruebas: frecuencia y amplitud dominantes, RMS, kurtosis de seno y de impulsos, casos
degenerados, energía por bandas, recuperación de tres picos espectrales, efecto del filtro
paso bajo y una demostración del aliasing que motivó el diseño.

## 🗺️ Estado y planificación

Fase actual: **Fase 4, motor de análisis**. La cadena de adquisición está cerrada y el
pipeline de detección está cerrado y validado por episodios.

El análisis vive en [server/analisis/](server/analisis/) — su
[README](server/analisis/README.md) documenta cada decisión y por qué. La auditoría de las
decisiones, incluidos los cuatro defectos de método que se detectaron y corrigieron, está en
[el cuaderno](server/analisis/cuadernos/auditoria-fase4.ipynb) y en
[el informe](docs/informes/2026-08-27-auditoria-metodologica-fase4.md).
Plan completo de fases y horas: [docs/ROADMAP.md](docs/ROADMAP.md).
Registro de campañas de medida: [docs/EXPERIMENTOS.md](docs/EXPERIMENTOS.md).
Informes de avance: [docs/informes/](docs/informes/).

## 📄 Memoria del TFM

El documento entregable vive en [memoria_TFM/](memoria_TFM/), sobre la plantilla oficial
del MUIoT. El contenido está dividido por capítulos siguiendo la estructura obligatoria de
la guía (introducción, estado del arte, objetivos, metodología, diseño, resultados,
conclusiones, bibliografía y anexos).

```bash
bash memoria_TFM/compilar.sh              # genera memoria_TFM/memoria_TFM.pdf
grep -rn '% TODO' memoria_TFM/capitulos/  # qué queda por redactar y qué dato necesita
```

Requiere XeLaTeX o tectonic: la plantilla usa `fontspec` y `pdflatex` no sirve.

Las reglas de formato, estilo y estructura están destiladas en
[docs/normativa/GUIA_MEMORIA.md](docs/normativa/GUIA_MEMORIA.md); los PDF oficiales
(solicitud de tema y guía de la memoria) están en [docs/normativa/](docs/normativa/).

No se modifican `tfm-muiot.sty`, `IEEEtran.bst`, `logo_*.pdf` ni `portada_TFM.pdf`: son
plantilla oficial y hay copia intacta en `memoria_TFM/plantilla/`.

## 📐 Convenciones del proyecto

Las directrices de código, las trampas conocidas del análisis y los criterios de
trazabilidad experimental están en [docs/GUIA-DESARROLLO.md](docs/GUIA-DESARROLLO.md).
Conviene leerlo antes de tocar el firmware o el pipeline: varias decisiones que parecen
arbitrarias responden a defectos medidos y documentados.

## 📁 Estructura del repositorio

```
device/                Firmware ESP32 (C++/Arduino)
  ├── device.ino            Orquestación: adquisición, ráfagas, MQTT
  ├── signal_processing.h     Extracción de características (verificable en PC)
  └── test/                 Pruebas de signal_processing.h con g++
server/                Hub: logger MQTT→CSV, aprovisionamiento de la Pi
  ├── data/                 Datasets, un directorio por nodo y firmware
  └── analisis/             Pipeline de detección de anomalías
docs/                  Documentación de ingeniería
  ├── GUIA-DESARROLLO.md    Convenciones y trampas conocidas
  ├── normativa/       Normativa del TFM y PDF oficiales
  └── informes/        Informes de avance
memoria_TFM/           Memoria LaTeX (plantilla oficial MUIoT)
  ├── capitulos/       Contenido por capítulo
  ├── figuras/         Figuras y gráficas
  └── plantilla/       Copia intacta de la plantilla oficial
hardware/              Notas de montaje, fotos y esquemas del banco de pruebas
```

# Arquitectura del Sistema

## Visión general
El sistema sigue un patrón **Edge-Fog** clásico de IoT industrial, con una decisión de
diseño deliberada: la inteligencia de diagnóstico debe poder residir en el nodo edge, y la
nube/hub es infraestructura de *entrenamiento*, no una dependencia de operación.

```
[Compresor físico]
      │ vibración, temperatura, sonido
      ▼
┌─────────────────────────────┐
│  ESP32 (nodo edge)          │
│  - Adquisición multi-sensor │
│  - Auto-recuperación I2C    │
│  - Empaquetado JSON         │
│  - Cliente MQTT             │
└──────────────┬──────────────┘
               │ Wi-Fi / MQTT (QoS 0), DOS canales:
               │   fridge/sensors    9 campos,  cada 1 s
               │   fridge/vibration  45 campos, cada 30 s
               ▼
┌─────────────────────────────┐
│  Raspberry Pi (hub local)   │
│  - Broker Mosquitto         │
│  - mqtt_logger.py → CSV     │
│  - Notebooks de análisis    │
│  - Entrenamiento offline    │
└──────────────┬──────────────┘
               │ (fase futura)
               ▼
      Modelo/umbral exportado
      de vuelta al ESP32 (inferencia embarcada)
```

## Nodo Edge (ESP32)
- **Placa:** DFRobot FireBeetle 2 ESP32-S3 (16 MB de flash, PSRAM octal).
- **Framework:** Arduino sobre ESP-IDF (ESP32 core de Espressif).
- **Buses de sensor:**
  - I2C (GPIO1/2) → MPU-6050 (vibración + temperatura del motor).
  - 1-Wire (GPIO14) → DS18B20 (temperatura externa/ambiente).
  - I2S (GPIO12/13/17) → INMP441 (nivel acústico).
- **Resiliencia:** `checkAndRecoverI2C()` detecta un bus I2C colgado (ACK fallido en
  0x68) y ejecuta `Wire.end()` → `Wire.begin()` → reinicialización del MPU-6050 sin
  reiniciar el microcontrolador. Es la pieza más crítica del firmware: las vibraciones
  del compresor son precisamente lo que puede desconectar físicamente el bus.
- **Ciclo actual:** bucle no bloqueante con `millis()` y dos cadencias independientes: canal
  lento a 1 Hz y ráfaga de 1024 muestras a 1 kHz cada 30 s. La conversión del DS18B20 se
  solicita de forma asíncrona, porque sus ~750 ms detenían el resto de la adquisición.
- **Única espera deliberada:** el bucle de captura de la ráfaga bloquea ~1,02 s. El análisis
  frecuencial exige muestras equiespaciadas y cualquier trabajo intercalado introduciría
  *jitter* en el espectro. Está acotado y muy por debajo del *keepalive* MQTT.

## Hub Local (Raspberry Pi)
- **Broker:** Mosquitto, puerto 1883 (red local, sin exposición a Internet).
- **Punto de acceso:** la Pi genera su propia red Wi-Fi (`NetworkManager` en modo compartido,
  IP fija 10.42.0.1), de modo que el nodo no depende de un router ajeno cuyo DHCP cambió de
  subred cuatro veces durante la puesta a punto. Aprovisionamiento en
  `server/provision-pi.sh`.
- **Logger:** `server/mqtt_logger.py`, suscrito a **ambos** canales, vuelca a
  `server/data/YYYY-MM-DD.csv` y `server/data/YYYY-MM-DD-vibration.csv` (un fichero por día y
  canal, rotación por fecha del sistema).
- **Análisis:** `server/analisis/` — pipeline de carga, limpieza, segmentación por episodios,
  características adimensionales y selección del modelo. Ver su
  [README](../server/analisis/README.md).

## Por qué Edge y no Cloud-first
La solicitud de TFM fija como objetivo desplazar la lógica de diagnóstico al extremo de la
red para permitir detección temprana **sin depender de un flujo masivo de datos hacia la
nube**. Consecuencias de diseño:
- El hub es sustituible por cualquier Raspberry Pi de laboratorio; no hay lock-in cloud.
- El formato de intercambio (JSON sobre MQTT) es deliberadamente simple y ligero.
- La fase final del TFM contempla portar el modelo entrenado (o un umbral estadístico
  derivado de él) de vuelta al ESP32, cerrando el ciclo Edge → Fog → Edge.

## Seguridad (alcance actual)

El sistema contempla **dos escenarios de despliegue** con implicaciones de seguridad muy
distintas. Conviene no confundirlos al documentar el trabajo.

### Escenario objetivo: broker en la Raspberry Pi (red local)
- Wi-Fi doméstico/laboratorio WPA/WPA2, red local aislada.
- MQTT sin TLS ni autenticación: aceptable en una red de confianza no expuesta a Internet.
- Es el escenario que describe la memoria como arquitectura del sistema.

### Escenario actual de desarrollo: broker público externo
Mientras la Raspberry Pi no está desplegada, el nodo publica contra un **broker MQTT
público**, con un prefijo de topic aleatorio (`MQTT_TOPIC_PREFIX`) para no cruzarse con
otros usuarios. Implicaciones reales que hay que tener presentes:

- **Sin confidencialidad.** La telemetría viaja por Internet en claro. Cualquiera que
  conozca el prefijo puede suscribirse y ver los datos del activo.
- **Sin autenticación: riesgo de integridad del dataset.** Cualquiera que conozca el
  prefijo puede *publicar* en esos topics, y el logger escribiría esas tramas en el CSV
  como si vinieran del nodo. Para un TFM esto es más grave que la falta de privacidad: un
  dataset contaminado invalida el entrenamiento del modelo y el problema no se detecta a
  simple vista.
- **El prefijo no es una medida de seguridad**, solo evita colisiones. Si se filtra, hay
  que cambiarlo.
- Mitigación mientras dure esta fase: usar el broker público solo para pruebas de
  conectividad, y **no capturar campañas de medida destinadas a la memoria** hasta tener el
  broker local. Si hubiera que capturar contra el broker público, rotar el prefijo y
  verificar la coherencia temporal de las filas del CSV antes de usarlas.

- Credenciales de Wi-Fi y broker fuera del control de versiones (`device/secrets.h`,
  `server/.env`).

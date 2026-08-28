# Arquitectura del sistema

La tesis del trabajo es que **el diagnóstico ocurre en el nodo**. La nube y el concentrador son
soporte de entrenamiento y almacenamiento, no requisito de operación: si se cae el enlace, el
nodo sigue diagnosticando.

```mermaid
flowchart LR
    subgraph activo["Activo bajo medida"]
        C["Compresor hermético<br/>de refrigeración"]
    end

    subgraph nodo["Nodo sensor · ESP32-S3"]
        direction TB
        S1["MPU-6050<br/>vibración · I2C"]
        S2["DS18B20<br/>temperatura · 1-Wire"]
        S3["INMP441<br/>acústica · I2S"]
        EX["Extracción de<br/>características"]
        DET["Detector de<br/>anomalías"]
        S1 --> EX
        S2 --> EX
        S3 --> EX
        EX --> DET
    end

    subgraph hub["Concentrador · Raspberry Pi"]
        direction TB
        BR["Broker MQTT<br/>Mosquitto"]
        LOG["Registrador<br/>a CSV"]
        BR --> LOG
    end

    subgraph pc["Equipo de análisis"]
        AN["Pipeline de análisis<br/>y ajuste del modelo"]
    end

    C -.->|"vibración<br/>temperatura<br/>sonido"| nodo
    nodo -->|"Wi-Fi · MQTT"| BR
    LOG -->|"CSV"| AN
    AN -.->|"modelo_referencia.h<br/>al recompilar"| DET
```

La flecha de vuelta es discontinua a propósito: **no es un lazo en tiempo de operación**. El
modelo se ajusta en el equipo de análisis y llega al nodo al recompilar el firmware. El nodo no
consulta nada para diagnosticar.

## Los tres canales

```mermaid
flowchart TD
    N["Nodo ESP32-S3"]
    N -->|"cada 1 s"| T1["fridge/sensors<br/>9 campos<br/>magnitudes instantáneas"]
    N -->|"cada 30 s"| T2["fridge/vibration<br/>45 campos<br/>características calculadas"]
    N -->|"cada 30 s"| T3["fridge/status<br/>7 campos<br/>veredicto de salud"]
    T1 --> F1["YYYY-MM-DD.csv"]
    T2 --> F2["YYYY-MM-DD-vibration.csv"]
    T3 --> F3["YYYY-MM-DD-status.csv"]
```

**Por qué tres y no uno.**

El canal lento muestrea a 1 Hz, lo que limita el análisis a frecuencias por debajo de 0,5 Hz.
La vibración del compresor está en torno a los 49 Hz y sus armónicos: a 1 Hz la señal se pliega
y no admite análisis frecuencial. Sirve para tendencias térmicas, no para vibración.

El canal de ráfaga captura 1024 muestras a 1 kHz y publica **las características ya calculadas**,
no la señal. Transmitir 3000 valores por segundo de forma continua sería insostenible, y
calcular en el borde es el planteamiento del proyecto.

El canal de veredicto lleva el diagnóstico. **124 bytes frente a los ~1050 del canal de
características**: quien solo quiera saber el estado del activo recibe un orden de magnitud
menos de tráfico.

## Dos cadencias en el nodo

```mermaid
flowchart LR
    subgraph loop["Bucle principal · no bloqueante con millis()"]
        direction TB
        A["¿1 s desde<br/>la última lectura?"] -->|sí| B["Canal lento<br/>9 magnitudes"]
        A -->|no| C["¿30 s desde<br/>la última ráfaga?"]
        C -->|sí| D["Ráfaga:<br/>1024 muestras a 1 kHz"]
        D --> E["5 transformadas<br/>de Fourier"]
        E --> F["Características<br/>por eje"]
        F --> G["Detector<br/>1,3 ms"]
        G --> H["Publicar en<br/>los 3 topics"]
    end
```

El bucle **no usa `delay()` largos**, con una excepción deliberada: la captura de la ráfaga
bloquea ~1,02 s. El análisis frecuencial exige muestras equiespaciadas y cualquier trabajo
intercalado introduciría *jitter* en el espectro. Está acotado y muy por debajo del *keepalive*
de MQTT.

La conversión del DS18B20 se solicita de forma **asíncrona**: sus ~750 ms de conversión
detendrían el resto de la adquisición.

## Red

El concentrador **genera su propia red Wi-Fi** (`NetworkManager` en modo compartido, IP fija
10.42.0.1). No depende de un router ajeno.

La decisión no es estética: durante la puesta a punto el DHCP de la red doméstica cambió de
subred cuatro veces, y cada cambio dejaba al nodo publicando contra una dirección que ya no
existía. Con el concentrador como punto de acceso, la dirección del broker es fija por
construcción.

```mermaid
flowchart LR
    ESP["ESP32-S3"] -->|"Wi-Fi 2,4 GHz<br/>WPA2"| AP["Raspberry Pi<br/>punto de acceso<br/>10.42.0.1"]
    AP --> MQ["Mosquitto :1883"]
    PC["Equipo de análisis"] -->|"SSH · SCP"| AP
```

## Presupuesto de cómputo en el nodo

| Recurso | Consumo | Disponible |
| :--- | ---: | ---: |
| Búferes estáticos de ráfaga | 22,9 KiB | 512 KB de SRAM |
| Parámetros del modelo | 31,6 KB | 8 MB de PSRAM |
| Cálculo de características | ~30 ms | ciclo de 30 s |
| **Inferencia** | **1,3 ms** | ciclo de 30 s |

La inferencia ocupa el **0,004 % del ciclo**. El coste de diagnosticar en el borde no es una
restricción con este planteamiento.

Los payloads se construyen con `snprintf` sobre búfer estático y nunca con `String`: el nodo
publica de forma continua durante días y la fragmentación del montón acabaría con él.

## Documentos relacionados

- [Conexionado](Conexionado) — pinout y lista de conexiones
- [Pipeline de análisis](Pipeline-de-analisis) — de los CSV al modelo
- [Trampas conocidas](Trampas-conocidas) — lo que ya ha fallado y por qué

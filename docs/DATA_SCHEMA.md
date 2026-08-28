# Esquema de Datos — Telemetría del nodo

## Topics MQTT
| Topic | Dirección | Payload | Frecuencia | CSV |
| :--- | :--- | :--- | :--- | :--- |
| `fridge/sensors` | ESP32 → Hub | JSON, 9 campos | ~1 Hz | `YYYY-MM-DD.csv` |
| `fridge/vibration` | ESP32 → Hub | JSON, 45 campos | cada 30 s | `YYYY-MM-DD-vibration.csv` |
| `fridge/status` | ESP32 → Hub | JSON, 7 campos | cada 30 s | `YYYY-MM-DD-status.csv` |

QoS 0, sin retención. Un mensaje perdido es aceptable: el análisis trabaja con ventanas
estadísticas, no con muestras individuales.

**Por qué tres canales.** El canal lento muestrea a 1 Hz, lo que limita el análisis a
frecuencias por debajo de 0,5 Hz (Nyquist). La vibración de un compresor está en torno a
los 48 Hz (2900 RPM) y sus armónicos, de modo que a 1 Hz la señal se pliega (*aliasing*) y
no admite análisis frecuencial. El canal de ráfaga captura 1024 muestras a 1 kHz y publica
las características ya calculadas en el nodo, en lugar de la señal cruda: transmitir 3000
valores por segundo sería insostenible, y calcular en el borde es precisamente el enfoque
del proyecto.

El tercer canal transporta el **veredicto del detector embarcado**, y es el que materializa el
objetivo del TFM: el diagnóstico lo emite el nodo. Un consumidor que solo quiera saber el
estado del activo recibe 124 bytes en lugar de las 45 características.

El canal lento y el de ráfaga **se mantienen sin cambios** al añadir el detector, y eso no es
casual: añadir campos al payload de ráfaga cambiaría la cabecera del CSV, que el registrador
solo escribe al crear el fichero, con lo que las filas posteriores quedarían desplazadas y la
serie histórica se partiría en dos conjuntos no comparables. Ya ocurrió una vez (ver
[server/data/README.md](../server/data/README.md)). Verificado: el payload de ráfaga sigue
teniendo los mismos 45 campos, en el mismo orden.

## Canal de veredicto — campos del payload `fridge/status`

| Campo | Tipo | Descripción |
| :--- | :--- | :--- |
| `health` | string | `nominal`, `anomaly` o `not_evaluable` |
| `streak` | int | Ráfagas anómalas consecutivas acumuladas |
| `notify` | 0/1 | 1 **solo en la transición** a estado notificable, para no republicar la misma alarma en cada ráfaga |
| `lof` | float | Puntuación del detector principal. Cuanto **menor**, más anómalo |
| `env` | float | Puntuación de la envolvente robusta, misma convención |
| `n_peaks` | int | Picos espectrales significativos, de 0 a 3 |
| `us_inference` | int | Microsegundos de inferencia **en el nodo** |

**`not_evaluable` no es un estado de salud intermedio.** Es la declaración de que la medida no
sirve para decidir, y ocurre por dos causas: más de 3 reintentos del bus I2C —los reintentos
*fabrican* la firma del fallo sobre un activo sano, de modo que juzgar una ráfaga degradada
produce un falso positivo sistemático— o el compresor detenido, caso en que no hay vibración
que analizar. Esas ráfagas **no cuentan ni rompen** la histéresis.

**Por qué se publican las tres puntuaciones y no solo el veredicto.** Los tres indicadores
dicen cosas distintas: `lof` y `env` señalan que el estado se ha alejado del de referencia, y
`n_peaks` que la desviación es una familia armónica. Con los tres, una discrepancia entre ellos
es diagnosticable a posteriori; con uno solo, no.

**`us_inference` es la medida que respalda la tesis del trabajo.** Sin ella, la afirmación de
que el diagnóstico cabe en el borde es una estimación.

**Regla para el análisis:** `notify` es lo que hay que contar para estimar la carga de alarmas
en operación, no `health`. Sobre el conjunto de referencia, el 5,1 % de las ráfagas se marcan
como anómalas pero se emiten **cero** avisos, porque son aisladas y la histéresis exige tres
consecutivas.

## Canal lento — campos del payload `fridge/sensors`

| Campo | Tipo | Unidad | Sensor | Rango esperado | Notas |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tempExt` | float | °C | DS18B20 | −10 … 40 | Ambiente/tubería. `-127.00` = sensor ausente o fallo de lectura. |
| `accX` | float | m/s² | MPU-6050 | ±39.2 (rango ±4 g) | Vibración eje X. |
| `accY` | float | m/s² | MPU-6050 | ±39.2 | Vibración eje Y. |
| `accZ` | float | m/s² | MPU-6050 | ±39.2 | Vibración eje Z. En reposo el eje alineado con la vertical mide la gravedad. **Medido en el banco: el módulo del vector da un 5-20 % por encima de 9,8 según la orientación, atribuible a una desviación de cero de ~+2 m/s² en Z.** Sin efecto sobre el análisis (la extracción elimina la continua), pero el canal lento **no está calibrado en valor absoluto**. |
| `gyroX` | float | rad/s | MPU-6050 | ±8.7 | Velocidad angular eje X. |
| `gyroY` | float | rad/s | MPU-6050 | ±8.7 | Velocidad angular eje Y. |
| `gyroZ` | float | rad/s | MPU-6050 | ±8.7 | Velocidad angular eje Z. |
| `motorTemp` | float | °C | MPU-6050 (interno) | 15 … 85 | Temperatura del die del MPU; proxy de la superficie del motor, no medida calibrada. |
| `noise` | int | adimensional | INMP441 | 0 … ~130000 | Media de \|muestra >> 14\| sobre 64 muestras a 16 kHz. Nivel relativo, **no** dB SPL. |

## Valores centinela y fallos
- `tempExt = -127.00` → `DEVICE_DISCONNECTED_C` de DallasTemperature: sonda desconectada.
  Debe descartarse en el análisis, no interpolarse como medida real.
- Bloque MPU-6050 a `0.0` en los siete campos → `checkAndRecoverI2C()` devolvió `false`:
  el bus I2C no se pudo recuperar en ese ciclo. Los ceros son *ausencia de dato*, no reposo;
  un `accZ` exactamente `0.00` es físicamente imposible con el sensor sano (gravedad).
- `noise = 0` sostenido → micrófono sin inicializar o L/R mal cableado.

Regla para el pipeline de ML: filtrar filas centinela **antes** de calcular estadísticos.
Un solo `-127` arrastra la media de temperatura del día entero.

## Canal de ráfaga — campos del payload `fridge/vibration`

Cada ráfaga son 1024 muestras a 1 kHz (1,024 s de señal). Resolución frecuencial
`fs/n` = 0,98 Hz, banda observable hasta 500 Hz. Los tres ejes se analizan por separado;
el sufijo `_x`, `_y`, `_z` indica el eje.

### Metadatos de la captura
| Campo | Tipo | Unidad | Descripción |
| :--- | :--- | :--- | :--- |
| `vib_fs` | int | Hz | Frecuencia de muestreo nominal de la ráfaga (1000). |
| `vib_n` | int | — | Muestras de la ráfaga (1024). |
| `ms_capture` | int | ms | Duración real de la captura. Si supera holgadamente los 1024 ms, la cadencia no se sostuvo y el eje de frecuencias queda comprimido. **Es el control de calidad de la ráfaga.** |
| `ms_total` | int | ms | Captura más cálculo de características. |
| `failed_bursts` | int | — | Contador acumulado de ráfagas descartadas por fallo del bus I2C desde el arranque. Creciente: su derivada indica la salud del cableado. |
| `bad_frames` | int | — | Contador acumulado de tramas del canal lento descartadas por lectura no válida del MPU-6050. |
| `retries` | int | — | Reintentos de lectura del acelerómetro dentro de **esta** ráfaga (máx. 1024). Incluye tanto los rechazos por módulo como por continuidad (`cont_rejects` está incluido en este total). |
| `total_retries` | int | — | Igual que `retries`, acumulado desde el arranque. |
| `cont_rejects` | int | — | De los `retries` de esta ráfaga, cuántos lo fueron específicamente por la comprobación de **continuidad** entre muestras consecutivas (salto > `ACC_STEP_MAX_MS2` = 6 m/s² en 1 ms), y no por el módulo del vector. Diagnóstico para distinguir EMI, conector suelto o lectura no atómica del sensor como causa raíz de la corrupción de un solo eje; no aporta una característica del modelo por sí sola. |
| `total_cont_rejects` | int | — | Igual que `cont_rejects`, acumulado desde el arranque. |
| `unpublished_bursts` | int | — | Contador acumulado de ráfagas que se capturaron y procesaron con éxito pero no se publicaron por no haber conexión MQTT en el instante de publicar. **Distinto de `failed_bursts`**: `failed_bursts` es un fallo del bus I2C durante la *captura* (la señal nunca existió); `unpublished_bursts` es un fallo de *conectividad* al publicar una señal que sí se calculó. Remedia la carencia de instrumentación descrita en el [informe de despliegue del hub](informes/2026-08-25-despliegue-hub.md), donde se observaron huecos de 102 s y 73 s entre ráfagas con `failed_bursts` a cero. Como la ráfaga perdida nunca llega al broker, el incremento solo se ve en la **siguiente** ráfaga que sí se publique (mismo patrón que el resto de contadores acumulados de esta tabla). |

### Características de vibración (por eje)
| Campo | Tipo | Unidad | Descripción |
| :--- | :--- | :--- | :--- |
| `rms_*` | float | m/s² | Valor eficaz de la componente alterna, **filtrada a 150 Hz**. Nivel global de vibración. |
| `peak_*` | float | m/s² | Máximo valor absoluto tras eliminar la continua, **sobre la señal filtrada**. |
| `kurt_*` | float | — | Kurtosis **sobre la señal filtrada**. 3,0 = ruido gaussiano; valores altos indican impulsividad (indicador clásico de fallo incipiente en rodamientos). 1,5 para un seno puro. |

**Los tres se calculan sobre la señal filtrada a 150 Hz; el espectro no.** El motivo: se
calculan en el dominio del tiempo y por tanto integran toda la banda, de modo que con una
componente de alta frecuencia dominando quedaban sin información diagnóstica — la kurtosis se
clavaba en 1,75, el 1,5 de una senoide pura, hiciera lo que hiciera el compresor.

El corte de 150 Hz conserva la fundamental del activo y sus dos primeros armónicos. Se derivó
de la regla de no pasar de un tercio de la frecuencia de resonancia del montaje, aplicada
entonces a los 448 Hz que se atribuían al acoplamiento adhesivo. **Esa atribución resultó
falsa**: son armónicos del giro (ver más abajo), y la resonancia real del montaje sigue sin
medir, de modo que el corte es una cota conservadora sin verificar.

> El espectro se deja sin filtrar a propósito. Esa decisión, tomada para poder caracterizar lo
> que se creía un artefacto, es **la que hizo posible detectar el fallo de EXP-003**: los
> estadísticos filtrados no lo registran.

Implicación para el análisis: `rms_*`, `peak_*` y `kurt_*` describen la banda 0-150 Hz,
mientras que `fdom_*`, `adom_*` y los picos 2 y 3 describen todo el espectro hasta Nyquist.
No son magnitudes de la misma señal.
| `fdom_*` | float | Hz | Frecuencia dominante, refinada por interpolación parabólica (precisión ~0,02 Hz, muy por debajo del bin de 0,98 Hz). |
| `adom_*` | float | m/s² | Amplitud estimada a la frecuencia dominante (error ≤ 4 %). |
| `f2_*` | float | Hz | Frecuencia del **segundo** pico espectral, en magnitud decreciente. |
| `a2_*` | float | m/s² | Amplitud del segundo pico. |
| `f3_*` | float | Hz | Frecuencia del **tercer** pico espectral. |
| `a3_*` | float | m/s² | Amplitud del tercer pico. |

**Por qué tres picos y no solo el dominante.** Al reubicar el sensor (2026-08-26) aparecieron
componentes entre 398 Hz y 497 Hz que se llevan el 95 % de la energía y desplazan la
fundamental del compresor (≈49 Hz) fuera del pico principal. Con un solo pico esa información
se perdía **en el nodo** y no era recuperable en el hub, porque solo se transmiten
características y no la señal.

Se prefirió esto a acotar la búsqueda a una banda fija, decisión que resultó determinante: esas
componentes son los armónicos 8×, 9× y 10× del giro, es decir la firma de un fallo real, y un
límite de banda las habría dejado fuera. Los picos se separan con una guarda de 4 bins, el
ancho del lóbulo principal de la ventana de Hann, para no devolver la falda del mismo tono como
pico distinto.

**Tres picos son insuficientes y conviene saberlo.** Uno de ellos es la fundamental, así que
solo caben **dos armónicos por ráfaga**: la familia de tres no se registra completa y la pareja
observada varía (8× y 9× en 401 ráfagas de EXP-003, 9× y 10× en 235). No afecta a la detección;
sí a la caracterización del fallo. Ampliarlo a cinco está pendiente.

### Reglas para el pipeline de ML

1. **No dar por supuesto que `fdom_*` es el régimen de giro.** Hay que buscar la fundamental
   entre los tres picos.
2. **Los tres picos vienen ordenados por AMPLITUD, no por frecuencia.** Es la trampa
   importante: en EXP-003 el armónico supera a la fundamental por un 2 % en 60 de 676 ráfagas
   y le quita la posición de dominante, con lo que un cociente `f2_*/fdom_*` da 9,0 en unas
   ráfagas y **0,111 en otras describiendo el mismo fenómeno**. `fdom_x` aparenta un CV del
   133 %.
3. **Hay que reordenar por frecuencia y descartar antes los picos por debajo del 20 % de la
   amplitud mayor**, que son ruido espectral y con frecuencia caen por debajo de la
   fundamental. Con las dos condiciones el CV de la fundamental baja al 0,12 %. Implementado en
   [`server/analisis/pipeline.py`](../server/analisis/pipeline.py).

### Características acústicas
| Campo | Tipo | Unidad | Descripción |
| :--- | :--- | :--- | :--- |
| `aud_fs` | int | Hz | Frecuencia de muestreo del audio (16000). |
| `aud_n` | int | — | Muestras analizadas (1024 → 64 ms, resolución 15,6 Hz). |
| `aud_rms` | float | — | Valor eficaz de la señal acústica. Nivel relativo, **no** dB SPL. |
| `aud_b0` | float | — | Fracción de energía espectral en 0–250 Hz. |
| `aud_b1` | float | — | Fracción de energía en 250–1000 Hz. |
| `aud_b2` | float | — | Fracción de energía en 1000–4000 Hz. |
| `aud_b3` | float | — | Fracción de energía en 4000–8000 Hz. |

Las cuatro bandas suman 1 (verificado en `device/test/test_signal_processing.cpp`). Son fracciones, no
niveles absolutos: describen *cómo se reparte* el sonido, no cuánto suena. El nivel absoluto
está en `aud_rms`.

### Ausencia de dato en el canal de ráfaga
Si el bus I2C falla durante la captura, la ráfaga **se descarta entera** y no se publica: una
señal con huecos produce un espectro sin sentido. Se incrementa `failed_bursts`, que
aparece en la siguiente ráfaga válida. Consecuencia para el análisis: un salto en
`failed_bursts` indica un intervalo sin datos espectrales, no una medida mala.

### Validación de cada muestra dentro de la ráfaga
Cada una de las 1024 lecturas del acelerómetro se acepta solo si pasa dos comprobaciones
independientes, en `device/device.ino`:

1. **Módulo del vector** (banda ancha, 2–25 m/s²): descarta valores saturados o mezclas de
   bytes de dos muestras distintas, pero **no** detecta la caída de un solo eje si los otros
   dos compensan el módulo total.
2. **Continuidad respecto a la muestra anterior de la misma ráfaga** (salto máximo 3 m/s²
   en 1 ms, `ACC_STEP_MAX_MS2`): sí detecta ese caso. Se confirmó en campo con `kurt_z`
   disparado a 150–750 y `peak_z` cayendo a 5,8–6,16 m/s² (la gravedad sana en ese eje es
   ~9,8 m/s²) sin que `failed_bursts` se moviera, porque el módulo total seguía dentro de
   banda.

Si una muestra falla cualquiera de las dos comprobaciones se reintenta una vez; si el
reintento también falla (por cualquiera de las dos razones), el bus se considera caído y la
ráfaga se descarta entera (mismo mecanismo que el fallo de transacción I2C). `retries` y
`cont_rejects` cuantifican, por ráfaga, cuántas muestras necesitaron ese reintento y cuántas
de ellas lo fueron específicamente por continuidad.

Si el audio no llega completo, los campos `aud_*` quedan a 0 y `aud_n` refleja las muestras
realmente leídas: comprobar `aud_n` antes de usar las bandas.

## Formato CSV generado por el logger
`server/data/YYYY-MM-DD.csv` (canal lento), cabecera fija:

```
ts,tempExt,accX,accY,accZ,gyroX,gyroY,gyroZ,motorTemp,noise
2026-08-19T18:44:03.512+02:00,4.31,0.12,-0.05,9.79,0.01,0.00,-0.02,38.60,142
```

- `ts`: instante de **recepción en el hub**, ISO-8601 con offset local. El ESP32 no lleva
  RTC ni NTP en esta fase, por lo que la marca de tiempo es la del hub (jitter de red
  despreciable frente al periodo de 1 s).
- Un fichero nuevo al cruzar la medianoche; el logger cierra y abre sin perder mensajes.

`server/data/YYYY-MM-DD-vibration.csv` sigue el mismo criterio, con las 32 columnas del
canal de ráfaga en el orden de `VIBRATION_FIELDS` de
[server/mqtt_logger.py](../server/mqtt_logger.py). Los campos ausentes se escriben **vacíos**,
nunca a cero: un cero es una medida válida y confundirlo con "sin dato" contamina el dataset.

## Características derivadas

Ya calculadas **en el nodo** (canal de ráfaga): RMS, pico, kurtosis, frecuencia y amplitud
dominantes por eje, y energía acústica por bandas. La implementación está en
[device/signal_processing.h](../device/signal_processing.h) y su verificación numérica en
[device/test/test_signal_processing.cpp](../device/test/test_signal_processing.cpp).

Pendientes, a calcular en el hub sobre series de ráfagas:
- Vibración: magnitud del vector de los tres ejes, evolución de los armónicos, relación
  entre el fundamental y sus múltiplos.
- Térmica: gradiente (∂T/∂t) y diferencial `motorTemp − tempExt`.
- Ciclo: duración de los periodos de marcha y parada, deducida del canal lento.

# Informe de avance — TFM Sistema IoT Edge para mantenimiento predictivo

**Fecha:** 2026-08-19 · **Periodo cubierto:** 2026-08-19
**Fase del roadmap:** 3 — Conectividad y captura de datos · **Horas acumuladas:** sin registrar

## 1. Resumen ejecutivo

Se ha corregido una limitación de diseño que habría invalidado el análisis frecuencial del
proyecto: el muestreo de vibración a 1 Hz no permite observar la firma de un compresor, cuya
fundamental está en torno a los 48 Hz. El firmware pasa a un esquema de doble cadencia con
ráfagas a 1 kHz y extracción de características en el propio nodo. El procesado de señal
queda verificado numéricamente en el PC; el firmware está **pendiente de validación en
placa**.

## 2. Trabajo realizado

| Tarea | Estado | Evidencia |
| :--- | :--- | :--- |
| Diagnóstico del límite de Nyquist en el muestreo de vibración | Completada | Prueba 7 de `device/test/test_signal_processing.cpp` |
| Extracción de características de vibración y audio | Completada | `device/signal_processing.h` |
| Verificación numérica del procesado (17 pruebas) | Completada | `device/test/test_signal_processing.cpp`, 17/17 |
| Refinado del pico por interpolación parabólica | Completada | `device/signal_processing.h`, función `analyzeAxis` |
| Muestreo por ráfagas a 1 kHz | Completada (sin probar en placa) | `device/device.ino`, `captureVibrationBurst()` |
| Bucle no bloqueante con `millis()` | Completada (sin probar en placa) | `device/device.ino`, `loop()` |
| Conversión asíncrona del DS18B20 | Completada (sin probar en placa) | `setWaitForConversion(false)` |
| Payload por `snprintf` sobre buffer estático | Completada | Dimensionado verificado: 471 de 768 bytes |
| Segundo canal MQTT y segundo CSV en el logger | Completada | `server/mqtt_logger.py`, `CANALES` |
| Compilación del firmware | **No realizada** | No hay `arduino-cli` en el equipo |

## 3. Incidencias y decisiones técnicas

**Muestreo a 1 Hz insuficiente.** El firmware anterior cerraba el bucle con `delay(1000)`,
lo que fija una frecuencia de muestreo de 1 Hz y un límite de Nyquist de 0,5 Hz. Un compresor
hermético con motor de dos polos a 50 Hz gira a unas 2900 RPM, es decir, unas 48 vueltas por
segundo, de modo que su vibración fundamental y sus armónicos quedaban muy por encima de la
banda observable. El resultado no era una medida degradada, sino una medida sin sentido
físico por plegado espectral.

**Decisión: doble cadencia en lugar de subir la tasa global.** Se valoró elevar la frecuencia
del bucle completo, pero transmitir tres ejes a 1 kHz supone del orden de 3000 valores por
segundo, insostenible sobre MQTT y contrario al planteamiento del trabajo. Se opta por
capturar ráfagas de 1024 muestras a 1 kHz cada 30 s y publicar únicamente las
características extraídas. La decisión refuerza el enfoque de procesado en el borde por una
razón de ingeniería, no como principio de diseño declarado.

**Decisión: conservar el canal lento sin cambios.** El topic `fridge/sensors` mantiene sus
nueve campos y su cadencia de 1 Hz. Así los datos ya capturados siguen siendo comparables y
se conserva la resolución temporal necesaria para las tendencias térmicas y la detección de
los ciclos de marcha y parada. Las características espectrales van a un topic nuevo,
`fridge/vibration`.

**Decisión: bloqueo deliberado durante la ráfaga.** El bucle de captura bloquea ~1,02 s. El
análisis frecuencial exige muestras equiespaciadas y cualquier trabajo intercalado
introduciría jitter que ensuciaría el espectro. El bloqueo está acotado y queda muy por
debajo del keepalive MQTT de 15 s.

**Incidencia detectada en revisión: orden de evaluación.** La primera versión de la lectura
cruda del acelerómetro componía cada eje como `(Wire.read() << 8) | Wire.read()`. El orden de
evaluación de los operandos no está especificado en C++, por lo que el byte alto y el bajo
podían intercambiarse según el compilador. Corregido con variables intermedias.

**Mejora sobre el estimador espectral.** La estimación de amplitud sobre un único bin
subestimaba hasta un 13 % cuando el tono cae entre dos bins (pérdida de festoneado de la
ventana de Hann). Se incorporó interpolación parabólica sobre la log-magnitud de los tres
bins centrales. Medido sobre señales sintéticas entre 45 Hz y 97 Hz:

| Estimador | Error de frecuencia (peor caso) | Error de amplitud (peor caso) |
| :--- | :--- | :--- |
| Bin único | 0,49 Hz (medio bin) | 13,2 % |
| Interpolación parabólica | **0,016 Hz** | **3,6 %** |

La frecuencia queda así resuelta unas 60 veces por debajo del ancho del bin, lo que permite
seguir desplazamientos pequeños del régimen de giro.

## 4. Datos capturados

Sin campañas de medida en este periodo: el trabajo ha sido de firmware y verificación
numérica. `server/data/` sigue vacío.

## 5. Bloqueos

- **No hay `arduino-cli` en el equipo de desarrollo**, por lo que el firmware no se ha
  compilado ni ejecutado. Es el bloqueo principal: hasta resolverlo, todo lo relativo al
  nodo es código sin validar en hardware.
- Pendiente el despliegue de Mosquitto en la Raspberry Pi, requisito para cualquier captura.

## 6. Riesgos

- **Nuevo:** la cadencia de la ráfaga puede no sostenerse en la placa si la lectura por I2C
  tarda más de 1000 µs por muestra. Mitigación implementada: el firmware publica
  `ms_capture`, que permite descartar en el análisis las ráfagas cuya duración se desvíe de
  los 1024 ms nominales.
- **Resuelto:** muestreo insuficiente para análisis frecuencial.
- **Sin cambios:** ausencia de fallos reales que etiquetar; `motorTemp` como indicador
  indirecto.
- **Por confirmar:** las 2900 RPM son las típicas de un motor de dos polos a 50 Hz, no una
  medida del activo. Conviene verificarlas en la placa de características antes de
  interpretar los espectros.

## 7. Próximos pasos

1. Instalar `arduino-cli`, compilar el firmware y corregir lo que aparezca.
2. Validar en placa: `ms_capture` ≈ 1024 ms, `ms_total` acotado, y que `fdom_z` coincide con
   el régimen real del compresor.
3. Desplegar Mosquitto en la Raspberry Pi y validar los dos CSV con el logger.
4. Solo entonces, lanzar la campaña baseline de ≥24 h. Lanzarla antes produciría un dataset
   sin contenido espectral utilizable y habría que repetirla.

## 8. Impacto en la memoria

Redactable ya con este avance:
- Capítulo 4 (Metodología), fase de conectividad: la incidencia del muestreo y su corrección.
- Capítulo 5 (Diseño): justificación cuantitativa de las frecuencias de muestreo a partir de
  Nyquist y del régimen del compresor; diseño del doble canal.
- Anexo técnico de software: campos del canal de ráfaga y criterios de validez.

Sigue bloqueado por falta de datos: todo el capítulo 6 (Resultados), que necesita la campaña
baseline.

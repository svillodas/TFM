# Notas de Hardware y Montaje

## Estado de validación
| Sensor | Bus | Pines | Estado |
| :--- | :--- | :--- | :--- |
| MPU-6050 | I2C | 21 (SDA) / 22 (SCL) | Validado, con auto-recuperación de bus |
| DS18B20 | 1-Wire | 14 (DATA) | Validado, pull-up ~5 kΩ a 3V3 |
| INMP441 | I2S | 12 (WS) / 13 (SD) / 17 (SCK) | Validado, L/R a GND (canal izquierdo) |

## Incidencias resueltas
- **Bus I2C colgado por vibración.** El movimiento del compresor provocaba microcortes en
  el cableado del MPU-6050 y el bus quedaba bloqueado, congelando el `loop()`. Resuelto por
  software con `checkAndRecoverI2C()`: sondeo de ACK en 0x68 y reinicio del bus con
  reinicialización del sensor, sin reiniciar el ESP32. **No eliminar esta rutina.**

## Configuración exigida por el muestreo a alta tasa
- **Bus I2C a 400 kHz** (`Wire.setClock(400000)`). A 100 kHz la lectura de los seis bytes
  del acelerómetro no cabe en el presupuesto de 1000 µs por muestra de la ráfaga.
- **Tasa interna del MPU-6050 a 1 kHz** (`setSampleRateDivisor(0)`): si el sensor entrega
  muestras más despacio que el bucle de lectura, se leen valores repetidos y el espectro
  resulta falso.
- **Filtro interno a 260 Hz** (`setFilterBandwidth(MPU6050_BAND_260_HZ)`): acota el
  contenido por debajo de la frecuencia de Nyquist de la ráfaga (500 Hz) para evitar que
  las componentes altas se plieguen dentro de la banda de análisis.
- **DS18B20 en conversión asíncrona** (`setWaitForConversion(false)`): sus ~750 ms de
  conversión a 12 bits bloqueaban el bucle. Se pide la conversión en un ciclo y se lee en
  el siguiente.

## Cuidados de montaje
- El acelerómetro debe ir **rígidamente acoplado** al chasis del compresor. Cinta o bridas
  blandas introducen su propia resonancia y el sensor acaba midiendo el soporte.
- Cableado I2C lo más corto posible y con alivio de tensión; es el punto débil frente a
  vibración sostenida.
- El INMP441 necesita línea de visión acústica al motor, alejado del flujo de aire del
  ventilador (el flujo satura la señal con ruido de banda ancha).
- Alimentación común 3V3 y GND común para los tres sensores.

## Pendiente
- **Verificar el firmware de ráfagas en la placa.** El equipo de desarrollo no tiene
  `arduino-cli`, así que el firmware no se ha compilado ni ejecutado en hardware. La
  matemática de extracción de características sí está verificada en el PC.
- Medir el régimen real del compresor (placa de características o tacómetro) para confirmar
  la frecuencia fundamental esperada. Las ~2900 RPM asumidas corresponden a un motor de dos
  polos a 50 Hz, pero conviene comprobarlo antes de interpretar los espectros.
- Encapsulado del nodo para la prueba en entorno real (Fase 7).
- Evaluar un segundo DS18B20 fijado a la carcasa del motor: `motorTemp` del MPU-6050 es la
  temperatura del die del chip, un proxy pobre de la temperatura real del motor.
- Fotos del banco de pruebas en `hardware/`.

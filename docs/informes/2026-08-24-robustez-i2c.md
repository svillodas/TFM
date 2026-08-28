# Informe de avance — TFM Sistema IoT Edge para mantenimiento predictivo

**Fecha:** 2026-08-24 · **Periodo cubierto:** 2026-08-19 a 2026-08-24
**Fase del roadmap:** 3 — Conectividad y captura de datos · **Horas acumuladas:** sin registrar

## 1. Resumen ejecutivo

El firmware de muestreo por ráfagas se ha validado en hardware por primera vez: la cadencia
de 1 kHz se sostiene con exactitud y el coste de cálculo de características es de 30 ms. En
el proceso se localizaron y corrigieron dos defectos de integridad de datos que habrían
invalidado el conjunto de entrenamiento sin dar ninguna señal visible, ambos originados en
que ni la biblioteca `Wire` del ESP32 ni la de Adafruit propagan los errores del bus I2C. Se
ha verificado además que la frecuencia dominante medida coincide con el régimen de giro del
compresor. No se ha capturado ninguna campaña de medida en el periodo.

## 2. Trabajo realizado

| Tarea | Estado | Evidencia |
| :--- | :--- | :--- |
| Validación del muestreo por ráfagas en placa | Completada | `ms_capture` = 1024 ms en todas las ráfagas observadas |
| Medida del coste de cálculo de características en el nodo | Completada | `ms_total` − `ms_capture` = 29-30 ms |
| Diagnóstico del truncado silencioso de `Wire.read()` | Completada | Campos de diagnóstico temporales: `dbg_zv` = −1 con vecinas válidas |
| Validación de la transacción I2C en cuatro puntos | Completada | `device/device.ino`, `readRegisters()` |
| Reintento único por muestra en la ráfaga | Completada | `device/device.ino`, `captureVibrationBurst()` |
| Sustitución de `mpu.getEvent()` por lectura directa de 14 registros | Completada | `device/device.ino`, `readMpuBlock()` |
| Validación de plausibilidad física del vector de aceleración | Completada | `device/device.ino`, `isPlausibleRaw()` |
| Escala del giróscopo leída del registro `GYRO_CONFIG` | Implementada, **pendiente de validar en placa** | `device/device.ino`, `updateGyroScale()` |
| Contadores de salud del nodo (`bad_frames`, `retries`, `total_retries`) | Completada | Payload de `fridge/vibration`; `server/mqtt_logger.py`, `VIBRATION_FIELDS` |
| Pines I2C declarados de forma explícita | Completada | `I2C_SDA` / `I2C_SCL`; contrastado con el fichero de variante del core 3.3.1 |
| Reducción del bus I2C de 400 kHz a 200 kHz | Completada | `I2C_FREQ_HZ` |
| Verificación en PC de la lógica de adquisición | Completada | Arnés con `Wire` simulado: reintentos, descartes, cadencia, escalas y plausibilidad |
| Dimensionado de los payloads tras añadir campos | Completada | Ráfaga 702 B y canal lento 201 B sobre buffer de 896 B |
| Configuración del broker Mosquitto local | Completada | `server/mosquitto-local.conf` |
| Validación extremo a extremo del logger | Completada | Ambos canales y descarte de JSON malformado, comprobados con tramas sintéticas |
| Identificación del régimen de giro del compresor | Completada | `fdom_x`, `fdom_y`, `fdom_z` ≈ 49,1 Hz con `motorTemp` a 42 °C |
| Captura de campañas de medida | **No realizada** | `server/data/` vacío |

## 3. Incidencias y decisiones técnicas

**Truncado silencioso de las lecturas fallidas del bus.** El firmware asumía que
`Wire.requestFrom()` señalaba el fracaso de una transacción devolviendo una cuenta de bytes
menor que la solicitada. No lo hace: el registro del controlador anota
`i2c_master_transmit_receive failed` mientras la función devuelve la cuenta pedida. El código
leía entonces de un buffer vacío, donde `Wire.read()` devuelve −1, y al asignar ese valor a
una variable `uint8_t` se convertía en `0xFF`. Los tres ejes salían como `0xFFFF`, es decir
−1 en complemento a dos, y esa muestra se publicaba como medida válida.

El efecto sobre las características es desproporcionado. Una única muestra anómala entre
1024 elevó la kurtosis del eje vertical de 2,9 a 847. La cifra es coherente con la
predicción analítica para un impulso aislado, `kurt ≈ (d⁴/n)/(d²/n + σ²)²`, que para los
valores medidos da 846,0 frente a los 846,859 observados. La kurtosis es precisamente el
indicador elegido para detectar impulsividad incipiente en rodamientos, de modo que el
artefacto era indistinguible del fallo que el sistema debe detectar.

*Decisión: validar la transacción y reintentar en lugar de descartar.* Se comprueban cuatro
condiciones —el resultado de `endTransmission()`, la cuenta de `requestFrom()`, el número de
bytes en `available()` y el signo de cada `read()`— y un fallo aislado se reintenta una vez
dentro del mismo hueco temporal. Se valoró descartar la ráfaga completa ante cualquier
fallo, que era el comportamiento anterior, pero la ráfaga son 1024 lecturas consecutivas: con
una tasa de fallo por lectura del 0,1 % solo sobreviviría el 36 % de las ráfagas. Con un
reintento la probabilidad de fallo efectiva pasa a 10⁻⁶. El coste es que la muestra
reintentada queda desplazada unos 420 µs de su instante nominal, una perturbación de una
muestra entre 1024, y queda declarada en el campo `retries` para poder filtrarla en el
análisis. Solo dos fallos consecutivos, que ya no son un microcorte sino un bus caído,
descartan la ráfaga.

Se descartó forzar un segundo reintento: a 200 kHz una lectura de seis bytes cuesta unos
415 µs, de modo que dos reintentos superarían el periodo de muestreo de 1000 µs.

**Publicación de basura en el canal lento.** El canal de 1 Hz obtenía las medidas mediante
`mpu.getEvent()` de la biblioteca Adafruit. Su implementación devuelve `true` de forma
incondicional y su función interna `_read()` opera sobre un buffer de pila sin inicializar,
descartando además el valor de retorno de la lectura. Ante un fallo del bus se interpretan
como medidas los bytes que hubiera en la pila. Se observó una trama con `accY` = −38,25 m/s²
y `motorTemp` = 61,18 °C; el valor de temperatura corresponde exactamente al término
constante de la fórmula de conversión con lectura cruda nula, lo que confirma el mecanismo.

La gravedad del caso está en que esa trama burla los tres centinelas definidos en
`docs/DATA_SCHEMA.md`: la temperatura externa es correcta, el bloque del acelerómetro no
está a cero y los valores caen dentro del rango nominal del sensor. El registrador la habría
escrito en el CSV como una medida legítima.

*Decisión: lectura directa de los registros del sensor.* Se sustituye `mpu.getEvent()` por
una única transacción validada de 14 bytes desde el registro `0x3B`, que entrega aceleración,
temperatura y velocidad angular. La biblioteca Adafruit se mantiene solo para la
configuración inicial del dispositivo, fuera del camino crítico. Cuando la lectura no supera
la validación, los campos del acelerómetro quedan a cero —el centinela de ausencia de dato
que ya documenta el esquema— y el descarte se declara en el contador `bad_frames`. No se
filtra en silencio: un dato perdido que no se cuenta es indistinguible de un dato bueno.

**Segunda línea de defensa por plausibilidad física.** La validación de la transacción no
cubre el caso en que el bus entrega bytes formalmente correctos pero sin sentido físico. Se
añade una comprobación sobre el módulo del vector de aceleración, que debe contener siempre
la gravedad y que en un compresor doméstico no alcanza decenas de m/s². La banda adoptada,
de 2 a 25 m/s², es deliberadamente ancha para no descartar vibración real.

Conviene anotar su limitación, comprobada en placa: la prueba opera sobre el módulo y no
detecta la caída de un solo eje cuando los restantes aportan magnitud suficiente. Una muestra
con el eje vertical a cero y el horizontal en su valor nominal arroja un módulo plausible. La
comprobación es por tanto complementaria de la validación de la transacción, no sustitutiva.

**Escala del giróscopo tomada del dispositivo.** Al retirar `mpu.getEvent()` se codificó
inicialmente el factor de conversión suponiendo el rango de ±500 °/s que la biblioteca
programa en su inicialización. La comparación de ambas versiones con el sensor en la misma
posición arrojó −0,10 rad/s con el escalado de la biblioteca frente a −0,21 rad/s con la
constante fija, un factor dos que indica que el dispositivo estaba operando en su rango de
arranque de ±250 °/s. La biblioteca acertaba porque lee el registro de configuración en cada
medida. Se corrige leyendo `GYRO_CONFIG` al configurar el sensor y tras cada recuperación del
bus, y registrando el rango detectado por el puerto serie. La decisión de fondo es que una
escala supuesta es peor que el defecto que se pretendía corregir: altera en silencio las
unidades de tres columnas del conjunto de datos.

**Velocidad del bus I2C.** A 400 kHz aparecían muestras corruptas de forma recurrente en el
eje vertical. Reducir el bus a 200 kHz eliminó esa corrupción concreta, aunque no los
microcortes del bus. El coste temporal es asumible: una lectura pasa de unos 210 µs a unos
415 µs, holgadamente dentro del periodo de 1000 µs.

**Recuperación del bus reactiva.** La rutina de recuperación pasa a invocarse cuando una
lectura falla realmente, en lugar de sondear el bus preventivamente antes de cada ciclo. Se
conserva íntegra su lógica —reinicio del bus y reconfiguración del sensor sin reiniciar el
microcontrolador— y se le añade una espera de 50 ms tras la reinicialización, porque los
registros del acelerómetro permanecen a cero hasta que concluye la primera conversión.

**Régimen de giro del compresor.** Con el compresor en marcha, identificado por una
temperatura de la superficie de 42 °C frente a 27,6 °C de ambiente, los tres ejes coinciden
en una frecuencia dominante de 49,1 Hz. El valor es coherente con un motor de inducción de
dos polos alimentado a 50 Hz, cuya velocidad sincrónica de 3000 RPM se reduce por el
deslizamiento hasta unas 2950 RPM. Con el compresor detenido y la superficie a temperatura
ambiente, ese pico desaparece y las frecuencias dominantes de los tres ejes resultan
dispares, como corresponde a ruido sin contenido determinista.

La verificación exige el acuerdo entre los tres ejes: se han observado lecturas aisladas
próximas a 49 Hz en un único eje sobre el suelo de ruido, que no constituyen evidencia. La
proximidad entre el régimen mecánico y la frecuencia de la red, separados por menos de dos
veces la resolución frecuencial de 0,98 Hz, obliga a esta cautela y debe quedar advertida en
el análisis.

**Desviación del acelerómetro.** El módulo del vector de aceleración en reposo resulta entre
un 7 % y un 10 % superior a la gravedad. Contrastando medidas en dos orientaciones distintas
se concluye que el origen es una desviación de cero de unos +2 m/s² en el eje vertical, y no
un error de ganancia: un error de ganancia mantendría el módulo constante al reorientar el
sensor. La consecuencia práctica es nula para el análisis, porque la extracción de
características elimina la componente continua antes de cualquier cálculo, y la kurtosis y la
frecuencia dominante son invariantes a la escala. Procede documentar que el canal lento no
está calibrado en valor absoluto.

## 4. Datos capturados

**No hubo captura de campañas en el periodo.** El directorio `server/data/` está vacío y
`docs/EXPERIMENTOS.md` no registra ninguna campaña.

| Campaña | Fichero | Muestras | Muestras válidas | Observaciones |
| :--- | :--- | :--- | :--- | :--- |
| — | — | — | — | Sin campañas en el periodo |

Las tramas empleadas para el diagnóstico se obtuvieron por suscripción directa al broker y no
se almacenaron: son observaciones de puesta a punto del nodo, no medidas experimentales.

## 5. Bloqueos

**El nodo publica contra un broker público.** Es adecuado para verificar conectividad, pero
no para capturar campañas destinadas a la memoria: cualquiera que conozca el prefijo de topic
puede publicar en él y el registrador escribiría esas tramas en el CSV. El broker local ya
está configurado y validado; falta redirigir el nodo hacia él, lo que exige que el nodo y el
equipo que aloja el broker compartan red.

**Acoplamiento mecánico del sensor sin verificar.** Con el compresor en marcha se midieron
valores eficaces de vibración entre 0,07 y 0,98 m/s². La magnitud parece baja para el activo
y apunta a una fijación insuficientemente rígida, en cuyo caso el sensor mediría el
movimiento de su soporte y no el del motor. No está comprobado: exige contrastar la medida
con el sensor acoplado rígidamente al chasis. Es el bloqueo de mayor impacto sobre la calidad
del conjunto de datos, porque ningún modelo puede discriminar una señal que el sensor no
llega a registrar.

**Conexionado del bus todavía marginal.** El contador `total_retries` crece de forma
apreciable y persisten los mensajes de reconocimiento fallido. El mecanismo de reintento
absorbe los fallos sin contaminar el dato, de modo que no impide capturar, pero el conexionado
mediante conectores desmontables no es adecuado para una exposición prolongada a la vibración.
Procede soldar las uniones con alivio de tensión antes de la campaña de 24 h.

**Registro de dedicación inexistente.** No hay constancia de las horas invertidas, lo que
impide contrastar el avance real con el reparto previsto de 150 h.

## 6. Riesgos

**Nuevo — corrupción silenciosa por bibliotecas que no propagan errores.** Materializado y
corregido en dos puntos independientes durante este periodo. Su gravedad reside en que no
produce ninguna señal externa: el nodo sigue publicando, el registrador sigue escribiendo y
la contaminación solo se aprecia al analizar la distribución de las características. Se
mitiga con los contadores `bad_frames`, `retries` y `total_retries`, que hacen medible la
calidad de cada medida. Como criterio general, procede desconfiar de toda biblioteca que no
devuelva estado de error en el camino crítico de adquisición.

**Nuevo — confusión entre el régimen mecánico y la frecuencia de la red.** El fundamental del
compresor, en torno a 49 Hz, y la frecuencia de la red, 50 Hz, están separados por menos de
dos veces la resolución frecuencial. Atribuir a la máquina una captación eléctrica falsearía
el diagnóstico. Se mitiga exigiendo acuerdo entre los tres ejes y contrastando con el
compresor detenido.

**Actualizado — muestreo por ráfagas.** El riesgo de que la cadencia no se sostuviese en la
placa queda **descartado**: `ms_capture` se mantiene en 1024 ms en todas las ráfagas
observadas.

**Actualizado — desconexión del bus por vibración.** Se mantiene, pero su impacto pasa de
huecos en el conjunto de datos a pérdida de ráfagas contabilizada. El riesgo residual es
ahora la degradación mecánica de las uniones a lo largo de días de exposición.

## 7. Próximos pasos

1. Validar en placa la lectura del rango del giróscopo y comprobar el rango que registra el
   nodo por el puerto serie *(Fase 3)*.
2. Corregir en `docs/DATA_SCHEMA.md` el rango del giróscopo, el valor de reposo del eje
   vertical, la banda observable —limitada a 260 Hz por el filtro interno del sensor, no a
   500 Hz por Nyquist— y añadir los cuatro contadores de salud *(Fase 3)*.
3. Corregir en `docs/HARDWARE_NOTES.md` los pines del bus I2C, indicados como GPIO 21 y 22
   cuando el firmware emplea GPIO 1 y 2 y la placa carece de GPIO 22 *(Fase 3)*.
4. Soldar el conexionado del sensor con alivio de tensión y fijarlo de forma rígida al chasis;
   contrastar el valor eficaz de vibración antes y después *(Fase 3)*.
5. Redirigir el nodo al broker local y comprobar la escritura de ambos CSV *(Fase 3)*.
6. Campaña de referencia en estado nominal, de al menos 24 h continuas, con registro en
   `docs/EXPERIMENTOS.md` *(Fase 3)*.
7. Limpieza del conjunto de datos y extracción de características derivadas en el hub
   *(Fase 4)*.

## 8. Impacto en la memoria

Con lo avanzado en este periodo pueden redactarse ya:

- **`04-metodologia.tex`**: el procedimiento de validación del muestreo en hardware y la
  estrategia de verificación del procesado de señal en el PC antes de subirlo a la placa.
- **`05-diseno.tex`**: la arquitectura de adquisición robusta —validación de la transacción,
  reintento acotado y plausibilidad física—, con el razonamiento cuantitativo sobre la
  supervivencia de las ráfagas. El apartado de tratamiento de la ausencia de dato queda
  completo, incluidos los contadores de salud del nodo.
- **`A1-anexo-hardware.tex`**: la caracterización del bus I2C, la elección de 200 kHz y la
  desviación de cero del acelerómetro.

Siguen bloqueados por falta de datos experimentales todos los `% TODO` de
`06-resultados.tex`, así como los apartados de `07-conclusiones.tex` que dependen de las
métricas de detección. La identificación del régimen de giro del compresor es un resultado
utilizable, pero procede consolidarlo con una campaña registrada antes de citarlo.

# Informe de avance — Detector embarcado en el nodo

**Fecha:** 27 de agosto de 2026
**Estado:** escrito y verificado en el PC; pendiente de compilar y flashear
**Fase:** 6 — Inferencia en el Edge

---

## 1. Resumen

Se implementó el detector de anomalías para ejecución en el nodo y se verificó en el PC contra
la referencia de scikit-learn sobre las **1161 ráfagas reales** de las dos campañas: **cero
veredictos discrepantes**.

Lo que queda es compilar y flashear, que exige `arduino-cli` y la placa conectada. La lógica ya
está verificada, de modo que en hardware solo resta medir tiempo y memoria.

| Elemento | Estado |
| :--- | :--- |
| Exportación del modelo a cabecera C++ | Hecho |
| Aritmética del detector, sin dependencias de Arduino | Hecho |
| Verificación contra scikit-learn, 1161 casos | **0 discrepancias** |
| Integración en `device.ino` con topic propio | Hecho |
| El registrador guarda el canal nuevo | Hecho |
| Compilar y flashear | Pendiente: falta `arduino-cli` y la placa |

---

## 2. Sin TinyML, y por un motivo de fondo

Los entornos de ejecución de modelos reducidos para microcontroladores —TensorFlow Lite Micro—
operan sobre **redes neuronales**: su repertorio son convoluciones, capas densas y funciones de
activación.

Ninguno de los modelos candidatos pertenece a esa familia. LOF es una búsqueda de vecinos más
cercanos, la envolvente robusta una forma cuadrática, el bosque de aislamiento un conjunto de
árboles. **No es que TFLite Micro resulte excesivo: no puede ejecutarlos.**

Y una red neuronal no era alternativa: con 505 observaciones nominales de 24 episodios,
cualquier arquitectura con capacidad apreciable se sobreajustaría. La familia de modelos la
determinó el tamaño de muestra, no la plataforma.

La propuesta de trabajo, por lo demás, **no menciona TinyML**: pide «algoritmos de Machine
Learning», y LOF y la envolvente robusta lo son.

La inferencia se programa por tanto directamente: ~15 líneas de C++ para la envolvente, ~60
para LOF.

---

## 3. Arquitectura de la solución

```
server/analisis/exportar_modelo.py
        │  ajusta sobre el conjunto nominal
        ▼
device/modelo_referencia.h          GENERADA. Parámetros y procedencia
        │
        │  #include
        ▼
device/detector.h                   La aritmética. Sin dependencias de Arduino
        │
        ├──► device/test/test_detector.cpp      verificación en el PC
        └──► device/device.ino                  publica en fridge/status
```

La separación entre `modelo_referencia.h` (los números) y `detector.h` (la aritmética) es
deliberada: **reentrenar no debe obligar a tocar código**. Se vuelve a ejecutar el exportador y
se recompila.

La cabecera generada lleva anotada la campaña, la duración, el número de ráfagas y episodios, el
filtro de calidad y la fecha, de modo que un firmware en la placa siempre se puede rastrear a
los datos que lo produjeron.

---

## 4. Coste real en el nodo

| Modelo | Memoria | Operaciones por ráfaga |
| :--- | ---: | ---: |
| Regla `n_picos` | 8 B | 3 |
| Envolvente robusta | 840 B | 210 |
| One-Class SVM | 2,3 KB | 1 110 |
| **LOF** (el elegido) | **31,6 KB** | **15 150** |
| Isolation Forest | 274 KB | 4 800 |

La placa tiene 512 KB de SRAM y 8 MB de PSRAM, y 15 150 operaciones en coma flotante a 240 MHz
son del orden de **0,1 ms** frente a una ráfaga cada 30 s.

Debe consignarse que en la primera versión del análisis varios modelos se descartaron por «no
embarcables» **sin haberlo medido**, y que esa restricción inexistente sesgaba la elección hacia
los modelos más simples.

---

## 5. El veredicto va en un topic propio

```
fridge/sensors    9 campos,  cada 1 s     sin cambios
fridge/vibration  45 campos, cada 30 s    sin cambios
fridge/status     7 campos,  cada 30 s    NUEVO
```

```json
{"health":"anomaly","streak":3,"notify":1,
 "lof":-1.5218,"env":-95.31,"n_peaks":3,"us_inference":1840}
```

124 bytes en el peor caso.

**Por qué un topic y no campos nuevos en la ráfaga.** Añadir campos cambia la cabecera del CSV,
que el registrador solo escribe al crear el fichero: las filas posteriores quedarían desplazadas
y la serie histórica se partiría en dos conjuntos no comparables. Ya ocurrió una vez.
Verificado que el payload de ráfaga conserva sus 45 campos en el mismo orden.

Y es el objetivo del TFM hecho visible: quien solo quiera el estado del activo recibe 124 bytes
en lugar de 45 características.

---

## 6. Tres estados, no dos

```c
VEREDICTO_NOMINAL
VEREDICTO_ANOMALIA
VEREDICTO_NO_EVALUABLE   // el nodo se NIEGA a juzgar
```

El tercero **no es un estado de salud intermedio**: es la declaración de que la medida no sirve
para decidir. Ocurre con más de 3 reintentos del bus —los reintentos fabrican la firma del fallo
sobre un activo sano— o con el compresor detenido. Esas ráfagas no cuentan ni rompen la
histéresis: no informan del estado de la máquina.

---

## 7. La histéresis, calibrada sobre datos reales

Simulando el flujo de las 1161 ráfagas:

| Ráfagas consecutivas exigidas | Avisos falsos (nominal) | Avisos sobre el fallo |
| ---: | ---: | ---: |
| 1 | 22 | 1 |
| 2 | 4 | 1 |
| **3** | **0** | **1** |
| 4 | 0 | 1 |

**Cero avisos falsos en 505 ráfagas nominales, y el fallo notificado.** El 5,1 % de ráfagas
marcadas se convierte en 0 avisos porque son aisladas. Es lo que convierte el detector en algo
usable: un sistema que avisa con una ráfaga suelta se ignora al tercer día.

Consecuencia para el análisis: **hay que contar `notify`, no `health`**, para estimar la carga
de alarmas en operación.

---

## 8. Cuatro defectos que la verificación destapó

Ninguno habría aparecido sin portar el código a un entorno de precisión simple.

**1. Una prueba mía mal planteada.** Esperaba 2 picos donde la respuesta correcta era 3: 0,05 sí
alcanza el 20 % de 0,2056. El código estaba bien.

**2. La covarianza de la envolvente era casi singular** — número de condición 1,4·10¹⁷. Causa:
las cuatro bandas acústicas **suman 1 por construcción** (medido: 1,000003 ± 5,9·10⁻⁵), porque
el firmware las normaliza. Cuatro columnas con dependencia lineal exacta.

La forma cuadrática sufría una cancelación de factor 45 000: se sumaban 883 millones para dar
19 463, y en precisión simple el resultado se desviaba 37 unidades. Corregido eliminando
`aud_b3` —que es `1 − b0 − b1 − b2`, no se pierde información— con lo que la condición baja a
6,5·10⁴, y acumulando la forma cuadrática en doble precisión.

**3. Un caso exactamente en la frontera.** La amplitud del tercer pico valía 0,044700 y el
umbral 0,2 × 0,2235 = 0,0447000000000000004: en doble queda fuera y en simple dentro. Corregido
haciendo que **el análisis en Python compare en precisión simple**, igual que el firmware, con lo
que ambos coinciden bit a bit. Es lo coherente cuando el firmware es el destino del modelo.

**4. `np.argsort` usa quicksort, que no es estable.** Cuando dos picos son ambos insignificantes
reciben la misma clave y su orden relativo era arbitrario. Cambiado a ordenación estable, que es
lo que hace la ordenación por inserción del firmware.

---

## 9. Dos limitaciones que el porte puso de manifiesto

**El modelo exportado es específico del activo sobre el que se ajustó.** Lleva las medianas del
nodo A, su umbral marcha/parada y su referencia de estado sano. Flashearlo en el nodo B daría
`not_evaluable` en el **100 %** de sus ráfagas: su valor eficaz en marcha es de 0,16 m/s² y el
umbral del nodo A es 0,199. Cada nodo necesita su propia campaña de referencia. Y el nodo
necesita una **fase de referencia** antes de poder emitir su primer veredicto.

**Tres características no se pueden validar con los datos disponibles.** `rms_x_rel`,
`adom_x_rel` y `dif_rel` se normalizan por la mediana del propio activo. Existen para detectar un
fallo que solo altere el nivel sobre una máquina con su propia referencia sana, y del activo con
fallo no hay ningún periodo sano medido: usar su propia mediana las anula, y usar la del activo
de referencia reintroduciría el sesgo entre máquinas. Solo un fallo inducido sobre el activo de
referencia lo resuelve.

---

## 10. El registrador no guardaba el canal nuevo

Detectado antes de dejar correr ninguna captura. El registrador estaba suscrito a dos topics: el
nodo habría publicado el veredicto y **el dato se habría perdido sin que nada protestase**.

Corregido, y añadida una comprobación a `provision-pi.sh comprobar` que verifica que el
registrador conoce los tres topics, precisamente porque el fallo que evita es silencioso.

---

## 11. Lo que falta

```
arduino-cli:  NO INSTALADO   ->  brew install arduino-cli
placa:        no conectada
```

Después: compilar —es el paso que puede fallar, porque el modelo añade 31,6 KB de constantes—,
flashear **el nodo A**, y verificar en placa cruzando el CSV de ráfaga con el de estado por
marca de tiempo. Ambos llevan la misma marca, de modo que la comparación es exacta: misma
ráfaga, dos implementaciones.

Con eso, la memoria puede afirmar que el diagnóstico se ejecuta en el nodo como **hecho medido**
y no como viabilidad demostrada.

---

## 12. Trazabilidad

| Elemento | Ubicación |
| :--- | :--- |
| Exportador del modelo | [`server/analisis/exportar_modelo.py`](../../server/analisis/exportar_modelo.py) |
| Cabecera generada | `device/modelo_referencia.h` |
| Aritmética del detector | [`device/detector.h`](../../device/detector.h) |
| Casos de prueba reales | [`exportar_casos_prueba.py`](../../server/analisis/exportar_casos_prueba.py) |
| Verificación contra scikit-learn | [`device/test/test_detector.cpp`](../../device/test/test_detector.cpp) |
| Verificación de la integración | [`device/test/test_integracion.cpp`](../../device/test/test_integracion.cpp) |
| Esquema del canal nuevo | [`docs/DATA_SCHEMA.md`](../DATA_SCHEMA.md) |
| Selección del modelo | [informe de auditoría](2026-08-27-auditoria-metodologica-fase4.md) |

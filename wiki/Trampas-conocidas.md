# Trampas conocidas

Nueve defectos que ya se han cometido en este proyecto, con su síntoma y su corrección. Todos
tienen una cosa en común: **ninguno produjo un error visible**. O devolvían un número plausible,
o devolvían el resultado correcto por el motivo equivocado.

Es la página más útil del repositorio si vas a tocar el análisis.

---

## 1. Los picos espectrales vienen ordenados por amplitud

**Síntoma:** el coeficiente de variación de la frecuencia dominante era del 133 %, y un cociente
`f2_x / fdom_x` daba **9,0 en unas ráfagas y 0,111 en otras describiendo el mismo fenómeno
físico**.

**Causa:** el firmware ordena los tres picos por amplitud. En el activo con fallo el armónico
supera a la fundamental por un 2 % (0,2056 frente a 0,2016) en el 9 % de las ráfagas y le
arrebata la posición de dominante.

**Corrección:** reordenar por **frecuencia**, descartando antes los picos con amplitud inferior
al 20 % de la mayor. Las dos condiciones son necesarias: ordenar solo por frecuencia toma picos
de ruido de frecuencia baja por fundamental.

---

## 2. `bad_frames` y los contadores `total_*` son acumulados

**Síntoma:** un filtro de calidad que exigiera `bad_frames == 0` descartaba el **100 %** de las
ráfagas. Devolvía un conjunto vacío, no un aviso.

**Causa:** son contadores acumulados desde el arranque del nodo, no por ráfaga.

**Corrección:** filtrar solo con `retries` y `cont_rejects`, que sí son por ráfaga.

---

## 3. Un umbral absoluto de marcha/parada no vale para dos máquinas

**Síntoma:** episodios de marcha de **una sola ráfaga y cero minutos** de duración.

**Causa:** el umbral se fijó en 0,05 m/s² con 1,88 h de datos. Con 21 h se ve que el grupo de
parado llega hasta 0,06: **el umbral caía dentro del grupo de parado**. Y el valle es propio de
cada máquina — 0,199 en un activo, 0,060 en el otro.

**Corrección:** derivarlo de los datos separando los dos modos del logaritmo del valor eficaz.

---

## 4. Las características con unidades separan máquinas, no estados

**Síntoma:** un detector sobre `rms`, `peak` y `kurt` alcanzaba el **99,4 % de detección sin
haber empleado ninguna característica que contenga la firma del fallo**.

**Causa:** el nivel de vibración de los dos activos difiere en un factor 12,5.

**Corrección:** características adimensionales. Y para no perder sensibilidad a la amplitud,
normalizar por la mediana del **propio** activo en lugar de suprimir la magnitud.

> Una métrica excelente puede estar midiendo el atributo equivocado. Que el número sea alto no
> dice que el número sea el correcto.

---

## 5. Los reintentos del bus fabrican la firma del fallo

**Es el más peligroso de la lista.**

**Síntoma:** en el activo **sano**, con más de diez reintentos del bus I2C la mediana de picos
significativos pasa de 1 a 3 y la fundamental estimada se derrumba de 49 Hz a 20 Hz. Exactamente
la firma del fallo real.

**Causa:** una muestra corrupta inyecta ruido de banda ancha, y varios coeficientes del espectro
superan el umbral de significación.

| Reintentos | Con más de un pico | Fundamental |
| ---: | ---: | ---: |
| 0–3 | 0,4 % | 49,15 Hz |
| 11–20 | **93 %** | **20,03 Hz** |
| > 20 | **94 %** | **16,03 Hz** |

**Corrección:** el filtro de calidad **es parte del detector**, no un preproceso. El nodo debe
**negarse a emitir veredicto** con más de 3 reintentos.

**Consecuencia práctica:** soldar el conexionado sube de prioridad. No es solo pérdida de datos:
las ráfagas que pasan con 4–10 reintentos contaminan la característica que decide.

---

## 6. Sesgo de espionaje de datos en la selección de características

**Síntoma:** una regla sobre una sola característica parecía superar a los modelos de aprendizaje
automático. Y su tasa de falsos positivos era del 8,3 %.

**Causa:** la característica se eligió ordenando las candidatas por su separación **frente al
conjunto con fallo**, es decir usando el conjunto de evaluación para tomar una decisión de
diseño.

Dos consecuencias, ambas falsas:

1. La regla **no supera** a los modelos: dándoles únicamente esa característica, los seis
   candidatos convergen al mismo 8,3 %. Con una dimensión hay una sola frontera que localizar.
   **El mérito era de la característica, no del algoritmo.**
2. Esa característica se eligió conociendo el fallo, así que su ventaja no se transfiere a otro:
   resulta **ciega a 4 de las 5 direcciones** de fallo examinadas.

**Corrección:** partición cronológica por episodios y todas las decisiones sobre el conjunto
nominal. El protocolo limpio **elige un modelo distinto**, que es la prueba de que la elección
anterior estaba contaminada.

---

## 7. Descartar modelos por una restricción no medida

**Síntoma:** varios modelos se descartaron por «no embarcables», lo que empujaba la elección
hacia el más simple.

**Causa:** nunca se midió.

| Modelo | Memoria | Operaciones |
| :--- | ---: | ---: |
| Regla de un umbral | 8 B | 3 |
| Envolvente robusta | 840 B | 210 |
| Modelo seleccionado | 31,6 KB | 15 150 |
| Bosque de aislamiento | 274 KB | 4 800 |

La placa tiene **512 KB de SRAM y 8 MB de PSRAM**, y 15 150 operaciones a 240 MHz son ~0,1 ms
frente a una ráfaga cada 30 s. **Los cinco caben con amplio margen.**

---

## 8. Una covarianza casi singular por características redundantes

**Síntoma:** al portar la envolvente a precisión simple, el resultado se desviaba 37 unidades
sobre puntuaciones del orden de 19 000.

**Causa:** las cuatro bandas acústicas **suman 1 por construcción** — el firmware las normaliza.
Cuatro columnas con dependencia lineal exacta (medido: 1,000003 ± 5,9·10⁻⁵). El número de
condición de la covarianza era 1,4·10¹⁷ y la forma cuadrática sufría una cancelación de factor
45 000: se sumaban 883 millones para dar 19 463.

**Corrección:** eliminar una banda, que es `1 − b0 − b1 − b2` y no aporta información. La
condición baja a 6,5·10⁴. Y acumular la forma cuadrática en doble precisión.

> Este defecto **solo aparece al portar a un entorno sin doble precisión nativa**. En el equipo
> de análisis nunca se habría visto.

---

## 9. Comparar el nodo contra un modelo reajustado

**Síntoma:** el verificador reportaba 2 discrepancias de 20 entre el veredicto del nodo y el del
equipo de análisis.

**Causa:** el verificador **reajustaba el modelo con los datos de hoy**. Desde que se exportó el
modelo habían llegado más ráfagas, así que cambiaron las medianas, el conjunto de ajuste y el
umbral: se comparaba contra **otro modelo**, no contra el que lleva la placa.

**Corrección:** leer los parámetros del propio `modelo_referencia.h`. Es el mismo principio que
el sello de procedencia de la cabecera: si un firmware debe poder rastrearse a los datos que lo
produjeron, la verificación debe hacerse contra **esos** y no contra los de ahora.

Con la corrección: **20 de 20 veredictos coincidentes**.

---

## Dos defectos de procedimiento, no de código

**Un criterio por descarte se rompe con cada elemento nuevo.** «Todo lo que no acabe en
`-vibration.csv` es canal lento» se rompió en **dos sitios** al aparecer un tercer canal. En uno
de ellos —la rutina que archiva ficheros con cabecera desfasada— habría **movido los datos** del
canal nuevo. Los criterios se declaran de forma positiva.

**Un valor por omisión que es correcto la mitad de las veces es peor que ninguno.** El script de
sincronización tenía `admin` como usuario por omisión, y uno de los concentradores usa otro. El
síntoma —una petición de contraseña— parece un problema de red.

---

## El patrón

Ninguno de estos nueve dio un error. Devolvieron números plausibles, o el resultado correcto por
el motivo equivocado.

De ahí tres prácticas que el proyecto adopta:

1. **Verificar contra un valor esperado analítico**, no contra «parece razonable». La kurtosis de
   un seno es 1,5 y su valor eficaz A/√2: eso se comprueba, no se supone.
2. **Abortar antes que continuar** cuando el esquema no cuadra. Un fichero con la cabecera
   equivocada devuelve valores que un cargador acepta sin protestar.
3. **Declarar los criterios antes de mirar los datos.** Es lo que hace la campaña prerregistrada
   de fallo inducido.

# Registro de Campañas de Medida

Toda captura que vaya a usarse en la memoria del TFM debe quedar anotada aquí. Sin esta
anotación, un CSV es un fichero de números sin condiciones experimentales asociadas y no
sirve como evidencia.

## Plantilla

```
### EXP-NNN — <título breve>
- **Fecha/hora:** 2026-MM-DD HH:MM – HH:MM (Europe/Madrid)
- **Activo:** <equipo, modelo, ubicación>
- **Condición:** nominal | fallo inducido: <descripción>
- **Montaje del sensor:** <punto de fijación, tipo de acoplamiento>
- **Ficheros:** server/data/YYYY-MM-DD.csv (filas HH:MM–HH:MM)
- **Firmware:** <commit o versión>
- **Etiqueta (ground truth):** <clase para el modelo>
- **Observaciones:** <ruido externo, apertura de puerta, ciclos de deshielo, incidencias>
```

## Campañas

### EXP-003 — Fallo real: familia armónica del giro (8×, 9× y 10×)

> **AVISO — cifras revisadas.** Las de este bloque se calcularon con una definición de característica defectuosa y con 719 ráfagas. Ver **Corrección de EXP-003** al final del documento: son 815 ráfagas, y la firma no es una componente en 447,76 Hz sino los armónicos **8×, 9× y 10×** del giro (398, 448 y 497 Hz).

- **Fecha/hora:** 2026-08-26 11:44 – 18:01 (Europe/Madrid), 6,27 h continuas.
- **Activo:** segundo compresor del banco. **Presenta un fallo real, no inducido**, audible
  como un pitido constante.
- **Condición:** **fallo real en curso.** La referencia de verdad es perceptiva: el activo
  emite un tono audible de forma sostenida, apreciable sin instrumentación.
- **Montaje del sensor:** acelerómetro adherido con cinta, nodo B. Orientación con la
  gravedad en el eje X (`accX` ≈ 1,75 tras el remontaje del día 26; ver
  `server/data/README.md` para la identificación de nodos).
- **Ficheros:** `server/data/nodo-b-otro-compresor/fw-46col/2026-08-26-vibration.csv`
  (719 ráfagas) y `2026-08-26.csv` (21 858 tramas).
- **Firmware:** 46 columnas, con filtro paso bajo a 150 Hz en los estadísticos temporales,
  tres picos espectrales por eje y comprobación de continuidad.
- **Etiqueta (ground truth):** fallo, sin clasificar el modo.
- **Campaña de control:** [EXP-004](#exp-004) sobre el activo de referencia, en estado
  nominal, con el mismo firmware y en el mismo intervalo temporal.

**Firma del fallo**

| Magnitud | Valor |
| :--- | :--- |
| Frecuencia de giro | 49,745 Hz (CV 0,52 %) |
| Componente tonal | 447,76 Hz, presente en los tres ejes |
| **Relación con el giro** | **9,0030** (CV **0,07 %**) |
| Entero más próximo | 9, con desviación del 0,03 % |
| Presencia | 712 de 719 ráfagas (99 %) |
| Energía acústica en 250–1000 Hz | 0,987 (mediana) |
| Nivel acústico relativo | 1677 |

**La componente está enganchada al régimen de giro.** La relación entre la componente tonal y
la frecuencia fundamental presenta un coeficiente de variación del 0,07 %, **inferior al de
cada una de las dos frecuencias por separado** (0,52 % y 0,12 %). Una resonancia estructural
tendría frecuencia fija y su relación con el giro variaría al cambiar el régimen; aquí ocurre
lo contrario, de modo que la componente la genera el propio giro del motor. Corresponde al
noveno armónico.

**Confirmación por dos modalidades independientes**

| Magnitud | Activo con fallo | Activo de referencia |
| :--- | ---: | ---: |
| Energía acústica en 0–250 Hz | 0,012 | 0,947 |
| Energía acústica en 250–1000 Hz | **0,987** | 0,034 |
| Nivel acústico relativo | **1677** | 333 |
| Ráfagas con banda 250–1000 Hz dominante | 704 / 719 (97 %) | 7 / 216 (3 %) |
| Ráfagas con componente en 380–460 Hz | 712 / 719 (99 %) | 1 / 216 (0 %) |

El reparto de energía acústica está **invertido** entre ambos activos, y la componente tonal
que la vibración detecta cae en la banda donde se concentra el 98,7 % de la energía acústica
del activo con fallo. Las dos modalidades coinciden sin compartir sensor ni cadena de medida.

- **Observaciones:**
  - La componente **no aparece** en `rms`, `peak` ni `kurtosis`, porque el filtro paso bajo a
    150 Hz de los estadísticos temporales la elimina. Su detección depende por completo de
    los picos espectrales sin filtrar y de las bandas acústicas. Una versión del firmware que
    hubiese acotado la búsqueda espectral a la banda útil del acoplamiento, alternativa que
    se valoró, no habría registrado este fallo.
  - Se identificó inicialmente como resonancia del acoplamiento del sensor, hipótesis que la
    prueba de enganche al giro descarta. El indicio que llevó a revisarla fue la información
    del operador sobre el tono audible.
  - **Limitación de la comparación:** el activo con fallo y el de referencia son máquinas
    distintas, de modo que el contraste no permite separar el efecto del fallo del de la
    variabilidad entre ejemplares. La magnitud de la diferencia observada en el reparto
    acústico, de 0,03 frente a 0,99, es difícil de atribuir a esa variabilidad, pero la
    validación rigurosa exige las campañas de fallo inducido sobre el activo de referencia
    previstas en la Fase 5.
  - Salud del nodo en la ventana: 17 ráfagas descartadas (2,7/h), 48 tramas del canal lento
    descartadas, y entre 2 y 7 reinicios del microcontrolador detectados por retroceso de los
    contadores acumulados.
  - El eje X resulta utilizable en su totalidad: `kurt_x` dentro del intervalo sano en las 719
    ráfagas. Los ejes Y y Z quedan dominados por la componente del fallo, de modo que sus
    estadísticos no describen el giro.

### EXP-004 — Control en estado nominal con el firmware definitivo
- **Fecha/hora:** 2026-08-26 15:13 – 17:06 (Europe/Madrid), 1,88 h. **Captura en curso.**
- **Activo:** compresor de referencia (nodo A).
- **Condición:** nominal. Sin tono audible.
- **Montaje del sensor:** adherido al tubo de descarga; gravedad en el eje X
  (`accX` ≈ 10,20).
- **Ficheros:** `server/data/nodo-a-nevera-buena/fw-46col/2026-08-26-vibration.csv`
  (216 ráfagas hasta el momento) y `2026-08-26.csv`.
- **Firmware:** idéntico al de EXP-003, condición necesaria para que la comparación sea válida.
- **Etiqueta (ground truth):** nominal.

| Magnitud | Valor |
| :--- | :--- |
| Frecuencia de giro con el motor en marcha | 49,44 Hz |
| Valor eficaz con el motor en marcha | 0,59 m/s² (mediana de las ráfagas en marcha) |
| Ráfagas con la fundamental identificada | 89 de 216 |
| Energía acústica en 0–250 Hz | 0,947 |
| Componente en 380–460 Hz | 1 de 216 |
| Ráfagas descartadas | 0,10/min |

- **Observaciones:**
  - Sirve de **control de EXP-003**: mismo firmware, mismo intervalo temporal, activo del
    mismo tipo en estado nominal. Es lo que permite afirmar que la componente al noveno
    armónico no es un artefacto de la cadena de medida.
  - La proporción de ráfagas con la fundamental identificada, 89 de 216, corresponde al ciclo
    de marcha y parada del activo: la señal solo existe con el motor en funcionamiento.
  - Los coeficientes de variación de esta campaña se calculan sobre el conjunto completo, que
    mezcla marcha y parada, por lo que no son comparables con los de EXP-003 sin segmentar
    antes por estado. La segmentación queda pendiente de la Fase 4.
  - **Captura en curso.** Las cifras se actualizarán al cerrar la campaña.

### EXP-002 — Caracterización de la cadena de adquisición y del punto de medida

> **AVISO — atribución revisada.** Este bloque atribuye las componentes de 398-448 Hz a una resonancia del acoplamiento adhesivo. **Es falso**: son armónicos del giro del activo. Ver **Corrección de EXP-003** al final. Las mediciones de nivel y el efecto de las correcciones de firmware siguen siendo válidos.

- **Fecha/hora:** 2026-08-26 11:44 – 11:48 (Europe/Madrid)
- **Duración:** 4 min. Campaña **de caracterización, no de entrenamiento**: su objeto es
  verificar el firmware definitivo y cuantificar la limitación del acoplamiento, no producir
  el conjunto de datos del modelo.
- **Activo:** compresor del sistema de refrigeración doméstico del banco de pruebas.
- **Condición:** nominal, sin fallo inducido. Compresor en marcha (salto térmico de
  \mbox{5,7 °C} sobre el ambiente).
- **Montaje del sensor:** acelerómetro adherido con cinta al **tubo de descarga** del
  compresor (posición 2 de las evaluadas), no a la cúpula. El tubo está unido rígidamente al
  cuerpo de la bomba y transporta la pulsación sin atravesar su suspensión interna. Orientación: `accX` = 1,60 y `accZ` = 11,62 m/s².
  Fijación **no rígida**: limitación conocida y aceptada, ver observaciones.
- **Ficheros:** `server/data/nodo-b-otro-compresor/fw-46col/2026-08-26-vibration.csv` y
  `server/data/nodo-b-otro-compresor/fw-46col/2026-08-26.csv`. La ventana de la campaña son
  las 7 primeras ráfagas (11:44–11:48); el fichero contiene 245 en total, hasta las 13:53,
  correspondientes a la caracterización posterior de la resonancia.
- **Firmware:** con filtro paso bajo a 150 Hz en los estadísticos temporales, tres picos
  espectrales por eje y comprobación de continuidad con umbral de 6 m/s².
- **Etiqueta (ground truth):** nominal.
- **Fotografías del montaje:** `hardware/fotos/nevera baseline/`, registradas en
  `hardware/fotos/README.md`.

**Resultados de la caracterización**

| Magnitud | Valor |
| :--- | :--- |
| Frecuencia fundamental del compresor | 49,77 Hz (desviación 0,08; CV 0,15 %) |
| Identificada en | 6 de 7 ráfagas, siempre como **tercer** pico |
| Amplitud en la fundamental | 0,0660 m/s² (desviación 0,0049; CV 7,4 %) |
| Resonancia del acoplamiento, modo 1 | 446,9 – 448,3 Hz |
| Resonancia del acoplamiento, modo 2 | 397,2 – 398,5 Hz |
| Valor eficaz filtrado (0–150 Hz) | 0,062 m/s² (mediana) |
| Kurtosis filtrada | 2,48 – 7,35 |
| Duración de la captura | 1024 ms en las 7 ráfagas, sin desviación |
| Ráfagas descartadas / tramas descartadas | 2 / 1 |
| Reintentos | 71 en la ventana; mediana 1 por ráfaga, máximo 30 |
| Rechazos por continuidad | 17 |
| Ráfagas calculadas y no publicadas | 0 |

- **Observaciones:**
  - La fundamental del compresor **no** es el pico dominante del espectro: aparece como
    tercer pico, por detrás de los dos modos de la resonancia del acoplamiento adhesivo.
    Con la versión anterior del firmware, que solo publicaba el pico dominante, esta
    información se perdía en el nodo y no era recuperable en el hub.
  - La resonancia se lleva del orden del 95 % de la energía: el valor eficaz sin filtrar
    era de 0,35 m/s² frente a 0,062 filtrado. Ese contraste cuantifica la limitación del
    acoplamiento.
  - Con un coeficiente de variación del 7,4 % en la amplitud de la fundamental, un cambio
    superior al 21 % (3σ) resulta detectable. Los modos de fallo previstos en la Fase 5
    alteran la amplitud del primer armónico en factores de 2 a 10, por lo que quedan dentro
    del margen.
  - **Fuera de alcance con este montaje:** la detección de deterioro incipiente de
    rodamientos por impulsividad, que reside por encima de la banda fiable de 0–150 Hz.
  - La ráfaga con 30 reintentos presenta la kurtosis más alta de la ventana (7,35), lo que
    confirma que los contadores de salud correlacionan con la calidad de la medida y sirven
    como criterio objetivo de filtrado del conjunto de datos.

### EXP-001 — Piloto corto en condición nominal (PLANIFICADA, pendiente de ejecutar)
- **Fecha/hora:** *(pendiente — rellenar con la ventana real HH:MM–HH:MM al ejecutarla)*
- **Duración objetivo:** ~4 h continuas. Se reduce deliberadamente frente a las ≥24 h de
  baseline de la Fase 3: el objetivo de esta campaña es validar el pipeline completo
  (captura → hub → CSV) con la corrección de continuidad activa, no producir el dataset de
  entrenamiento definitivo. La campaña de 24 h queda para cuando el montaje del sensor esté
  fijado de forma definitiva (ver limitaciones).
- **Activo:** compresor del sistema de refrigeración doméstico (banco de pruebas).
- **Condición:** nominal, sin fallo inducido.
- **Montaje del sensor:** el actual (provisional, sin acoplamiento rígido al chasis) —
  **limitación conocida y aceptada para este piloto**, no definitiva. Los valores eficaces
  medidos hasta ahora (0,07–0,38 m/s² con el compresor en marcha) son bajos para el activo;
  ver riesgo correspondiente en `ROADMAP.md`.
- **Ficheros:** *(pendiente — `server/data/YYYY-MM-DD-vibration.csv` y `.csv` del canal
  lento, con el rango de filas de la ventana real)*
- **Firmware:** versión con comprobación de continuidad entre muestras (`isContinuous`,
  `ACC_STEP_MAX_MS2` = 3 m/s², contador `cont_rejects`/`total_cont_rejects`) y contador de
  ráfagas no publicadas (`unpublished_bursts`). Repositorio sin control de versiones (no es
  un repositorio git), así que se identifica por fecha de este registro: 2026-08-25.
  **Pendiente de verificar en placa real** — sin `arduino-cli` en el equipo de desarrollo,
  el cambio no se ha compilado contra el toolchain ESP32-S3 antes de subirlo.
- **Etiqueta (ground truth):** nominal.
- **Observaciones / limitaciones conocidas a documentar en la memoria si se usa este dato:**
  - Fijación mecánica del sensor provisional, no definitiva (ver arriba).
  - Conexionado del sensor no soldado; tasa de reintentos observada ≈37/min con el
    compresor en marcha.
  - Reinicio no explicado del nodo observado en sesiones previas (hipótesis: caída de
    tensión); vigilar `total_retries`/`total_cont_rejects` por si se reinician a cero
    durante la campaña.
  - Canal acústico (`aud_*`) no aporta información en el montaje actual (mide vibración
    estructural, no sonido) — excluir de las características si se entrena un modelo con
    este dato.
  - `fdom_y` ≈ 448 Hz observado de forma recurrente sin explicación confirmada — pendiente
    de investigar; no usar `fdom_y`/`adom_y` como característica hasta aclararlo.
  - Ninguna de estas limitaciones invalida el piloto como prueba del *pipeline*; sí
    invalidan sus datos como *baseline* definitivo para el modelo (Fase 4).

---

## Análisis derivado

| Análisis | Campañas | Script | Resultado |
| :--- | :--- | :--- | :--- |
| Baseline de detección de anomalías | EXP-003 vs **EXP-005** | [`server/analisis/`](../server/analisis/) | 656/656 detectadas. Validación cruzada por episodios: 0,5 % de falsos positivos de media, 8,3 % en el peor arranque. Ver EXP-005 al final |

**Advertencia sobre este análisis.** Un detector ajustado sobre características con unidades
físicas (`rms`, `peak`, `kurt`) alcanza el 99,8 % de detección **sin haber empleado ninguna
característica que contenga la firma del fallo**. El nivel de vibración de los dos activos
difiere en un factor 5,5, de modo que separa las dos máquinas y no el estado de una de ellas.
Toda métrica obtenida sobre este par debe usar características adimensionales y declarar que
el contraste es entre máquinas distintas.

**Rendimiento de captura.** Una hora sobre el activo nominal rinde **24 ráfagas utilizables**
y una hora sobre el activo con fallo, 99. La diferencia es el ciclo de trabajo (27 % frente a
99 % de tiempo en marcha), no la calidad de la medida, que es equivalente. Toda campaña
nominal debe dimensionarse sobre las 24/h.

---

## Corrección de EXP-003 (2026-08-26, tras ampliar la captura a 815 ráfagas)

Las cifras publicadas inicialmente para EXP-003 se calcularon con una definición de
característica **defectuosa** y quedan sustituidas por las siguientes. Se consigna el error
porque es instructivo.

**El defecto.** Los cocientes se calculaban como `f2_x / fdom_x`, y el firmware publica los
tres picos **ordenados por amplitud**. En 60 de 676 ráfagas el armónico del fallo supera a la
fundamental del giro por un 2 % (0,2056 frente a 0,2016) y pasa a ocupar la posición de pico
dominante: el mismo fenómeno físico daba un cociente de 9,0 en unas ráfagas y de 0,111 en
otras. `fdom_x` aparentaba un CV del 133 %.

**La corrección.** Los picos se reordenan por **frecuencia**, descartando previamente los de
amplitud inferior al 20 % de la mayor —que son ruido espectral y con frecuencia caen por debajo
de la fundamental—. Verificado entre el 15 % y el 30 %: el resultado no depende del umbral.

**Cifras corregidas.**

| Magnitud | Valor |
| :--- | :--- |
| Duración | 7,14 h, 815 ráfagas, 676 utilizables, **2 episodios de marcha útiles** |
| Frecuencia de giro | 49,745 Hz, CV **0,12 %** |
| Componentes tonales | **398, 448 y 497 Hz** = armónicos **8×, 9× y 10×** |
| Desviación respecto del entero | < 0,05 % |
| Cociente del 9.º armónico | 9,0042, CV 0,137 % (n = 429) |
| Presencia | 659/676 ráfagas con tres picos significativos (97 %) |
| Picos significativos | 3 (frente a 1 del activo de referencia, separación 6,90 sd) |

**Lo que mejora respecto de la versión anterior.** No es una componente aislada sino una
**familia armónica** de tres términos simultáneos en múltiplos enteros exactos. Una resonancia
estructural no produce eso, así que el argumento ya no depende de comparar coeficientes de
variación —comparación que era discutible— sino de la coincidencia de tres armónicos con la
serie del giro.

**Límite de la instrumentación que este análisis revela.** El firmware publica tres picos por
eje, uno de ellos la fundamental, de modo que solo caben dos armónicos por ráfaga. La pareja
registrada varía (8× y 9× en 401 ráfagas, 9× y 10× en 235). Con tres picos no se puede
caracterizar una familia armónica de más de dos componentes.

---

### EXP-005 — Campaña de referencia prolongada del activo nominal

- **Objetivo:** obtener un conjunto de estado nominal con cobertura de varios ciclos de
  marcha/parada, para calibrar el umbral del detector y hacer posible la validación cruzada por
  episodios, que con EXP-004 no lo era.
- **Activo:** compresor de referencia (nodo A, `|a|` = 10,33), en uso doméstico normal.
- **Fecha/hora:** 2026-08-26 15:13 – 2026-08-27 12:46 (Europe/Madrid), **21,54 h continuas**.
- **Firmware:** `fw-46col`, sin modificaciones respecto de EXP-003 y EXP-004.
- **Ficheros:** `server/data/nodo-a-nevera-buena/fw-46col/2026-08-26-vibration.csv` (866) y
  `2026-08-27-vibration.csv` (1241), más los dos del canal lento (75 308 tramas). Sin bytes NUL.
- **Rendimiento:** 2107 ráfagas, 758 con el compresor en marcha (36 %), **505 utilizables**
  tras el filtro de calidad, en **24 episodios de marcha**. 23 útiles por hora.

| Magnitud | Valor |
| :--- | :--- |
| Frecuencia de giro | 49,15 Hz |
| Picos espectrales significativos | **1** en 503 de 505 ráfagas |
| Energía acústica 0–250 Hz | 0,870 |
| Umbral marcha/parada derivado de los datos | 0,1994 m/s² |
| Ciclo nocturno | 9 marchas de 30 min cada 83,8 min (36 % de trabajo) |

El tramo de tarde y noche presenta arranques irregulares de 4 a 9 min, atribuibles a aperturas
de puerta. **Esa heterogeneidad no es un defecto de la campaña**: es la variabilidad que el
modelo debe tolerar, y es lo que la validación por episodios pone a prueba.

#### Tres correcciones de método que esta campaña obligó a hacer

Se consignan porque las tres invalidaban resultados anteriores y ninguna era visible con las
1,88 h de EXP-004.

**1. El umbral marcha/parada estaba mal.** Se había fijado en 0,05 m/s² a partir de EXP-004.
Con 21 h se ve que el grupo de parada del nodo A llega hasta 0,06 y que el valle real está entre
0,06 y 0,30: **el umbral caía dentro del grupo de parado**, y producía episodios espurios de una
sola ráfaga. Además el valle es propio de cada máquina (0,1994 en el nodo A, 0,0595 en el nodo
B), de modo que ningún valor absoluto sirve para las dos. Se deriva ahora de los datos separando
los dos modos del logaritmo del valor eficaz, sin hiperparámetros.

**2. Los reintentos del bus I2C fabrican la firma del fallo sobre un activo sano.** Es la
corrección importante. En este activo, que está en estado nominal:

| `retries` | n | con `n_picos` > 1 | `f0` mediana |
| ---: | ---: | ---: | ---: |
| 0 | 261 | 0,4 % | 49,15 Hz |
| 1–3 | 206 | 0,5 % | 49,17 Hz |
| 4–5 | 53 | 8 % | 49,25 Hz |
| 6–10 | 48 | 31 % | 49,16 Hz |
| 11–20 | 46 | **93 %** | **20,03 Hz** |
| > 20 | 69 | **94 %** | **16,03 Hz** |

Una muestra corrupta inyecta ruido de banda ancha y varios coeficientes del espectro superan el
umbral de significación. El corte del filtro se recalibró de 5 a **3 reintentos**: conserva las
ráfagas con un 0,4 % de espurias, la misma tasa que exigir cero pero con un 79 % más de datos.

**Consecuencia para el despliegue:** el filtro de calidad es parte del detector y no un
preproceso. El nodo debe **negarse a emitir veredicto** sobre una ráfaga con más de 3
reintentos, en lugar de juzgarla.

**3. La firma de EXP-003 no es un artefacto de ese defecto.** Comprobado restringiendo ambos
conjuntos a ráfagas con **cero reintentos**:

| Conjunto | n | `n_picos` = 1 / 3 | `f0` |
| :--- | ---: | :--- | ---: |
| Nodo A, sano | 278 | 277 / 1 | 49,15 Hz |
| Nodo B, con fallo | 443 | 0 / 430 | 49,76 Hz |

Cocientes armónicos del nodo B sin ningún reintento: **8,0016 con CV del 0,029 %** y 9,0035 con
CV del 0,106 %. La firma del nodo B es además idéntica con reintentos y sin ellos (8,003 frente
a 7,998), mientras la del nodo A se derrumba. **Un artefacto del bus no puede producir un valor
que el propio bus no altera.**

#### Resultado del detector con protocolo libre de sesgo de espionaje

Las cifras publicadas antes de esta campaña se obtuvieron **usando el conjunto con fallo para
tomar decisiones de diseño**: la característica `n_picos` se eligió ordenando las candidatas por
su separación *frente al fallo*. Eso es espionaje de datos.
[`server/analisis/protocolo.py`](../server/analisis/protocolo.py) impone la separación estricta.

Partición **cronológica por episodios** del conjunto nominal: los 16 más antiguos para
desarrollo, los 8 más recientes para prueba. Cronológica y no aleatoria porque reproduce la
situación real y no filtra información del futuro.

| Magnitud | Valor |
| :--- | ---: |
| Modelo elegido **sin mirar el fallo** | **LOF** |
| Direcciones de fallo cubiertas | 5 de 5 |
| Falsos positivos en desarrollo | 6,3 % |
| **Falsos positivos en los episodios de prueba** | **7,8 %** |
| **Detección sobre el activo con fallo** | **100 %** |

**El protocolo elige un modelo distinto** del que se había elegido a mano. Esa discrepancia es
la evidencia de que la elección anterior estaba contaminada.

#### Limitaciones que subsisten

- **El contraste sigue siendo entre máquinas distintas.** Las características adimensionales
  acotan ese sesgo; no lo eliminan. La diferencia de nivel entre los dos activos es de un factor
  12,5. Solo un fallo inducido sobre el activo de referencia lo elimina.
- **El activo con fallo tiene 3 episodios**, de los que 2 son aprovechables. La validación por
  episodios se aplica al lado nominal.
- **El modo de fallo no está identificado.** Hay una firma caracterizada, no un mecanismo.
- **El 76 % de las ráfagas del nodo A se descarta**, en su mayoría por el compresor parado
  (36 % en marcha) y el resto por reintentos del bus. Soldar el conexionado recuperaría esa
  segunda parte.

---

### EXP-006 — Fallo inducido por obstrucción de ventilación (PRERREGISTRADA)

> **Los criterios de esta campaña se declaran ANTES de ejecutarla.** Es lo contrario del sesgo
> de espionaje que se corrigió en la Fase 4: en lugar de mirar los datos y decidir después qué
> demuestran, se declara antes qué contaría como detección y qué como no detección. En la memoria
> queda constancia de que se hizo en este orden.

**Estado:** pendiente de ejecutar. Requiere el detector flasheado en el nodo A.

#### Motivación

Es la única vía para cerrar la limitación de mayor peso del trabajo: **los dos activos medidos
son máquinas distintas**, de modo que el contraste no separa el efecto del fallo del de la
variabilidad entre ejemplares. Un fallo inducido sobre el activo de referencia sí lo separa.

Y valida dos cosas que hoy no están validadas:

- **El canal térmico**, que no se ha contrastado contra ningún fallo real. Se añadió al detector
  con tres características (`dif_rel`, `grad_motor`) sin ninguna evidencia experimental.
- **La detección en hardware**, no en el equipo de análisis.

Se elige la obstrucción de ventilación entre los modos posibles por tres razones: es reversible
sin dañar el activo, es el modo que **no altera la firma vibratoria** —de modo que pone a prueba
el planteamiento multimodal— y no exige desmontar el sensor, con lo que el montaje permanece
idéntico al de EXP-005 y las series son comparables.

#### Protocolo

| Fase | Duración | Condición |
| :--- | ---: | :--- |
| 1. Referencia en hardware | 3–4 h | Nevera normal, detector corriendo |
| 2. Obstrucción | 2 h | Rejilla del condensador **parcialmente** tapada |
| 3. Recuperación | 1 h | Rejilla despejada |

La fase 1 **no es opcional**: sin un «antes» medido en la placa, la comparación se haría contra
una simulación en el equipo de análisis y no contra el nodo.

La fase 3 tampoco: un detector que señala el fallo pero **no regresa a nominal** al retirarlo
está defectuoso, y demostrar la recuperación es parte del resultado.

#### Criterio de parada por seguridad

Vigilar `motorTemp` en el canal lento. **Si supera 70 °C, retirar la obstrucción de inmediato.**
No sellar la rejilla por completo y no dejar la campaña sin supervisión.

```bash
mosquitto_sub -h 10.42.0.1 -t 'fridge/sensors' -v
```

#### Qué se espera, declarado de antemano

| Magnitud | Predicción |
| :--- | :--- |
| `dif_rel` | **Sube.** El condensador no evacúa calor |
| `grad_motor` | **Sube** durante la fase 2 |
| Ciclo de trabajo | **Se alarga.** El compresor no alcanza consigna |
| `rms_x`, `kurt_x`, `n_peaks` | **Sin cambio apreciable.** Este modo no altera la vibración |
| `aud_b0..b2` | Sin cambio apreciable |

#### Qué contaría como detección

**Detección positiva:** el nodo emite al menos un aviso (`notify` = 1) durante la fase 2 y
ninguno durante las fases 1 y 3.

**No detección:** ningún aviso durante la fase 2, con `dif_rel` habiéndose desplazado.

**Resultado no concluyente:** avisos también en la fase 1 o en la 3, o `dif_rel` sin desplazarse
—en cuyo caso la obstrucción no llegó a alterar el estado térmico y la campaña no prueba nada
sobre el detector.

#### Y si no detecta, también es resultado

Una no detección significa que las características térmicas no se desplazan lo suficiente con
esta perturbación, e informa del límite real del sistema. **Se escribirá en la memoria en esos
términos.** Lo que no se hará es decidir después de ver los datos qué contaba como éxito.

#### Registro al ejecutar

Anotar aquí: fecha y hora de cada fase, ficheros generados, `motorTemp` máxima alcanzada, número
de avisos por fase, y desplazamiento medido de cada característica.

---

### EXP-007 — Verificación del detector embarcado en hardware (21,56 h continuas)

- **Fecha/hora:** 2026-08-27 14:10 – 2026-08-28 11:43 (Europe/Madrid), 21,56 h continuas.
- **Activo:** compresor de referencia (nodo A, `nodo-a-nevera-buena`), en estado nominal en banco de ensayos.
- **Montaje del sensor:** acelerómetro MPU-6050 adherido al tubo de descarga, sensor DS18B20 y micrófono INMP441.
- **Ficheros:** `server/data/nodo-a-nevera-buena/fw-46col/2026-08-27-status.csv`, `2026-08-27-vibration.csv`, `2026-08-27.csv`, `2026-08-28-status.csv`, `2026-08-28-vibration.csv`, `2026-08-28.csv` (162 670 filas en total acumuladas).
- **Firmware:** `fw-46col` con detector Local Outlier Factor (LOF) embarcado en C++, guardián de reintentos I2C, filtro de calidad y publicación del canal de estado en `fridge/status`.
- **Etiqueta (ground truth):** nominal.

**Resultados de la verificación experimental en placa**

| Magnitud | Valor medido en hardware |
| :--- | :--- |
| Duración de la captura continua | **21,56 h** |
| Veredictos totales emitidos por el nodo | **2536** |
| Veredicto `health = not_evaluable` (reposo/bus) | 1623 (64,0 %) |
| Veredicto `health = nominal` | 749 (29,5 %) |
| Veredicto `health = anomaly` | 164 (6,5 %) |
| Ráfagas evaluables (compresor en marcha) | **913** (36,0 % del total) |
| Ráfagas anómalas sobre evaluables | 164 / 913 (18,0 %) |
| Avisos emitidos tras histéresis (`notify = 1`) | **14 avisos** (concentrados en ciclos nocturnos) |
| Racha máxima de anomalías consecutivas | 11 |
| **Tiempo de inferencia (mediana)** | **14 µs** |
| **Tiempo de inferencia (p99 / máx)** | **1380 µs / 1942 µs** (1,38 ms / 1,94 ms) |
| **Ocupación del ciclo de 30 s** | **0,00005 %** |
| **Paridad Nodo (MCU) vs. PC** | **908 de 913 ráfagas coincidentes (99,45 %)** |
| Diferencia mediana de puntuación LOF | 0,00134 (máx 0,13216 en frontera) |
| Discrepancias por borde de decisión | 5 de 913 (0,55 %) |

- **Observaciones:**
  - Demuestra empíricamente la viabilidad de la inferencia en el borde en un microcontrolador ESP32-S3: el cómputo de LOF y extracción de características consume fracciones de milisegundo (<2 ms en el peor caso).
  - La paridad matemática entre la ejecución en microcontrolador y el recálculo en servidor/PC supera el 99,4 %, quedando las discrepancias acotadas a ráfagas extremadamente próximas al hiperplano de decisión (distancia mínima de 0,00124).
  - **La tasa de ráfagas marcadas subió del 7,8 % medido fuera de muestra al 14,0 %, y no está
    explicada.** Ninguna característica lo justifica por sí sola: la mayor desviación entre las
    ráfagas anómalas y las nominales no alcanza 0,8 sd en ninguna de las catorce, de modo que es
    un efecto multivariante.
  - **Los avisos NO se concentran en franjas nocturnas.** Comprobado: la tasa es del 13,7 % entre
    las 00:00 y las 08:00 y del 14,3 % en el resto de la jornada. Están repartidos de forma
    uniforme, y una atribución a la deriva térmica ambiental carece de apoyo en estos datos.
  - Lo que sí se ha podido acotar: anulando las tres bandas acústicas, la tasa de ráfagas
    marcadas baja del 14,0 % al **5,7 %**. El canal acústico aporta 8,3 puntos, si bien por una
    dispersión distribuida y no por sucesos intensos aislados (ver EXP-008).

---

### EXP-008 — Apertura de puerta: ciclo completo de perturbación, detección y recuperación

- **Fecha/hora:** 2026-08-28, apertura entre 12:09 y 12:11. Captura continua hasta las 14:26.
- **Activo:** compresor de referencia (nodo A), **sano durante toda la campaña**.
- **Condición:** puerta abierta 2 min. La perturbación es del entorno, no una degradación.
- **Ficheros:** `server/data/nodo-a-nevera-buena/fw-46col/2026-08-28-{status,vibration}.csv`
  y `2026-08-28.csv`.
- **Etiqueta:** nominal en cuanto al estado mecánico; **sobrecarga operativa** inducida.

> **No estaba prerregistrada.** EXP-006 declara criterios de antemano para una obstrucción de
> ventilación, que es otra perturbación. Los de EXP-008 no se declararon antes.

> **Aviso sobre las marcas de tiempo.** El nodo no tiene reloj de tiempo real y las marcas las
> pone el concentrador, cuyo reloj no está sincronizado con una referencia externa. Los
> intervalos y las duraciones son válidos —salen de un solo reloj— pero la alineación con la
> hora civil no está verificada.

#### El ciclo completo

| Fase | min | dif °C | motor °C | nominal | anomaly | no eval | avisos |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 · marcha previa | 37 | 15,26 | 41,0 | 60 | 13 | 1 | 0 |
| 2 · **puerta abierta** | 2 | 19,48 | 46,7 | 1 | 3 | 0 | **1** |
| 3 · subida térmica | 30 | 20,64 | 48,8 | 35 | 10 | 0 | 0 |
| 4 · **anomalía sostenida** | 61 | **24,69** | **51,8** | 3 | **108** | 0 | **3** |
| 5 · compresor parado | 40 | 13,45 | 44,5 | 0 | 2 | 78 | 0 |
| 6 · **nueva marcha** | 5 | 14,88 | 41,0 | **9** | 1 | 0 | **0** |

**Efecto físico:** 130 min de marcha continua (11:32–13:42) frente a una mediana nominal de
**31 min**. Cuatro veces lo normal, con el diferencial 9,4 °C por encima.

**Recuperación observada:** a las 14:22 arranca con la puerta cerrada y vuelve a `nominal` —
9 de 10 ráfagas, racha en 0, cero avisos, diferencial en 14,88 °C frente a los 15,26 °C de
referencia.

#### Dos fenómenos con significado opuesto

**El aviso de las 12:10:40 es un FALSO POSITIVO.** Una prueba de ablación lo establece: se anula
cada grupo de características y se recalcula.

| Configuración | Ráfagas detectadas |
| :--- | ---: |
| Sin anular nada | 3 de 3 |
| Anulando lo **térmico** | 3 de 3 |
| Anulando lo **acústico** | **0 de 3** |
| Anulando el nivel | 3 de 3 |
| Anulando la forma de onda | 3 de 3 |

Solo el canal acústico es necesario. Lo que el nodo detectó fue el sonido de la habitación con
la puerta abierta: `aud_b1` +2,70 sd, `aud_b0` −2,64 sd, y la firma vibratoria sin desplazar.
Abrir la puerta es el suceso más frecuente en la vida de un aparato doméstico.

**La anomalía sostenida a partir de +30 min SÍ es una detección legítima.** 108 de 111 ráfagas
marcadas durante una hora, racha de 61 consecutivas, con el diferencial subiendo de forma
monótona hasta 25,09 °C. El retraso de 30 min no es un defecto: es la constante de tiempo del
fenómeno, porque el estado térmico de un compresor no cambia en 90 s.

#### Qué establece y qué no

**Sí:** el detector señala una condición anómala real **del propio activo de referencia** y deja
de señalarla cuando cesa. El ciclo entero está observado.

**No:** no es un fallo mecánico. El compresor no se ha degradado, ha trabajado el cuádruple
porque se le metió calor. Es una **sobrecarga operativa**. La limitación de mayor peso del
trabajo —que el activo averiado y el de referencia son máquinas distintas— sigue intacta en lo
que respecta a los *fallos*.

#### El coste del canal acústico, cuantificado

Anulando las tres bandas y recalculando sobre la captura completa:

| Configuración | Ráfagas marcadas |
| :--- | ---: |
| Con bandas acústicas | **14,0 %** |
| Sin bandas acústicas | **5,7 %** |
| El evento de la puerta, sin acústica | 0 de 3 |

Son **8,3 puntos**. Y el mecanismo no es el que cabría suponer: solo el 10 % de las ráfagas
anómalas presenta un valor extremo de `aud_b1` —frente al 5 % que correspondería por
construcción— de modo que la contribución no procede de sucesos intensos sino de una dispersión
distribuida que la campaña de referencia no capturó.

El canal tiene por tanto las dos caras medidas: aportó la confirmación independiente del fallo
real de EXP-003 (0,986 frente a 0,034), procedente de un sensor que no comparte cadena con el
acelerómetro, y cuesta 8,3 puntos frente a perturbaciones del entorno.

#### Un defecto de la política de avisos, y su corrección sin reflashear

El episodio produjo **4 avisos para un solo suceso**: cuando una ráfaga nominal se cuela en
medio de una anomalía sostenida —ocurrió 3 veces— la racha se reinicia y el sistema vuelve a
notificar.

La histéresis es una **política de notificación**, no una medida: no altera `health`, `lof`,
`env` ni `n_peaks`, solo `notify` y `streak`. Y es una función pura de la secuencia de
veredictos, de modo que **cualquier alternativa se evalúa sobre los datos ya capturados, sin
reflashear el nodo ni repetir campañas** ([`politica_avisos.py`](../server/analisis/politica_avisos.py)).

| Tiempo mínimo entre avisos | Avisos totales | Del episodio | Primera detección |
| ---: | ---: | ---: | :--- |
| 0 min (actual) | 18 | 4 | 12:10:40 |
| 30 min | 12 | 3 | 12:10:40 |
| 60 min | 12 | 2 | 12:10:40 |
| 120 min | **7** | **1** | 12:10:40 |

**Se descartó una primera propuesta**, y conviene consignarlo: exigir varias ráfagas *nominales*
consecutivas para rearmar no reduce los avisos (14, 16 y 19 según el valor, frente a 18 del
actual). El motivo es que al no romper la racha con una nominal aislada, la racha de anomalías se
acumula más rápido y el aviso se dispara antes.

Lo que sí funciona es el tiempo mínimo entre avisos, que es deduplicación y no
insensibilización: la primera detección de cada episodio nunca se pierde.

**Contrapartida declarada:** un fallo que apareciera dentro de la ventana de silencio quedaría
sin notificar hasta que expirase. Con un ciclo de trabajo de unos 85 min, un silencio de 120 min
abarca más de un ciclo completo, de modo que el valor no es trasladable a otro activo sin
repetir la medida sobre el suyo. Es una decisión de política de operación y no una elección
técnica.

**No se ha modificado el firmware.** Cambiar la política a mitad de una serie haría que la
columna `notify` significase algo distinto antes y después, introduciendo una discontinuidad en
un registro que hasta ahora es homogéneo.


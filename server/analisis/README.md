# Pipeline de análisis — Fase 4

Detección de anomalías sobre las características que publica el nodo. Este documento recoge
las decisiones de cada etapa y **por qué** son esas. Los umbrales viven en
[`pipeline.py`](pipeline.py), no aquí, para que no puedan divergir.

```
manifiesto.json ──► carga ──► limpieza ──► segmentación ──► características ──► modelo
                      │          │             │                  │               │
                   candado    centinelas    episodios        adimensionales   selección
                  firmware    y NUL         de marcha        por diseño       por criterios
```

## Ejecución

```bash
.venv/bin/pip install -r server/requirements-analisis.txt   # solo en el portátil
.venv/bin/python server/analisis/pipeline.py                 # etapas 1-4: qué datos hay
.venv/bin/python server/analisis/comparar_modelos.py         # etapa 6: qué modelo, y validación
.venv/bin/python server/analisis/cobertura_modos.py          # puntos ciegos (datos sintéticos)
.venv/bin/python server/analisis/baseline_anomalias.py       # el detector elegido
```

---

## 1. Estudio del problema

Detección **no supervisada de una clase**. No es un clasificador: se ajusta un modelo de lo
que es normal y se marca lo que se desvía. El motivo es que los fallos son escasos, variados
y no se conocen de antemano, así que no hay conjunto etiquetado de fallos con el que entrenar.

Y hay una restricción que condiciona todo lo demás: **la inferencia final debe caber en el
ESP32**. No es un detalle de implementación, es la tesis del TFM. Un modelo excelente que
exija la Raspberry Pi encendida no resuelve el problema planteado.

## 2. Datos

| Conjunto | Origen | Ráfagas útiles | Episodios | Papel |
| :--- | :--- | ---: | ---: | :--- |
| Nominal | `nodo-a-nevera-buena/fw-46col` | 467 | **22** | Ajuste |
| Fallo | `nodo-b-otro-compresor/fw-46col` | 656 | 2 | Evaluación |

Las series se leen de [`manifiesto.json`](../data/manifiesto.json), no recorriendo el árbol.
Dos candados en la carga, ambos probados:

1. **Filtro por firmware.** Solo `fw-46col`. Las versiones anteriores publican `rms`, `peak` y
   `kurt` sin filtrar y un único pico espectral: son **definiciones distintas de la misma
   magnitud** y mezclarlas no significa nada.
2. **Comprobación del número de columnas de cada CSV.** Es el candado que importa, porque
   cubre el caso que ya ocurrió: un fichero con cabecera desalineada dentro de un directorio
   correcto. Leído con la cabecera equivocada devuelve `rms_x` = 7 y `aud_b3` = 0,986, valores
   que un cargador acepta sin protestar. El pipeline **aborta**, no avisa.

El candado de firmware se aplica **solo al canal de ráfaga**. El canal lento publica las mismas
10 columnas en todas las versiones, así que excluirlo descartaría en silencio 20,6 h de datos
térmicos válidos: con la excepción, la cobertura térmica pasa de 19 h a **40,5 h**.

## 3. Limpieza y preprocesado

**Bytes nulos.** Se retiran al leer. Son huecos del sistema de ficheros por parada sucia del
concentrador: bloques reservados cuyos datos nunca se escribieron. Van a reaparecer, porque el
registrador vuelca con `flush()` y no con `fsync()`.

**Centinelas.** `tempExt` = −127 (DS18B20 sin responder) y `motorTemp` = 0 (lectura del MPU
fallida). Un solo −127 arrastra la media térmica de la jornada entera.

**Duplicados de `ts`.** Aparecen al consolidar fragmentos de varias descargas.

**Filtro de calidad.** `retries` ≤ 5, `cont_rejects` ≤ 2, `kurt_x` en [1, 20]. Va **separado**
de la limpieza a propósito: la fracción descartada es un resultado que hay que declarar, no un
detalle interno.

> **Solo contadores por ráfaga.** `bad_frames` y los contadores con prefijo `total_` son
> **acumulados desde el arranque del nodo**. Exigirles cero descarta el 100 % de las
> observaciones. Es el error más fácil de cometer aquí y no da ningún síntoma: devuelve un
> conjunto vacío, no un aviso.

### Este filtro no es limpieza: es parte del detector

**Los reintentos del bus I2C fabrican la firma del fallo sobre un activo sano.** Medido sobre el
nodo A, que está en estado nominal:

| `retries` | n | con `n_picos` > 1 | `f0` mediana |
| ---: | ---: | ---: | ---: |
| 0 | 261 | 0,4 % | 49,15 Hz |
| 1–3 | 206 | 0,5 % | 49,17 Hz |
| 4–5 | 53 | 8 % | 49,25 Hz |
| 6–10 | 48 | 31 % | 49,16 Hz |
| 11–20 | 46 | **93 %** | **20,03 Hz** |
| > 20 | 69 | **94 %** | **16,03 Hz** |

Una muestra corrupta inyecta ruido de banda ancha y varios coeficientes del espectro superan el
umbral de significación. El corte se calibró en **3 reintentos**: conserva 467 ráfagas con un
0,4 % de artefactos, la misma tasa que exigir cero, con un 79 % más de datos.

**Consecuencia para el despliegue:** el ESP32 debe **negarse a emitir veredicto** sobre una
ráfaga con más de 3 reintentos, no juzgarla.

**Y la firma del nodo B no es este artefacto.** Restringiendo ambos conjuntos a cero reintentos:
el nodo A da un pico en 260 de 261 ráfagas y el nodo B tres en 430 de 443, con cocientes
armónicos de **8,0016 (CV 0,029 %)** y 9,0035 (CV 0,106 %). La firma del nodo B es además
idéntica con reintentos y sin ellos (8,003 frente a 7,998), mientras la del nodo A se derrumba.
Un artefacto del bus no puede producir un valor que el propio bus no altera.

**Reinicios del nodo.** Un retroceso en un contador acumulado indica reinicio, no error de
lectura. Se marca la fila pero **no se descarta**, y deliberadamente **no corta un episodio**:
un reinicio interrumpe la *observación*, no la marcha del compresor. Cortar por reinicio
presentaría como independiente lo que es el mismo estado de la máquina — con los datos
actuales inflaba la cuenta de episodios del nodo B de 3 a 7.

## 4. Segmentación: la unidad de observación

**Marcha o parada.** El valor eficaz filtrado es bimodal, pero **el nivel de cada modo es
propio de cada máquina**: el nodo A da 0,024 parado y 1,61 en marcha; el nodo B, 0,022 y 0,158.
Ningún umbral absoluto sirve para las dos.

> El primero que se probó, 0,05, se fijó con 1,88 h del nodo A y **era incorrecto**: caía dentro
> del grupo de parado, cuyo extremo llega a 0,06. Con 19 h se ve que el valle real está entre
> 0,06 y 0,30. Aquel umbral producía episodios espurios de una sola ráfaga.

El umbral se deriva ahora de los datos, separando los dos modos del logaritmo del valor eficaz.
Sin hiperparámetros. Da 0,198 para el nodo A y 0,060 para el nodo B, cada uno en su propio
valle. Si los dos modos no están separados al menos un factor 3, el pipeline avisa y considera
todo en marcha, en vez de partir en dos un grupo homogéneo.

**Episodios.** Un episodio es un tramo contiguo de ráfagas en marcha. Es **la unidad de
observación independiente**, y es la cifra que hay que mirar:

Las ráfagas salen cada 30 s. Las de un mismo episodio describen la misma condición de
operación y están fuertemente correlacionadas. 638 ráfagas de un único arranque de 6 h **no
son 638 observaciones**: son una condición medida 638 veces. Cualquier métrica calculada como
si lo fuesen sobreestima la evidencia en un orden de magnitud.

## 5. Características

**Todas adimensionales.** No es una preferencia estética, es el hallazgo que gobierna el
diseño:

> Un detector sobre `rms`, `peak` y `kurt` alcanza el **99,8 %** de detección **sin haber
> empleado ninguna característica que contenga la firma del fallo**. El nivel de vibración de
> los dos activos difiere en un factor 5,5, así que separa las dos *máquinas* y no el estado
> de una de ellas. Es una métrica excelente obtenida sobre el atributo equivocado.

| Característica | Definición | Separación medida |
| :--- | :--- | ---: |
| `n_picos` | Picos con amplitud ≥ 20 % de la mayor | **6,90 sd** |
| `aud_b1` | Energía acústica en 250–1000 Hz | 4,07 sd |
| `aud_b0` | Energía acústica en 0–250 Hz | 3,88 sd |
| `r3` | `f_alta / f0` | 3,17 sd |
| `r2` | `f_media / f0` | 2,21 sd |
| `q3`, `q2` | Amplitudes relativas a la del pico `f0` | 1,96 / 0,66 sd |
| `crest` | `peak_x / rms_x` | 0,94 sd |
| `kurt_x` | Kurtosis del eje X | 0,57 sd |

### Los picos se ordenan por FRECUENCIA, no por amplitud

Esto no es un detalle. El firmware publica los tres picos **ordenados por amplitud**, y con
esa ordenación los cocientes no son estables: en 60 de 676 ráfagas del activo con fallo el
armónico supera a la fundamental del giro por un **2 %** (0,2056 frente a 0,2016) y pasa a
ocupar la posición de pico dominante. Con la definición por amplitud, `f2/fdom` valía 9,0 en
unas ráfagas y **0,111 en otras describiendo el mismo fenómeno**: `fdom_x` aparentaba un CV
del 133 % y el cociente pasaba del 1,9 % al 30,9 %.

Reordenar por frecuencia lo arregla, pero por sí solo rompe el conjunto nominal: toma picos de
ruido de frecuencia baja y amplitud despreciable por fundamental, y el CV de `q2` se iba al
219 % porque el denominador era la amplitud de un pico de ruido. Hacen falta **las dos
condiciones**: descartar los picos con amplitud inferior al 20 % de la mayor, y ordenar por
frecuencia los que quedan.

Con ambas, `f0` tiene un CV del 0,16 % en el nominal y del 0,12 % en el activo con fallo.

El umbral del 20 % se verificó entre 0,15 y 0,30: la separación por `n_picos` es perfecta en
todo ese intervalo, de modo que el resultado no depende de acertar con el valor.

**Solo el eje X.** No por comodidad: `kurt_x` está en rango físico en el 100 % de las ráfagas
de ambos nodos, mientras `kurt_z` lo está en el 59 % del nodo A y el 44 % del nodo B. Es
selección por repetibilidad **medida**, no por criterio de la literatura.

Un cociente de frecuencias próximo a un entero delata un armónico del giro; una resonancia
estructural no produce varias componentes en múltiplos enteros exactos y simultáneos. El activo
con fallo presenta **8×, 9× y 10×** a la vez. Como el firmware publica solo tres picos, la
pareja concreta que entra varía por ráfaga (8× y 9× en 401, 9× y 10× en 235), y de ahí que el
CV de `r2` sea del 15 % sin que la firma sea inestable: restringido a las ráfagas donde el pico
alto es el 9.º, el cociente vale **9,0042 con un CV del 0,137 %**.

## 6. Selección del modelo

`comparar_modelos.py` compara seis candidatos en el **mismo punto de operación**: umbral en el
cuantil 0,05 de las puntuaciones de entrenamiento. Criterios, en orden de aplicación:

1. **Comportamiento sobre condiciones de operación no vistas.** Validación cruzada dejando
   fuera un episodio de marcha completo, mirando el **peor** episodio y no la media. Es el
   criterio decisivo, y el que exigía la campaña de referencia prolongada.
2. **Falsos positivos fuera de muestra**, frente al 5 % que el umbral fija por construcción.
   La tasa dentro de muestra la fija el umbral y no informa de nada.
3. Tasa de detección.
4. **Número de hiperparámetros.** Cada uno es un grado de libertad que con 45 observaciones
   correlacionadas no se puede ajustar honestamente.
5. **Viabilidad de embarcarlo en el ESP32.**

### Resultado

**Validación cruzada por episodios**, que es la correcta: se deja fuera un arranque completo,
se ajusta sobre los demás y se mide sobre una condición de operación **no vista**. Con 22
episodios ya es posible; con uno no lo era.

| Modelo | FP fuera de episodio | **Peor episodio** | Detec. | Hiperp. | Embarcable |
| :--- | ---: | ---: | ---: | ---: | :--- |
| **Regla sobre `n_picos`** | **0,5 ± 1,8 %** | **8,3 %** | 100 % | 1 | **Sí, una comparación** |
| Isolation Forest | 3,3 ± 7,9 % | 33,8 % | 100 % | 3 | No, 200 árboles |
| Regla sobre `r2` | 4,6 ± 6,1 % | 18,8 % | 96,6 % | 1 | Sí, dos comparaciones |
| Elliptic Envelope | 5,9 ± 8,4 % | 33,3 % | 100 % | 2 | Sí, forma cuadrática |
| LOF | 6,2 ± 8,3 % | 31,1 % | 100 % | 2 | No, exige el conjunto de ajuste |
| One-Class SVM | 6,7 ± 8,3 % | 25,0 % | 100 % | 2 | No |

**La columna que decide es el peor episodio, no la media.** Una media baja con un peor caso alto
significa que el detector falla de forma *concentrada*: en operación eso es una tanda de alarmas
falsas seguidas sobre un mismo arranque, no una aislada cada tanto. La regla es 3 a 4 veces
mejor que cualquier alternativa ahí.

Nota: One-Class SVM pasó del 46 % de falsos positivos con 45 observaciones al 6,7 % con 467. El
diagnóstico anterior era correcto en su naturaleza — sus hiperparámetros no eran ajustables con
ese tamaño de muestra — pero el problema era el número de datos, no el modelo.

**La detección no discrimina: los seis dan el 100 %.** Con un factor 5,5 de diferencia de
nivel entre activos, detectar este fallo es fácil y esa cifra no mide capacidad diagnóstica.
Consignarla como logro sería el mismo error que el detector dimensional.

### Un aviso antes de elegir: solo hay UN modo de fallo observado

Elegir el modelo por su tasa de falsos positivos contra un único fallo es **sobreajuste a ese
fallo**. `cobertura_modos.py` lo hace visible perturbando el conjunto nominal en direcciones de
fallo típicas. **Los datos que genera son sintéticos y no son evidencia** — localizan puntos
ciegos, que es otra pregunta.

| Dirección | Regla `n_picos` | Envolvente robusta | Bosque |
| :--- | ---: | ---: | ---: |
| Holgura mecánica | 100 % | 100 % | 100 % |
| Rodamiento incipiente | **0 %** | 100 % | 100 % |
| Roce o fricción | **0 %** | 100 % | 100 % |
| Desequilibrio de masa | **0 %** | 99 % | 10 % |

La regla es **ciega a 3 de 4**: detecta lo que *añade* componentes espectrales, no lo que altera
la amplitud o la impulsividad.

### El coste oculto de las características adimensionales

Son **ciegas por construcción** a un fallo que solo cambie el nivel. Todo se expresa como
cociente respecto a la fundamental, así que un desequilibrio de masa —que sube la amplitud a la
frecuencia de giro sin añadir componentes— no aparece en ninguna.

**Arreglo:** normalizar por la mediana del **propio** activo en marcha (`rms_x_rel`,
`adom_x_rel`) en vez de suprimir la magnitud. Adimensional en la forma, específica en el valor:
la mediana vale 1 en ambos activos, así que no reintroduce el sesgo entre máquinas, y la
envolvente pasa a detectar el 99 % del desequilibrio.

> **Contrapartida para el despliegue:** el nodo necesita la mediana de su propio activo, así que
> tiene que aprenderla en una fase de referencia. No puede juzgar su primera ráfaga.

### El compromiso que estos datos no resuelven

| Modelo | Peor episodio | Direcciones cubiertas |
| :--- | ---: | ---: |
| Regla sobre `n_picos` | **8,3 %** | 1 de 4 |
| Envolvente robusta | 25,0 % | **4 de 4** |
| Envolvente de Mahalanobis | 33,3 % | 4 de 4 |
| Bosque de aislamiento | 46,8 % | 3 de 4 |

Ninguno gana en las dos columnas. Y la elección **no es técnica**: depende de si cuesta más una
alarma falsa o un fallo no detectado, que es una decisión de quien explota el activo.

### La regla NO gana a los modelos de ML. Es un modelo de ML con una característica

La conclusión «la regla supera a los modelos» era **engañosa**, y conviene tenerlo claro:

Dando a cada modelo **únicamente `n_picos`**, los seis convergen al **mismo 8,3 %**. Con una
dimensión hay una sola frontera que encontrar. La comparación original era injusta: a la regla
le daba una característica bien elegida y a los modelos las 15, incluidas varias que no separan
nada y tienen mucha dispersión — lo que hunde a cualquier modelo de distancias o densidades.

**El mérito es de la característica, no del algoritmo.**

Y de ahí la objeción que decide: esa característica se eligió **sabiendo cuál era el fallo**, así
que su ventaja no se transfiere a otro. El análisis de cobertura lo confirma: **ciega a 4 de 5
direcciones**. Un detector de anomalías existe para los fallos que no conoces, así que
optimizarlo contra el único que tienes es sobreajuste.

### Y el 25 % del peor episodio estaba mal presentado

Son **3 ráfagas de 12** en uno de los episodios cortos de la tarde. Ponderado por ráfagas —lo
que verías en operación— la tasa es del **5,6 %**, y **11 de 22 episodios dan 0 %**.

### Todo lo anterior tenía sesgo de espionaje. El protocolo limpio está en `protocolo.py`

Las cifras de arriba se obtuvieron **usando el conjunto con fallo para tomar decisiones de
diseño**. `n_picos` se eligió ordenando las candidatas por su separación *frente al fallo*. Eso
es espionaje de datos y hace optimista todo lo que se derive.

`protocolo.py` implementa la separación estricta:

| | |
| :--- | :--- |
| **Permitido** | Cualquier decisión sobre el conjunto **nominal**. Conocimiento previo del dominio. Perturbaciones **sintéticas** del nominal |
| **Prohibido** | Elegir u ordenar características por su comportamiento sobre el fallo. Ajustar umbrales mirando la detección. Repetir la evaluación final |

Partición **cronológica por episodios** (no aleatoria: una partición aleatoria reparte
episodios contiguos entre ambos lados y filtra información del futuro):

```
desarrollo   16 episodios más antiguos   →  todas las decisiones
prueba        8 episodios más recientes  →  se mira UNA vez
```

**Resultado con el protocolo limpio:**

| | |
| :--- | ---: |
| Modelo elegido sin mirar el fallo | **LOF (novelty)** |
| Cobertura de direcciones | 5 de 5 |
| FP en desarrollo | 6,3 % |
| **FP en los episodios de prueba** | **7,8 %** |
| **Detección sobre el fallo** | **100 %** |

Nótese que el protocolo limpio elige **un modelo distinto** del que elegí a mano.

### Y el criterio de embarcabilidad que usé no existía

Etiqueté modelos como «no embarcables» **por suposición, sin medir**. Medido:

| Modelo | Memoria | Operaciones/ráfaga |
| :--- | ---: | ---: |
| Regla `n_picos` | 8 B | 3 |
| Elliptic Envelope | 960 B | 240 |
| One-Class SVM | 2,3 KB | 1 110 |
| LOF | 32 KB | 15 150 |
| Isolation Forest | 274 KB | 4 800 |

La placa tiene **512 KB de SRAM y 8 MB de PSRAM**, y 15 000 operaciones en coma flotante a
240 MHz son ~0,1 ms frente a una ráfaga cada 30 s. **Los cinco caben de sobra.** Ese criterio
sesgó la elección hacia lo simple sin ninguna base.

Ambas con **histéresis**: N ráfagas anómalas consecutivas antes de notificar. El 8,3 % del peor
episodio son ráfagas aisladas; exigir tres seguidas lo baja dos órdenes de magnitud.

Y hay una dirección que **ningún** modelo sobre vibración cubre: la obstrucción de la
ventilación no altera la firma vibratoria. Corresponde al canal lento, por el diferencial
térmico y la prolongación del ciclo. Es la justificación de que el sistema sea multimodal.

### El modelo, en resumen

La regla sobre `n_picos` vale 1 en 465 de las 467 ráfagas nominales y 3 en las 656 del activo
con fallo.

Lo que la cifra **no** dice: el intervalo de decisión sigue siendo un punto, porque las dos
observaciones discrepantes caen fuera del cuantil que lo fija. Eso no la invalida, pero
significa que **el margen de tolerancia no está estimado**: el modelo separa «un pico» de «más
de uno» y no tiene noción de cuánto puede acercarse un activo sano a la frontera. La cifra
honesta es la de la validación por episodios: 0,5 % de media, 8,3 % en el peor arranque.

Por eso **`r2` se conserva como corroboración**. Identifica *qué* armónico aparece y no solo
cuántos picos hay, de modo que un segundo armónico legítimo del giro no la dispara. Ambas se
embarcan con una o dos comparaciones en coma flotante.

El principio general: entre candidatos con comportamiento equivalente, el más simple gana. Los
grados de libertad que el conjunto de datos no permite ajustar no son capacidad, son riesgo.

Dos modelos quedan descartados por calibración, no por complejidad. **One-Class SVM** da un
46 % de falsos positivos donde el umbral pide un 5 %: con 45 muestras y 10 dimensiones, `nu` y
`gamma` no están ajustables. La **envolvente de Mahalanobis** propia da un 20 % porque su
regularización es un término diagonal fijo, insuficiente con una covarianza casi singular;
`EllipticEnvelope`, que regulariza bien, da un 6,3 %.

## 7. Evaluación — y qué no se puede afirmar

Lo que sí:

- El fallo se detecta con características adimensionales, con 100 % de detección y ~6 % de
  falsos positivos fuera de muestra.
- Una regla de una o dos comparaciones iguala al modelo completo, y se embarca.
- La firma es una **familia de armónicos del giro en 8×, 9× y 10×** (398, 448 y 497 Hz sobre
  una fundamental de 49,745 Hz), cada uno dentro del 0,05 % del entero. Ese razonamiento es
  sobre magnitudes adimensionales dentro de cada ráfaga y no depende del número de episodios.

Lo que **no**:

- **Los dos activos son máquinas distintas.** Usar características adimensionales acota ese
  sesgo; no lo elimina. Solo un fallo inducido sobre el mismo activo lo elimina. Es la
  limitación de mayor peso.
- **La validación por episodios se aplica al lado nominal, no al del fallo**, que tiene 2
  episodios aprovechables. Y no se corrige alargando la captura: ese compresor está en marcha
  el 95 % del tiempo, así que más horas dan el mismo episodio más largo.
- **El margen de tolerancia del umbral no está estimado** (ver arriba).
- **El modo de fallo no está identificado.** Hay una firma caracterizada, no un mecanismo.
- **El 63 % de las ráfagas nominales se descarta**: 63 % por compresor parado y un 32 % de las
  restantes por reintentos del bus. Soldar el conexionado recuperaría la segunda parte.

## 8. Despliegue

### ¿TinyML? No, y el motivo es de fondo

TensorFlow Lite Micro —el entorno que la gente llama TinyML— sirve para ejecutar **redes
neuronales** en microcontroladores. Su repertorio de operadores son convoluciones, capas densas,
funciones de activación.

**Ninguno de los siete candidatos es una red neuronal.** LOF es una búsqueda de vecinos más
cercanos; la envolvente robusta es una forma cuadrática; el bosque de aislamiento es un conjunto
de árboles. TFLite Micro **no puede ejecutar ninguno de ellos**, así que la pregunta no es si
conviene usarlo: es que no aplica.

Y no es que el modelo sea demasiado simple para merecerlo. Es que el problema —detección de una
clase con 505 observaciones— no admite una red neuronal: se sobreajustaría por completo. La
elección de familia de modelos vino determinada por el tamaño de muestra, no por el hardware.

Lo que se escribe a mano en C++:

| Modelo | Qué hay que programar | Memoria |
| :--- | :--- | ---: |
| Envolvente robusta | Vector de medias, matriz inversa, forma cuadrática. ~15 líneas | 960 B |
| LOF | Conservar la matriz de ajuste, distancias, k vecinos, densidad local. ~60 líneas | 32 KB |

Sin marco de trabajo, sin intérprete, sin modelo serializado. Aritmética.

### Qué modelo se embarca

El protocolo limpio (`protocolo.py`) elige **LOF**. Procede consignar una reserva honesta: LOF y
la envolvente robusta quedan casi empatadas en falsos positivos sobre el conjunto de desarrollo
(6,3 % frente a 6,0 %), y **el desempate lo decidió la columna de obstrucción de ventilación del
análisis de cobertura, que son datos sintéticos.** Es una base legítima —no interviene el fallo
real— pero débil.

Cambiar ahora la elección a la envolvente porque es 34 veces más pequeña sería **volver a
espiar**: el criterio se declaró antes de la evaluación y reordenarlo después de ver los
resultados es el mismo defecto con otra cara. Si el coste de despliegue debía pesar más, tenía
que haberse dicho al principio.

Queda por tanto declarado así: **LOF por protocolo**, con la envolvente como alternativa casi
equivalente y mucho más económica, y con la advertencia de que la diferencia entre ambas se
apoya en datos sintéticos. Un segundo modo de fallo real resolvería la cuestión.

### Cómo llega el modelo al chip

```
server/analisis/exportar_modelo.py       (pendiente)
        │  ajusta sobre el conjunto de desarrollo
        ▼
device/modelo_referencia.h               generado, no se edita a mano
        │  #include
        ▼
arduino-cli compile
```

El fichero generado lleva un comentario con la campaña y la fecha de las que salió. Reentrenar
es volver a ejecutar el script y recompilar; nunca copiar números a mano.

### Dos guardianes que el análisis reveló necesarios

**1. Negarse a juzgar una ráfaga con más de 3 reintentos del bus.** Sin él, el detector marca
como fallo cada ráfaga con el bus inestable: los reintentos fabrican la firma sobre un activo
sano. No es un filtro de calidad, es parte del detector.

**2. Histéresis.** Exigir N ráfagas anómalas consecutivas antes de notificar. El 7,8 % de falsos
positivos de la evaluación son ráfagas aisladas, y exigir tres seguidas lo reduce en dos órdenes
de magnitud si se suponen independientes.

Y una contrapartida de las características normalizadas por el propio activo: el nodo necesita
la mediana de su máquina, así que **tiene que aprenderla en una fase de referencia antes de
poder emitir veredicto**. No puede juzgar su primera ráfaga.

> No reflashear el nodo con una campaña de captura en curso: cambia la definición de las
> características y parte la serie en dos conjuntos no comparables.

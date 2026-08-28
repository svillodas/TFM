# Informe de avance — Detección de un fallo real: familia armónica del giro

> **Revisado el 26 de agosto de 2026 tras ampliar la captura a 815 ráfagas.** Las cifras del
> cuerpo de este informe corresponden a la primera versión del análisis, con una definición de
> característica defectuosa. La corrección está al final y en `docs/EXPERIMENTOS.md`; el
> hallazgo se refuerza, no se cae.

**Fecha:** 26 de agosto de 2026
**Campañas:** EXP-003 (activo con fallo), EXP-004 (activo de referencia)
**Estado:** hallazgo confirmado y documentado en la memoria

---

## 1. Resumen

Se disponía de un segundo compresor que presentaba un fallo real, no inducido, perceptible
como un tono audible sostenido. La instrumentación del nodo detectó una componente tonal
en **447,76 Hz** presente en el 99 % de las ráfagas, ausente en el activo de referencia
medido con el mismo firmware en el mismo intervalo.

La componente mantiene una relación de **9,0030** con la frecuencia de giro, con un
coeficiente de variación del **0,07 %**, inferior al de cualquiera de las dos frecuencias
por separado. Es el **noveno armónico del giro**, no una propiedad del montaje.

El hallazgo aporta al TFM lo que no estaba previsto tener: un caso de fallo con **verdad de
referencia independiente de la instrumentación** —el operador lo oye— y un activo de control
en estado nominal medido en las mismas condiciones.

---

## 2. Evidencia

### 2.1 Enganche al régimen de giro

| Magnitud | Valor | CV |
| :--- | ---: | ---: |
| Frecuencia de giro (`fdom_x`) | 49,745 Hz | 0,52 % |
| Componente tonal (`f2_x`/`f3_x`) | 447,76 Hz | 0,12 % |
| **Cociente** | **9,0030** | **0,07 %** |

El razonamiento es el que decide la cuestión. Si la componente fuese una resonancia
estructural, su frecuencia sería la magnitud estable y el cociente heredaría la variabilidad
del régimen de giro. Lo observado es lo contrario: **el cociente es más estable que sus dos
términos**, de modo que la componente la genera el giro. La desviación respecto del entero 9
es del 0,03 %.

### 2.2 Confirmación acústica, con sensor y cadena independientes

| Magnitud | Con fallo (EXP-003) | Referencia (EXP-004) |
| :--- | ---: | ---: |
| `aud_b0` (0–250 Hz) | 0,012 | 0,947 |
| `aud_b1` (250–1000 Hz) | **0,987** | 0,034 |
| `aud_rms` | **1677** | 333 |
| Ráfagas con pico en 380–460 Hz | 712/719 (99 %) | 1/216 (0 %) |

El reparto de energía acústica está **invertido** entre ambos activos, y la banda donde se
concentra la energía del activo con fallo es la que contiene la componente que ve el
acelerómetro. Dos modalidades que no comparten sensor, bus ni acondicionamiento coinciden.

---

## 3. Correcciones que este hallazgo obliga a hacer

Tres afirmaciones anteriores del proyecto quedan invalidadas. Se consignan porque el error
en cada caso es informativo.

**«Los 448 Hz son una resonancia del acoplamiento del sensor.»** Incorrecto. La hipótesis era
coherente con lo observado —la componente aparecía en distintas posiciones del sensor y su
frecuencia se desplazaba— pero la prueba que la resuelve, comprobar el enganche al régimen,
no se planteó hasta que el operador mencionó el tono audible. Es un límite del análisis
basado solo en los registros: la interpretación establecida no se cuestionó porque nada en
los datos obligaba a hacerlo.

**«`aud_b1` = 0,99 está saturado y no aporta información.»** Incorrecto. Era la firma del
fallo. Un valor extremo y estable no es necesariamente un sensor mal escalado.

**«El canal acústico es redundante con el acelerómetro.»** Incorrecto. Es la confirmación
independiente que permite descartar un artefacto de la cadena de vibración, y es lo que
convierte un indicio en una evidencia.

**«El 95 % de la mejora del punto de medida no es señal aprovechable.»** Parcialmente
incorrecto. Ese 95 % reside en la banda donde después se identificó el fallo. Lo correcto es
que la ganancia *sobre los estadísticos temporales filtrados* es de 1,6 y no de quince.

---

## 4. Consecuencias de diseño confirmadas

Dos decisiones de firmware se adoptaron bajo la interpretación equivocada y resultan
necesarias también bajo la correcta:

- **Publicar tres picos espectrales** en lugar del dominante. Con un solo pico, el fallo
  ocuparía la única posición disponible y el régimen de giro quedaría oculto —y con él, la
  posibilidad de calcular el cociente que identifica el armónico.
- **No filtrar el espectro.** El filtro paso bajo a 150 Hz de los estadísticos temporales
  elimina por completo la componente: `rms`, `peak` y `kurt` **no registran este fallo**. Su
  detección depende en su totalidad de los picos espectrales sin filtrar y de las bandas
  acústicas.

Se valoró como alternativa **acotar la búsqueda espectral a la banda fiable del montaje**, del
orden de 150 Hz. Esa alternativa habría situado el fallo fuera de la banda examinada y el
fenómeno no se habría registrado. Se descartó por no depender de acertar con un límite fijo,
motivo que resultó ser el correcto por una razón distinta de la prevista.

---

## 5. Lo que el hallazgo no establece

- **El modo de fallo no está identificado.** Se ha caracterizado una firma, no un mecanismo.
- **El contraste es entre máquinas distintas**, de modo que no separa el efecto del fallo del
  de la variabilidad entre ejemplares. La magnitud de la diferencia (0,03 frente a 0,99 en
  reparto acústico) es difícil de atribuir a esa variabilidad, pero la afirmación rigurosa
  exige comparación dentro de un mismo activo.
- **La resonancia del acoplamiento sigue sin medir.** El corte del filtro a 150 Hz se derivó
  de los 448 Hz que se le atribuían; refutada la atribución, el corte es una cota conservadora
  sin verificar.

---

## 6. Trazabilidad

| Elemento | Ubicación |
| :--- | :--- |
| Campaña del activo con fallo | [EXP-003](../EXPERIMENTOS.md) |
| Campaña del activo de referencia | [EXP-004](../EXPERIMENTOS.md) |
| Datos | `server/data/nodo-b-otro-compresor/fw-46col/`, `server/data/nodo-a-nevera-buena/fw-46col/` |
| Clasificación de las series | [`server/data/manifiesto.json`](../../server/data/manifiesto.json) |
| Corrección de la atribución | `memoria_TFM/capitulos/05-diseno.tex`, secciones de componente tonal y corrección en el nodo |
| Resultado | `memoria_TFM/capitulos/06-resultados.tex`, secciones de fallo real y confirmación multimodal |

---

## 7. Corrección posterior

**Lo que estaba mal.** Los cocientes se calculaban sobre los picos tal como los publica el
firmware, que los **ordena por amplitud**. En 60 de 676 ráfagas el armónico del fallo supera a
la fundamental por un 2 % y le arrebata la posición de pico dominante, con lo que el mismo
fenómeno daba cocientes de 9,0 y de 0,111 indistintamente. La solución es ordenar por
**frecuencia**, descartando antes los picos con amplitud inferior al 20 % de la mayor.

**Lo que cambia el hallazgo, a mejor.** No es una componente en 447,76 Hz al noveno armónico:
son **tres componentes simultáneas en 398, 448 y 497 Hz**, los armónicos 8×, 9× y 10× del giro,
cada uno dentro del 0,05 % del entero.

El argumento contra la resonancia estructural queda por tanto más sólido. La versión anterior
se apoyaba en que el CV del cociente (0,07 %) era inferior al de las frecuencias por separado,
comparación que con la definición corregida no se sostiene: el cociente del noveno armónico da
un CV del 0,137 % frente al 0,125 % de la fundamental. El argumento válido es distinto y no
depende de ninguna comparación de coeficientes: **una resonancia estructural no produce tres
componentes simultáneas en múltiplos enteros exactos de una frecuencia que además varía.**

**Un límite de la instrumentación que esto pone al descubierto.** El firmware publica tres
picos por eje, uno de ellos la fundamental: solo caben dos armónicos por ráfaga. La pareja
registrada varía (8× y 9× en 401 ráfagas, 9× y 10× en 235), y de ahí el CV del 15 % del
cociente intermedio sin que la firma sea inestable. **Con tres picos no se puede caracterizar
una familia armónica de más de dos componentes.**

**Detector resultante.** El número de picos significativos separa los dos activos y se embarca
con una comparación.

> **Actualizado el 27 de agosto** con la campaña de referencia de 19 h ([EXP-005](../EXPERIMENTOS.md)),
> que aporta 467 ráfagas nominales en **22 episodios** y hace posible la validación cruzada por
> episodios: la regla da **0,5 % de falsos positivos de media y 8,3 % en el peor arranque**,
> frente al 25-34 % de los seis candidatos restantes. Esa campaña destapó además que **los
> reintentos del bus I2C fabrican esta misma firma sobre un activo sano**, y confirmó que la
> firma del nodo B no es ese artefacto: con cero reintentos en ambos lados, los cocientes
> armónicos dan 8,0016 con un CV del 0,029 %.

Detalle en `server/analisis/README.md`.

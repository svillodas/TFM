# Informe de avance — Auditoría metodológica de la Fase 4

**Fecha:** 27 de agosto de 2026
**Campañas:** EXP-003 (fallo real), EXP-005 (referencia prolongada, 21,54 h)
**Estado:** pipeline de análisis cerrado; cuatro defectos de método detectados y corregidos

---

## 1. Resumen

Se cerró el pipeline de detección de anomalías y, en el proceso, se detectaron y corrigieron
**cuatro defectos de método propios**, tres de los cuales invalidaban resultados ya publicados
en la memoria. Este informe los documenta porque el valor metodológico de haberlos encontrado
es superior al de las cifras que sustituyen.

| # | Defecto | Consecuencia |
| ---: | :--- | :--- |
| 1 | Cocientes calculados sobre picos ordenados por amplitud | El mismo fenómeno daba 9,0 y 0,111 |
| 2 | Umbral marcha/parada absoluto y mal situado | Episodios espurios de una ráfaga |
| 3 | **Sesgo de espionaje** en la selección de características | Cifras optimistas y modelo equivocado |
| 4 | Criterio de embarcabilidad no medido | Sesgaba la elección hacia lo simple |

El resultado final, con protocolo libre de espionaje: **7,8 % de falsos positivos** sobre
episodios nunca vistos y **100 % de detección** sobre el activo con fallo.

---

## 2. Defecto 1 — Los picos vienen ordenados por amplitud

El firmware publica los tres picos espectrales **ordenados por amplitud**. En el activo con
fallo el armónico supera a la fundamental del giro por un **2 %** (0,2056 frente a 0,2016) en 60
de 676 ráfagas y le arrebata la posición de dominante.

Consecuencia: un cociente `f2_x / fdom_x` valía **9,0 en unas ráfagas y 0,111 en otras
describiendo el mismo fenómeno físico**. `fdom_x` aparentaba un coeficiente de variación del
133 %.

**Corrección.** Reordenar los picos **por frecuencia**, descartando previamente los de amplitud
inferior al 20 % de la mayor. Las dos condiciones son necesarias: ordenar solo por frecuencia
toma picos de ruido de frecuencia baja por fundamental, y el CV de la amplitud relativa se iba
al 219 %. Verificado entre el 15 % y el 30 %: el resultado no depende del umbral.

Con ambas, el CV de la fundamental es del 0,16 % en el activo sano y del 0,12 % en el activo con
fallo.

**El hallazgo del fallo sale reforzado.** No es una componente aislada en 447,76 Hz: son **tres
simultáneas en 398, 448 y 497 Hz**, los armónicos 8×, 9× y 10× del giro, cada uno dentro del
0,05 % del entero. Una resonancia estructural no produce tres componentes en múltiplos enteros
exactos de una frecuencia que además varía.

Debe retirarse en cambio el argumento anterior, que se apoyaba en que el CV del cociente
(0,07 %) era inferior al de las frecuencias por separado. Con la definición corregida no se
sostiene: el cociente del noveno armónico da un CV del 0,111 % frente al 0,12 % de la
fundamental. El argumento válido es la **coincidencia de tres armónicos con la serie del giro**,
que no depende de comparar coeficientes.

---

## 3. Defecto 2 — El umbral marcha/parada

Se había fijado en 0,05 m/s² a partir de las 1,88 h de EXP-004. Con las 21,54 h de EXP-005 se
observa que el grupo de parado del nodo A llega hasta 0,06 y que el valle real está entre 0,06 y
0,30: **el umbral caía dentro del grupo de parado** y producía episodios espurios de una sola
ráfaga.

Y el valle es **propio de cada máquina**: 0,1994 m/s² en el nodo A, 0,0595 en el nodo B. Ningún
valor absoluto sirve para las dos.

**Corrección.** Derivarlo de los datos separando los dos modos del logaritmo del valor eficaz.
Sin hiperparámetros. Si los dos modos no están separados al menos un factor 3, el pipeline avisa
y considera todo en marcha, en lugar de partir en dos un grupo homogéneo.

---

## 4. Defecto 3 — El filtro de calidad es parte del detector

Es el hallazgo de mayor consecuencia práctica. **Los reintentos del bus I2C fabrican la firma
del fallo sobre el activo sano.**

| `retries` | n | con más de un pico | `f0` mediana |
| ---: | ---: | ---: | ---: |
| 0 | 261 | 0,4 % | 49,15 Hz |
| 1–3 | 206 | 0,5 % | 49,17 Hz |
| 4–5 | 53 | 8 % | 49,25 Hz |
| 6–10 | 48 | 31 % | 49,16 Hz |
| 11–20 | 46 | **93 %** | **20,03 Hz** |
| > 20 | 69 | **94 %** | **16,03 Hz** |

Una muestra corrupta inyecta ruido de banda ancha y varios coeficientes del espectro superan el
umbral de significación. El corte se recalibró de 5 a **3 reintentos**.

**Consecuencia para el despliegue:** el nodo debe **negarse a emitir veredicto** sobre una ráfaga
con más de 3 reintentos, no juzgarla. Sin ese guardián el detector marca como fallo cada ráfaga
con el bus inestable.

**Y sube la prioridad de soldar el conexionado.** No es pérdida de datos: las ráfagas que pasan
con 4–10 reintentos **contaminan la característica que decide**.

### La comprobación que podía tumbar el trabajo

Si los reintentos fabrican la firma, ¿es la firma de EXP-003 ese mismo artefacto? Restringiendo
ambos conjuntos a **cero reintentos**:

| Conjunto | n | 1 pico / 3 picos | `f0` |
| :--- | ---: | :--- | ---: |
| Nodo A, sano | 278 | 277 / 1 | 49,15 Hz |
| Nodo B, con fallo | 443 | 0 / 430 | 49,76 Hz |

Cocientes del nodo B sin ningún reintento: **8,0016 con CV del 0,029 %** y 9,0035 con CV del
0,106 %. Y su firma es **idéntica** con reintentos y sin ellos (8,003 frente a 7,998), mientras
la del nodo A se derrumba.

**Un artefacto del bus no puede producir un valor que el propio bus no altera.** El fallo es
real.

---

## 5. Defecto 4 — Sesgo de espionaje de datos

El defecto más grave, y el que menos síntomas daba.

La característica `n_picos` se eligió **ordenando las candidatas por su separación medida sobre
el conjunto con fallo**. Es decir, usando el conjunto de evaluación para tomar una decisión de
diseño. Todo lo derivado de ahí era optimista.

Y de ello se seguía una conclusión **falsa**: que una regla sobre una característica superaba a
los modelos de aprendizaje automático. Dándoles **únicamente esa característica**, los seis
candidatos convergen al mismo 8,3 %: con una dimensión hay una sola frontera que localizar. La
comparación original era desigual — una característica bien elegida frente a las quince,
incluidas varias sin capacidad de separación y con dispersión elevada, lo que penaliza a todo
modelo basado en distancias o densidades. **El mérito era de la característica, no del
algoritmo.**

Y la objeción determinante: esa característica se eligió conociendo el fallo, de modo que su
ventaja no se transfiere a otro. El análisis de cobertura lo confirma — **ciega a 4 de 5
direcciones de fallo**. Un detector de anomalías tiene por objeto precisamente los fallos que no
se conocen de antemano.

### El protocolo

[`server/analisis/protocolo.py`](../../server/analisis/protocolo.py), con las reglas explícitas:

| | |
| :--- | :--- |
| **Permitido** | Cualquier decisión sobre el conjunto **nominal** (en explotación también se tendría). Conocimiento previo del dominio. Perturbaciones **sintéticas** del nominal |
| **Prohibido** | Seleccionar u ordenar características por su comportamiento sobre el fallo. Ajustar umbrales mirando la detección. Repetir la evaluación final |

Partición **cronológica por episodios**: 16 episodios más antiguos para desarrollo, 8 más
recientes para prueba. Cronológica y no aleatoria porque reproduce la situación real —se ajusta
con lo capturado y se despliega sobre lo que venga— mientras una partición aleatoria reparte
episodios contiguos entre ambos lados y filtra información del futuro.

### Resultado

| Magnitud | Valor |
| :--- | ---: |
| Modelo elegido **sin mirar el fallo** | **LOF** |
| Direcciones cubiertas | 5 de 5 |
| Falsos positivos en desarrollo | 6,3 % |
| **Falsos positivos en episodios de prueba** | **7,8 %** |
| **Detección sobre el fallo** | **100 %** |

**El protocolo elige un modelo distinto del elegido a mano.** Esa discrepancia es la evidencia
de que la elección anterior estaba contaminada: de haber sido correcta, ambos habrían coincidido.

---

## 6. Defecto 5 — Un criterio de selección infundado

Entre los cinco criterios de selección se incluyó la viabilidad de embarcar cada modelo, y
varios se descartaron por ese motivo **sin haberlo medido**.

| Modelo | Memoria | Operaciones/ráfaga |
| :--- | ---: | ---: |
| Regla `n_picos` | 8 B | 3 |
| Envolvente robusta | 960 B | 240 |
| One-Class SVM | 2,3 KB | 1 110 |
| LOF | 32 KB | 15 150 |
| Isolation Forest | 274 KB | 4 800 |

La placa tiene **512 KB de SRAM y 8 MB de PSRAM**, y 15 150 operaciones en coma flotante a
240 MHz son del orden de **0,1 ms** frente a una ráfaga cada 30 s.

**Los cinco caben con amplio margen.** La restricción no existía y orientaba la selección hacia
los modelos más simples sin fundamento.

---

## 7. El coste oculto de las características adimensionales

Las características adimensionales se adoptaron para eliminar el sesgo entre máquinas —el nivel
de los dos activos difiere en un factor 12,5— pero tienen un coste que no se había declarado:
son **ciegas por construcción a un fallo que solo modifique el nivel**, puesto que toda magnitud
se expresa como cociente respecto de la fundamental. Un desequilibrio de masa eleva la amplitud
del giro sin añadir componentes, y ninguna lo registra.

**Corrección.** Normalizar por la mediana del **propio** activo en marcha (`rms_x_rel`,
`adom_x_rel`) en lugar de suprimir la magnitud: adimensional en la forma, específica en el valor.
La mediana vale 1 en ambos activos, así que no reintroduce el sesgo, y la envolvente pasa a
detectar el 99 % del desequilibrio simulado.

**Contrapartida operativa:** el nodo necesita la mediana de su propio activo, de modo que ha de
**aprenderla en una fase de referencia** antes de poder emitir veredicto. No puede juzgar su
primera ráfaga.

### El canal térmico no se estaba usando

Al revisarlo se comprobó que el detector usaba 9 características de vibración y 4 de sonido, y
**ninguna de temperatura**: el canal lento vive en otro fichero y a otra cadencia, y nunca se
habían unido. Añadida la unión por marca de tiempo, con el diferencial térmico relativo al
propio activo y el gradiente del minuto anterior.

Es lo que hace detectable una obstrucción de ventilación, que **no altera la vibración ni el
sonido en absoluto**. Es la justificación experimental del planteamiento multimodal.

En esa unión apareció un defecto adicional: `astype("int64")` sobre una marca de tiempo devuelve
**microsegundos** en pandas 3, no nanosegundos, de modo que dividir por 10⁹ colapsaba las marcas
y 24 753 de 24 780 quedaban duplicadas. El gradiente salía en 19 °C/min sobre un activo cuya
temperatura varía 7 °C en total. Corregido calculando los segundos por diferencia frente a un
instante explícito, que es independiente de la unidad interna.

---

## 8. Sobre TinyML

**No se emplea, y no figura en la propuesta de trabajo.** La solicitud pide «algoritmos de
Machine Learning»; no menciona TinyML, redes neuronales ni TensorFlow.

El motivo de fondo: los entornos de ejecución de modelos reducidos para microcontroladores
operan sobre **redes neuronales**. Ninguno de los siete candidatos lo es —LOF es una búsqueda de
vecinos, la envolvente una forma cuadrática, el bosque un conjunto de árboles—, de modo que no es
que resulten excesivos: **no pueden ejecutarlos**.

Y una red neuronal no era alternativa: con 505 observaciones nominales de 24 episodios,
cualquier arquitectura con capacidad apreciable se sobreajustaría. La familia de modelos la
determinó el tamaño de muestra, no la plataforma.

La inferencia se programa directamente: ~15 líneas de C++ para la envolvente, ~60 para LOF.

---

## 9. Desviación respecto de la propuesta

La propuesta enuncia «clasificación automática de los estados de salud». Lo obtenido es
**detección de una clase**: distingue nominal de anómalo sin atribuir la desviación a un estado
concreto.

**Justificación:** un clasificador exige ejemplos etiquetados de cada estado, y se dispone de un
único modo de fallo real, sobre un activo que además no es el de referencia. Un clasificador
multiclase no sería ajustable ni evaluable. La detección de una clase es además el planteamiento
que la literatura prescribe para esta situación. El objetivo se alcanza en su formulación
binaria, no en la multiclase.

---

## 10. Lo que sigue sin resolver

1. **Los dos activos son máquinas distintas.** Las características adimensionales acotan el
   sesgo, no lo eliminan. Solo un fallo inducido sobre el activo de referencia lo elimina, y es
   la primera línea de continuación.
2. **Un solo modo de fallo real.** Las cinco direcciones del análisis de cobertura son
   sintéticas y no constituyen evidencia.
3. **El lado del fallo tiene 2 episodios aprovechables**, y no se corrige alargando la captura:
   ese activo permanece en marcha el 95 % del tiempo.
4. **La elección entre LOF y la envolvente robusta se apoya en datos sintéticos.** Quedan casi
   empatadas en falsos positivos (6,3 % frente a 6,0 %) y el desempate lo decidió la columna de
   obstrucción del análisis de cobertura. Cambiar ahora a la envolvente por ser 34 veces más
   pequeña sería volver a espiar: el criterio se declaró antes de la evaluación.
5. **La inferencia no está embarcada.** Viabilidad demostrada, funcionamiento no.

---

## 11. Trazabilidad

| Elemento | Ubicación |
| :--- | :--- |
| Pipeline de datos | [`server/analisis/pipeline.py`](../../server/analisis/pipeline.py) |
| Comparación de modelos y validación por episodios | [`comparar_modelos.py`](../../server/analisis/comparar_modelos.py) |
| Puntos ciegos (datos sintéticos) | [`cobertura_modos.py`](../../server/analisis/cobertura_modos.py) |
| **Protocolo sin sesgo de espionaje** | [`protocolo.py`](../../server/analisis/protocolo.py) |
| Detector y su evaluación | [`baseline_anomalias.py`](../../server/analisis/baseline_anomalias.py) |
| **Auditoría de las 8 decisiones** | [`cuadernos/auditoria-fase4.ipynb`](../../server/analisis/cuadernos/auditoria-fase4.ipynb) |
| Decisiones y su justificación | [`server/analisis/README.md`](../../server/analisis/README.md) |
| Campañas | [EXP-003 y EXP-005](../EXPERIMENTOS.md) |
| Capítulos afectados | `02-estado-del-arte`, `03-objetivos`, `05-diseno`, `06-resultados` |

# Informe de avance — TFM Sistema IoT Edge para mantenimiento predictivo

> ## ⚠ REVISADO — este informe contiene una atribución incorrecta
>
> Todo el cuerpo de este informe atribuye las componentes de 398-448 Hz a **una resonancia del
> acoplamiento adhesivo del sensor**. **Esa atribución es falsa.** El análisis posterior
> estableció que son los armónicos **8×, 9× y 10× de la frecuencia de giro**: la firma de un
> fallo real del activo, no una propiedad del montaje.
>
> El informe se conserva sin reescribir porque es un registro fechado y porque el razonamiento
> que llevó al error es parte del método seguido: la hipótesis era coherente con todo lo
> observado entonces, y la prueba que la refuta —comprobar si la relación con el régimen de giro
> se mantiene constante— no se planteó hasta que el operador mencionó un tono audible.
>
> **Lo que sigue siendo válido:** el cambio de punto de medida y su efecto sobre el nivel, las
> dos correcciones de firmware (filtro a 150 Hz en los estadísticos temporales, tres picos
> espectrales) y el recalibrado del umbral de continuidad a 6 m/s². Las correcciones eran
> necesarias bajo la interpretación equivocada y siguen siéndolo bajo la correcta.
>
> **Lo que cambia de sentido:** el «95 % del incremento no es señal aprovechable» era lo
> contrario. Ese 95 % es la banda donde estaba el fallo.
>
> Corrección completa en
> [`2026-08-26-fallo-real-noveno-armonico.md`](2026-08-26-fallo-real-noveno-armonico.md) y en
> [`../EXPERIMENTOS.md`](../EXPERIMENTOS.md).

**Fecha:** 2026-08-26 · **Periodo cubierto:** 2026-08-26
**Fase del roadmap:** 3 — Conectividad y captura de datos · **Horas acumuladas:** sin registrar

## 1. Resumen ejecutivo

Se resolvió la limitación que impedía capturar la firma vibratoria del activo. El acelerómetro
estaba fijado sobre la cúpula del compresor, superficie que el fabricante aísla del motor
mediante una suspensión interna, de modo que la señal medida no se distinguía del ruido
propio del sensor. Al trasladarlo al tubo de descarga el nivel se multiplicó por un factor
entre nueve y veinte, aunque quedó al descubierto una resonancia del acoplamiento adhesivo
que se lleva en torno al 95 % de la energía. Ambas circunstancias se abordaron con dos
correcciones en el firmware, verificadas en el computador y validadas en la placa. El
firmware queda cerrado para la campaña de referencia.

## 2. Trabajo realizado

| Tarea | Estado | Evidencia |
| :--- | :--- | :--- |
| Comparación de puntos de medida sobre el activo | Completada | [EXP-002](../EXPERIMENTOS.md); guía visual anotada |
| Traslado del acelerómetro al tubo de descarga | Completada | `hardware/fotos/README.md`, tabla de posiciones |
| Caracterización de la resonancia del acoplamiento | Completada | Dos modos, en 397-398 Hz y 446-448 Hz |
| Tres picos espectrales por eje en lugar del dominante | Completada | `device/signal_processing.h`; pruebas 8 y 9 |
| Filtro paso bajo a 150 Hz en los estadísticos temporales | Completada | `device/signal_processing.h`; pruebas 9, 10 y 11 |
| Recalibración del umbral de continuidad | Completada | 3 a 6 m/s², justificado sobre la pendiente medida |
| Verificación numérica del procesado | Completada | 27/27 pruebas, ampliadas desde 17 |
| Validación en placa del firmware definitivo | Completada | [EXP-002](../EXPERIMENTOS.md) |
| Ampliación de los buffers de publicación | Completada | Payload 896 a 1152 B; peor caso medido en 1050 B |
| Columnas nuevas en el registrador | Completada | 45 campos, coherencia verificada con el firmware |
| Fase de actualización del concentrador | Completada | `server/provision-pi.sh actualizar` |
| Script de sincronización con el concentrador | Completada | `server/sync-pi.sh` |
| Campaña de referencia | **No realizada** | Pendiente; el firmware queda listo |

## 3. Incidencias y decisiones técnicas

**El punto de medida pesaba más que el tipo de fijación.** El acelerómetro se encontraba
adherido a la cúpula del compresor. Sobre esa posición, el valor eficaz de vibración con el
activo en marcha era de \mbox{0,047 m/s²}, y la comparación entre las ráfagas con
frecuencia dominante próxima al régimen del motor y el resto no mostraba diferencia alguna
de nivel: \mbox{0,069} frente a \mbox{0,079 m/s²}, con recorridos solapados. La conclusión
era que el canal de vibración no distinguía el activo en marcha del activo detenido, mientras
que el canal térmico sí lo hacía.

La causa es de diseño del propio activo. Un compresor hermético lleva el conjunto motor-bomba
suspendido sobre muelles en el interior de la carcasa, solución que reduce el ruido radiado
y que en consecuencia aísla la superficie exterior de la vibración que interesa medir. La
cúpula es, por tanto, el lado amortiguado de esa suspensión.

*Decisión: trasladar el sensor al tubo de descarga.* Se evaluaron dos alternativas, el
anclaje al chasis y el tubo de descarga, y se adoptó la segunda. El tubo está unido
rígidamente al cuerpo de la bomba y transporta la pulsación sin atravesar la suspensión
interna. El traslado elevó el valor eficaz entre nueve y veinte veces según el eje, y la
frecuencia fundamental pasó de identificarse en el 8 % de las ráfagas a hacerlo en la
práctica totalidad.

**La mejora no es la que sugiere el dato en bruto.** El nivel pasó de \mbox{0,047} a
\mbox{0,35 m/s²}, pero en torno al 95 % de ese incremento corresponde a una resonancia del
acoplamiento y no a señal aprovechable. El valor eficaz en la banda útil es de
\mbox{0,062 m/s²}, de modo que la ganancia en señal utilizable es de un factor próximo a
1,6 y no de quince. Procede consignarlo así para no atribuir al sistema una sensibilidad de
la que no dispone.

**Resonancia del acoplamiento adhesivo.** Con el sensor inmóvil y sin manipulación, el
espectro quedó dominado por una componente cuasi senoidal en torno a los \mbox{448 Hz}: la
amplitud estimada alcanzaba el 95 % de la que correspondería a una senoide pura de ese valor
eficaz, y la kurtosis se situaba en 1,72, próxima al valor analítico de 1,5 de una senoide.
Se identificaron dos modos, en \mbox{397-398 Hz} y \mbox{446-448 Hz}.

El origen se atribuyó al acoplamiento y no al punto de medida por dos observaciones. La
primera es que la misma frecuencia aparecía con el sensor en la cúpula, aunque con amplitud
del orden del ruido: la resonancia es una propiedad del conjunto formado por la masa del
módulo y la elasticidad del adhesivo, de modo que acompaña al sensor con independencia de
dónde se fije. La segunda es que la frecuencia se desplazó entre \mbox{398 Hz} y
\mbox{448 Hz} a lo largo de la sesión; un artefacto de origen eléctrico se habría mantenido
fijo, mientras que una resonancia mecánica se desplaza al variar ligeramente el acoplamiento.

Al mejorar el punto de medida la resonancia no se introdujo, sino que se hizo audible: una
resonancia amplifica lo que se le entrega, y hasta entonces no se le entregaba energía
suficiente.

**Consecuencia sobre las características, y su corrección.** El efecto era distinto según la
característica. Los estadísticos temporales —valor eficaz, valor de pico y kurtosis— se
calculan sobre la señal completa y por tanto integraban la resonancia: la kurtosis quedaba
fijada en torno a 1,75 con independencia del estado del activo, es decir, sin capacidad
diagnóstica alguna. La estimación espectral, por su parte, devolvía como frecuencia dominante
la de la resonancia, con lo que el régimen de giro del motor resultaba invisible.

*Decisión: corregir en el nodo y no en el concentrador.* Es una consecuencia del procesado en
el borde que conviene explicitar: el nodo transmite características y no señal, de modo que
lo que allí se descarta no es recuperable después. Una vez publicada una frecuencia dominante
de \mbox{448 Hz}, la información sobre el pico de \mbox{49 Hz} no existe en ningún otro
lugar. A ello se añade que modificar la definición de una característica invalida cualquier
conjunto de referencia capturado con la definición anterior, por lo que el firmware debía
quedar cerrado antes de la campaña y no después.

*Corrección primera: tres picos espectrales por eje.* Se publican las frecuencias y amplitudes
de los tres coeficientes de mayor magnitud, separados por una guarda de cuatro coeficientes
—el ancho del lóbulo principal de la ventana empleada— para no devolver la falda de un mismo
tono como pico distinto. Se valoró la alternativa de acotar la búsqueda a una banda fija y se
descartó: la resonancia medida se desplazó entre \mbox{398 Hz} y \mbox{448 Hz}, de modo que
un límite fijo habría fallado ante ese desplazamiento.

*Corrección segunda: filtro paso bajo en los estadísticos temporales.* Se aplica un filtro de
segundo orden con corte en \mbox{150 Hz} antes de calcular valor eficaz, pico y kurtosis. El
espectro se deja deliberadamente sin filtrar, para que la resonancia siga siendo observable y
caracterizable. La consecuencia, que debe tenerse presente en el análisis, es que los
estadísticos temporales describen la banda \mbox{0-150 Hz} mientras que los picos
espectrales describen todo el intervalo hasta la frecuencia de Nyquist: no son magnitudes de
la misma señal.

La elección del corte responde a la práctica habitual en medida de vibración de no emplear un
montaje por encima de un tercio de su frecuencia de resonancia. Con la resonancia en
\mbox{448 Hz}, la banda fiable alcanza unos \mbox{150 Hz}, suficiente para la fundamental del
activo y sus dos primeros armónicos.

**Recalibración del umbral de continuidad.** La comprobación de continuidad entre muestras
consecutivas se había fijado en \mbox{3 m/s²} por muestra, valor justificado sobre una
pendiente máxima estimada de \mbox{0,5 m/s²} por milisegundo. Las medidas invalidaron esa
estimación: la resonancia, que es señal legítima, produce una pendiente de
\mbox{2,6 m/s²} por milisegundo, el 87 % del umbral, con lo que la comprobación habría
empezado a rechazar muestras válidas. El umbral se situó en \mbox{6 m/s²}, entre la pendiente
legítima máxima y el menor salto de corrupción observado, que equivale a la componente
continua del eje y se sitúa entre \mbox{5,8} y \mbox{11,9 m/s²}.

**Configuración del concentrador sobrescrita por la sincronización.** El registrador quedó
inoperativo con un error de resolución de nombre: su configuración apuntaba al intermediario
público, que no es alcanzable con el punto de acceso activo por carecer este de salida a
Internet. El origen fue una sincronización de ficheros desde el equipo de desarrollo que no
excluía `server/.env`, fichero que pertenece al concentrador. Se añadió una comprobación de
coherencia que verifica que el intermediario configurado es el local y que el prefijo de tema
coincide con el que el nodo publica realmente, tomándolo del propio intermediario en lugar de
suponerlo. La sincronización se automatizó en un procedimiento que fija las exclusiones, dado
que escribirlas a mano ya había producido este error y, en otra ocasión, directorios anidados.

## 4. Datos capturados

| Campaña | Fichero | Muestras | Muestras válidas | Observaciones |
| :--- | :--- | :--- | :--- | :--- |
| [EXP-002](../EXPERIMENTOS.md) | `2026-08-26-vibration.csv` | 7 ráfagas | 6 con fundamental identificada | Caracterización, no entrenamiento |
| [EXP-002](../EXPERIMENTOS.md) | `2026-08-26.csv` | 259 tramas | 258 | Salto térmico de \mbox{5,7 °C} |

Resultados principales de la caracterización:

| Magnitud | Valor |
| :--- | :--- |
| Frecuencia fundamental del activo | \mbox{49,77 Hz}, desviación 0,08, coeficiente de variación 0,15 % |
| Posición en el espectro | Tercer pico, tras los dos modos de la resonancia |
| Amplitud en la fundamental | \mbox{0,0660 m/s²}, coeficiente de variación 7,4 % |
| Valor eficaz filtrado | \mbox{0,062 m/s²} (mediana) |
| Kurtosis filtrada | 2,48 a 7,35, frente al valor fijo de 1,75 anterior |
| Duración de la captura | \mbox{1024 ms} en las siete ráfagas, sin desviación |

Las capturas de las sesiones anteriores, correspondientes a la puesta a punto, se archivaron
en subdirectorios identificados como descarte y no forman parte del conjunto de datos.

## 5. Bloqueos

**Campaña de referencia pendiente.** Es el único bloqueo que queda para pasar a la Fase 4. El
firmware y el concentrador están validados.

**Sensibilidad limitada por el acoplamiento.** Con una fijación adhesiva la banda fiable es
\mbox{0-150 Hz}. Ello excluye la detección de deterioro incipiente de rodamientos por
impulsividad, que reside en frecuencias superiores. La limitación está medida y acotada, y su
corrección exigiría un acoplamiento rígido, atornillado o magnético, fuera del alcance del
trabajo.

**Registro de dedicación inexistente.** Sin constancia de las horas invertidas no es posible
contrastar el avance con el reparto previsto.

## 6. Riesgos

**Nuevo — resonancia del acoplamiento del sensor.** Materializado y mitigado. Concentra en
torno al 95 % de la energía medida en \mbox{397-448 Hz}. Se mitiga con el filtro paso bajo en
los estadísticos temporales y con la publicación de tres picos espectrales. El riesgo residual
es la reducción de sensibilidad, que queda cuantificada.

**Nuevo — pérdida irreversible de información por el procesado en el borde.** El nodo
transmite características y no señal, de modo que un defecto en su cálculo no es corregible
en el concentrador, y una modificación posterior de la definición invalida el conjunto de
referencia. Se mitiga cerrando el firmware antes de iniciar la campaña.

**Nuevo — la sincronización de ficheros puede destruir la configuración del concentrador.**
Materializado: dejó el registrador suscrito al intermediario público. Se mitiga con las
exclusiones fijadas en el procedimiento de sincronización y con la comprobación de coherencia
de la configuración.

**Actualizado — el acelerómetro no transmite la vibración del activo.** Queda **mitigado**
por el cambio de punto de medida. El nivel pasó de \mbox{0,047} a \mbox{0,062 m/s²} en la
banda útil y la fundamental se identifica en la práctica totalidad de las ráfagas, frente al
8 % anterior.

**Actualizado — corrupción de una muestra aislada.** Se mantiene mitigada, con el umbral
recalibrado sobre la pendiente medida. Se registraron 17 rechazos por continuidad en la
ventana de caracterización.

## 7. Próximos pasos

1. Campaña de referencia en estado nominal, con registro en `docs/EXPERIMENTOS.md`
   *(Fase 3)*.
2. Fotografía de detalle de la fijación adoptada sobre el tubo de descarga, para completar el
   archivo del banco *(Fase 3)*.
3. Limpieza del conjunto de datos y extracción de las características derivadas en el
   concentrador *(Fase 4)*.
4. Ajuste del modelo sobre el estado nominal y selección del umbral de decisión *(Fase 4)*.

## 8. Impacto en la memoria

Con lo avanzado en este periodo se han redactado:

- **`A1-anexo-hardware.tex`**: la selección del punto de medida, con la figura anotada de los
  puntos evaluados y el cuadro comparativo, y la explicación del descarte de la cúpula por la
  suspensión interna del compresor.
- **`05-diseno.tex`**: pendiente de incorporar la caracterización de la resonancia y las dos
  correcciones adoptadas como decisión de diseño.

Este periodo aporta además material para el capítulo de resultados que antes no existía: la
validación de la cadena de adquisición, la eficacia de las comprobaciones de integridad y la
repetibilidad de las características, todas ellas procedentes de una campaña registrada.

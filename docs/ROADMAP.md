# Roadmap por Fases

Alineado con las tareas de la solicitud de TFM (6 ECTS ≈ 150 h). El reparto de horas es
orientativo; lo que importa es el orden de dependencias.

Leyenda: ✅ hecho · 🔄 en curso · ⬜ pendiente

---

## Fase 0 — Definición del escenario de prueba ✅ (~10 h)
*Tarea TFM: "Definición del escenario de prueba"*
- ✅ Activo representativo elegido: compresor de sistema de refrigeración doméstico.
- ✅ Variables físicas de interés: vibración, temperatura, firma acústica.
- ⬜ Caracterización documentada de la firma operativa nominal (depende de Fase 3).

## Fase 1 — Diseño de la arquitectura ✅ (~15 h)
*Tarea TFM: "Diseño de la arquitectura del sistema"*
- ✅ Modelo Edge–Fog definido: ESP32 → MQTT → Raspberry Pi.
- ✅ Modelo de intercambio de datos: JSON de 9 variables sobre `fridge/sensors`.
- ✅ Documentado en [ARCHITECTURE.md](ARCHITECTURE.md) y [DATA_SCHEMA.md](DATA_SCHEMA.md).

## Fase 2 — Selección e integración de hardware ✅ (~30 h)
*Tarea TFM: "Selección de componentes de hardware y software"*
- ✅ ESP32 + MPU-6050 (I2C) + DS18B20 (1-Wire) + INMP441 (I2S) integrados.
- ✅ Lectura simultánea de los tres sensores en el mismo ciclo.
- ✅ Auto-recuperación del bus I2C ante desconexión por vibración.
- ✅ Payload JSON consolidado de 9 variables.
- ✅ Wi-Fi WPA/WPA2 con diagnóstico de errores y timeout.
- ✅ Cliente MQTT con reconexión no bloqueante.

## Fase 3 — Conectividad y captura de datos 🔄 (~25 h)
Solo queda la campaña de referencia, que es tiempo de reloj. El trabajo activo está en la Fase 4.
- ✅ **Hub desplegado en la Raspberry Pi** (2026-08-25). La Pi genera su propia red Wi-Fi
      (punto de acceso) y el nodo se conecta directamente a ella, sin router intermedio: la
      IP del broker queda fija en `10.42.0.1` y deja de depender del DHCP ajeno, que durante
      la puesta a punto cambió de subred cuatro veces. Mosquitto y el logger arrancan solos
      tras un corte de corriente. Aprovisionamiento en `server/provision-pi.sh`, verificación
      con `provision-pi.sh comprobar`. Ver [informe](informes/2026-08-25-despliegue-hub.md).
- ✅ Validado extremo a extremo ESP32 → broker (2026-08-24). El nodo publica en ambos
      topics; verificado por suscripción directa.
- ✅ Logger `server/mqtt_logger.py` probado extremo a extremo con tramas sintéticas:
      escribe los dos CSV con sus cabeceras y descarta JSON malformado sin caerse
      (2026-08-24). Pendiente de estrenar con datos reales.
- ✅ Nodo redirigido al broker local (2026-08-25). Se abandona el broker público.
- ✅ **Componente tonal de alta frecuencia acotada por software** (2026-08-26). Al reubicar
      el sensor desde la cúpula del compresor a un punto con mejor transmisión, el nivel de
      vibración subió entre 9 y 20 veces según el eje, y apareció una componente entre 398 Hz
      y 448 Hz que se lleva el 95 % de la energía. Se atribuyó entonces a una resonancia del
      pegado adhesivo; **el 26 se demostró que es el noveno armónico del giro, es decir un
      fallo real** (ver el hito siguiente). Dejaba
      `kurt_z` clavada en 1,75 —el 1,5 de una senoide pura— y desplazaba la fundamental del
      compresor fuera del pico dominante. Dos correcciones, ambas en el nodo porque lo que
      allí se descarta no se recupera en el hub:
      1. **Filtro paso bajo a 150 Hz** aplicado solo a `rms`, `peak` y `kurt`, que se
         calculan en el tiempo e integran toda la banda. El espectro se deja sin filtrar
         para poder seguir caracterizando esa componente. Fue la decisión que hizo posible
         detectar el fallo.
      2. **Tres picos espectrales por eje** en lugar del dominante. Se prefirió a acotar la
         banda a un límite fijo porque las componentes se extendían entre 398 Hz y 497 Hz.
         Ese límite habría dejado el fallo fuera de la banda examinada. 27/27 pruebas en el PC.
- ✅ Umbral de continuidad recalibrado a 6 m/s² (2026-08-26). El valor inicial de 3 m/s²
      quedó invalidado por los datos: la familia armónica produce una pendiente **legítima**
      de 2,6 m/s²/ms, el 87 % de ese umbral, con lo que habría rechazado muestras buenas.
- ✅ **Validado en placa** (2026-08-26, [EXP-002](EXPERIMENTOS.md)). `kurt_z` pasa de estar
      fija en 1,75 a variar entre 2,48 y 7,35, y la fundamental del compresor se identifica en
      **6 de 7 ráfagas** a 49,77 Hz (CV 0,15 %) como tercer pico. Amplitud 0,0660 m/s² con
      CV del 7,4 %, lo que sitúa el umbral de detección en un cambio del 21 %. Ver
      [informe](informes/2026-08-26-punto-medida-resonancia.md).
- ✅ **Punto de medida seleccionado: el tubo de descarga** (2026-08-26). Se descartó la cúpula
      del compresor: un compresor hermético lleva el motor suspendido sobre muelles internos,
      de modo que la cúpula es el lado amortiguado de esa suspensión. El traslado elevó el
      nivel entre 9 y 20 veces. El 95 % de ese incremento está en la banda de la familia
      armónica y no en la que describen los estadísticos filtrados, cuya ganancia es de ~1,6
      veces. Se creyó una pérdida y era lo contrario: es la banda donde estaba el fallo.
- ✅ **Comprobación de continuidad entre muestras consecutivas** (2026-08-25). Era el
      bloqueo determinante. La corrupción de una muestra por ráfaga persistía: se midió
      `kurt_x` = 1001 con `peak_x` = 10,6154, que coincide con la predicción analítica para
      un único impulso aislado (1001,6). La comprobación de plausibilidad por módulo del
      vector **no detecta la caída de un solo eje**, límite demostrado en placa. Se añadió
      `isContinuous()` en `device/device.ino`: un salto > `ACC_STEP_MAX_MS2` = 3 m/s² entre
      dos muestras consecutivas del mismo eje (6x de margen sobre la pendiente físicamente
      alcanzable a 1 ms) se trata igual que un fallo de módulo, reutilizando el mecanismo de
      reintento único ya existente. Contadores `cont_rejects`/`total_cont_rejects` añadidos
      al payload de ráfaga para diagnóstico de causa raíz (EMI, conector suelto o lectura no
      atómica). **Pendiente de verificar en placa** (no hay `arduino-cli` en el equipo de
      desarrollo).
- ✅ **Contador de ráfagas calculadas pero no publicadas** (2026-08-25). Se observaron huecos
      de 102 s y 73 s con `failed_bursts` a cero: la publicación va condicionada al estado de
      la conexión y, si no está establecida, la ráfaga se calculaba y se perdía sin dejar
      rastro. Añadido `unpublishedBursts`/`unpublished_bursts` en `device/device.ino`, mismo
      patrón que `failed_bursts`: contador acumulado desde el arranque, incrementado en el
      `else` de la publicación a `TOPIC_BURST`, visible en la siguiente ráfaga que sí se
      publique (la ráfaga perdida en sí nunca llega al broker). **Pendiente de verificar en
      placa** (no hay `arduino-cli` en el equipo de desarrollo).
- ✅ **Fallo real detectado y caracterizado** (2026-08-26,
      [EXP-003](EXPERIMENTOS.md) / [EXP-004](EXPERIMENTOS.md)). El segundo compresor tiene un
      fallo no inducido con **verdad de referencia independiente de la instrumentación**: un
      tono audible que el operador percibe. Las componentes que se atribuían al montaje son
      **tres simultáneas en 398, 448 y 497 Hz**: los armónicos **8×, 9× y 10×** de la
      frecuencia de giro, cada uno dentro del **0,05 %** del entero. Una resonancia estructural
      no produce tres componentes en múltiplos enteros exactos de una frecuencia que además
      varía. Confirmado por el canal acústico, que no comparte sensor ni cadena: `aud_b1`
      0,987 frente a 0,034 del activo nominal, con el reparto de energía **invertido** entre
      ambos. Presente en 627/676 ráfagas del activo con fallo y en 0/45 del de referencia.
      Ver [informe](informes/2026-08-26-fallo-real-noveno-armonico.md).
      Consecuencias: la firma **no aparece** en `rms`, `peak` ni `kurt` —el filtro a 150 Hz
      la elimina—, de modo que su detección depende por completo de los tres picos
      espectrales sin filtrar y de las bandas acústicas. Las dos correcciones del hito
      anterior, adoptadas bajo la interpretación equivocada, son las que hicieron posible
      registrarlo: acotar la búsqueda espectral a la banda fiable, alternativa que se valoró,
      lo habría dejado fuera.
- ⬜ **Medir la resonancia real del acoplamiento.** El corte del filtro en 150 Hz se derivó
      de la regla de un tercio aplicada a los 448 Hz. Refutada esa atribución, el valor es
      una cota conservadora **sin respaldo experimental**. No es bloqueante para la Fase 4.
- ⬜ **Verificar la alimentación del nodo.** `total_retries` volvió de 29 a 0, y ese contador
      solo puede crecer: hubo un reinicio no explicado del microcontrolador.
- ⬜ Corregir `noise` del canal lento: promedia sobre 4 ms cuando el periodo de la señal es
      de 22,8 ms, lo que la hace inservible. Afecta solo a esa variable.
      **Corrección de un diagnóstico anterior:** se dio por sentado que el reparto de energía
      acústica estaba saturado y que el canal duplicaba al acelerómetro, y se planteó
      rediseñar el acoplamiento del micrófono. Era falso en ambos extremos. El valor extremo
      de `aud_b0` en el activo nominal (0,947) y de `aud_b1` en el activo con fallo (0,987)
      **son la medida**, no un defecto de escalado, y su inversión entre los dos activos es
      la confirmación independiente del fallo. El canal se deja como está.
- ✅ **Campaña de referencia completada** (2026-08-27, [EXP-005](EXPERIMENTOS.md)): 19,04 h
      continuas, 1868 ráfagas, 467 útiles en **22 episodios de marcha**. Ciclo nocturno regular
      de 30 min cada 84 min. Es lo que hizo posible la validación cruzada por episodios.
- ~~Campaña baseline: 12 h continuas~~ *(planificación original, superada por EXP-005)*
      en estado nominal, con la cadencia de ráfaga doblada a 15 s. Se reduce desde las ≥24 h previstas inicialmente, y la reducción se
      justifica en dos puntos:
      1. El **diferencial térmico** (`motorTemp − tempExt`) en lugar de la temperatura
         absoluta elimina la deriva ambiental de la formulación, con lo que deja de ser
         necesario cubrir el ciclo día/noche completo.
      2. **Doblar la cadencia** a una ráfaga cada 15 s da 2880 ráfagas en 12 h, holgado para
         el ajuste del modelo. Las características por ráfaga son idénticas y comparables:
         solo cambia la densidad temporal.
      Lo que **no** se puede acortar es la cobertura de ciclos de marcha/parada y de al menos
      un desescarche, que son fenómenos de tiempo de reloj. Por debajo de 8 h la cobertura de
      ciclos se estrecha y probablemente no se capture ningún desescarche, con lo que cada
      desescarche de las campañas de fallo aparecería como falso positivo.
- ⬜ **Montaje mecánico definitivo del sensor** (acoplamiento rígido al chasis; un sensor
      mal fijado mide su propio soporte, no el motor). **Prioritario:** con el compresor en
      marcha se midieron valores eficaces de 0,07-0,98 m/s², magnitud baja para el activo y
      compatible con una fijación insuficientemente rígida. Ningún modelo puede discriminar
      una señal que el sensor no llega a registrar.
- ✅ Migración del muestreo a `millis()` no bloqueante (2026-08-19).
- ✅ Muestreo por ráfagas a 1 kHz con extracción de características en el nodo
      (2026-08-19). 1024 muestras/ráfaga, resolución 0,98 Hz. Banda útil hasta 260 Hz, no
      500: la limita el filtro interno del sensor, no Nyquist. Publicado
      en el topic `fridge/vibration`. Ver
      [informe](informes/2026-08-19-muestreo-rafagas.md).
- ✅ **Firmware verificado en la placa** (2026-08-24). `ms_capture` = 1024 ms en todas las
      ráfagas observadas, cálculo de características en 30 ms, y frecuencia dominante de
      49,1 Hz coincidente en los tres ejes con el compresor en marcha — el régimen esperado
      de un motor de dos polos a 50 Hz con deslizamiento.
- ✅ **Adquisición robusta frente a fallos del bus I2C** (2026-08-24). Se localizaron dos
      defectos que corrompían el dato en silencio, ambos por bibliotecas que no propagan
      los errores del bus: `Wire.read()` devolviendo −1 truncado a `0xFF`, y
      `mpu.getEvent()` de Adafruit devolviendo `true` sobre un buffer sin inicializar. Una
      sola muestra corrupta entre 1024 elevaba la kurtosis de 2,9 a 847. Corregido con
      validación de la transacción en cuatro puntos, reintento único por muestra,
      comprobación de plausibilidad física y lectura directa de los registros del sensor.
      Ver [informe](informes/2026-08-24-robustez-i2c.md).
- ✅ Contadores de salud del nodo: `bad_frames`, `retries` y `total_retries`, que hacen
      medible la calidad de cada medida en lugar de suponerla.
- ⬜ **Soldar el conexionado del sensor** con alivio de tensión. **Sube de prioridad**: los
      reintentos del bus descartan el 32 % de las ráfagas en marcha del nodo A y, peor, las que
      pasan con 4-10 reintentos fabrican picos espectrales espurios que imitan un fallo. No es
      solo pérdida de datos: es contaminación de la característica que decide.
- ⬜ Validar en placa la lectura del rango del giróscopo (`updateGyroScale()`).

## Fase 4 — Motor de análisis inteligente 🔄 (~35 h) ← **FASE ACTUAL**
*Tarea TFM: "Desarrollo del motor de análisis inteligente"*
- ✅ **Baseline preliminar en pie** (2026-08-26, `server/analisis/baseline_anomalias.py`).
      Isolation Forest ajustado solo sobre el activo nominal: **676/676** ráfagas del activo
      con fallo detectadas, 2,2 % de falsos positivos, umbral en el percentil 1 del nominal.
      Dos hallazgos condicionan todo lo que venga después:
      1. **Las características deben ser adimensionales.** Un detector sobre `rms`, `peak` y
         `kurt` da el 99,8 % *sin usar ninguna característica que contenga la firma del
         fallo*: el nivel de los dos activos difiere en un factor 5,5, de modo que separa
         máquinas y no estados. Es el modo de error al que este contraste está expuesto.
      2. **Una regla de una comparación basta.** El número de picos espectrales
         significativos (amplitud ≥ 20 % de la mayor) vale 1 en 465 de las 467 ráfagas
         nominales y 2 o 3 en las 656 del activo con fallo: separación de **6,9 sd**, la
         siguiente característica está en 4,1. Se embarca en el ESP32 con una comparación, lo
         que adelanta trabajo de la Fase 6. Lo que la cifra no dice: el intervalo de decisión
         sigue siendo un punto, así que **el margen de tolerancia no está estimado**. Se
         conserva `r2` como corroboración porque identifica *qué* armónico aparece y no solo
         cuántos picos hay.
      **Validado por episodios** (2026-08-27, con EXP-005): dejando fuera un arranque completo
      y midiendo sobre una condición no vista, la regla da **0,5 % de falsos positivos de
      media y 8,3 % en el peor episodio**, frente al 25-34 % en el peor episodio de los seis
      candidatos restantes. Ese es el número que cuenta para el despliegue: un peor caso alto
      significa tandas de alarmas falsas seguidas, no una aislada cada tanto.
- ✅ **Explicada la asimetría de descarte** (2026-08-26). No es un problema de calidad: el
      filtro de contadores lo supera el 80 % de las ráfagas del nodo A y el 87 % del nodo B,
      cifras equivalentes. Lo que difiere es el **ciclo de trabajo**: el nodo A se capturó con
      el compresor en marcha en el 27 % de las ráfagas y el nodo B en el 99 %. De ahí el
      rendimiento: **24 ráfagas útiles/h en el nodo A** frente a 99 en el nodo B. La campaña
      de referencia debe dimensionarse sobre esa cifra, no sobre la cadencia de publicación.
      Nota lateral, sin confirmar: un 99 % de tiempo en marcha frente al 63 % medido sobre
      20,6 h del nodo A es en sí mismo compatible con un compresor que no alcanza consigna.
- ⬜ Limpieza del dataset: filtrado de valores centinela (ver DATA_SCHEMA.md).
- ✅ **Criterio de filtrado por calidad establecido**: solo contadores **por ráfaga**
      (`retries` ≤ 5, `cont_rejects` ≤ 2, `kurt_x` en [1, 20]). `bad_frames` y los contadores
      con prefijo `total_` son **acumulados desde el arranque**: exigirles cero descarta el
      100 % de las ráfagas. Documentado en el script y en la memoria.
- ✅ **Selección de eje por repetibilidad medida**: `kurt_x` está en rango físico en el 100 %
      de las ráfagas de ambos nodos, mientras `kurt_z` lo está en el 59 % del nodo A y el
      44 % del nodo B. El eje X es el único utilizable sin más trabajo de montaje.
- ✅ Extracción de características en el nodo: RMS, pico, kurtosis, frecuencia y amplitud
      dominantes por eje, energía acústica por bandas (`device/signal_processing.h`, verificado en PC).
- ⬜ Características derivadas en el hub: gradientes térmicos, evolución de armónicos,
      duración de los ciclos de marcha y parada.
- ✅ **Selección del modelo entre 7 candidatos** (`server/analisis/comparar_modelos.py`), en
      el mismo punto de operación y con 5 criterios declarados. Dos hallazgos: la **tasa de
      detección no discrimina** (los 7 dan el 100 %), y dos candidatos caen por calibración —
      One-Class SVM da un 46 % de falsos positivos donde el umbral pide un 5 %, porque con 45
      observaciones y 11 dimensiones sus hiperparámetros no son ajustables.
- ✅ **Corregida una definición de característica defectuosa** (2026-08-26). Los cocientes se
      calculaban sobre los picos tal como los publica el firmware, que los ordena **por
      amplitud**: en 60 de 676 ráfagas el armónico del fallo le quita la posición de dominante
      a la fundamental y el mismo fenómeno daba cocientes de 9,0 y de 0,111. Corregido
      ordenando por **frecuencia** y descartando antes los picos por debajo del 20 % de la
      amplitud mayor. El hallazgo se refuerza: son **8×, 9× y 10×** simultáneos, no una sola
      componente. Ver la corrección al final de [EXPERIMENTOS.md](EXPERIMENTOS.md).
- ⬜ **Ampliar los picos espectrales del firmware.** Con tres picos, uno de ellos la
      fundamental, solo caben dos armónicos por ráfaga: la familia 8×/9×/10× no se puede
      caracterizar completa. No reflashear con una campaña en curso.
- ✅ **Localizados los puntos ciegos del detector** (2026-08-27,
      `server/analisis/cobertura_modos.py`, datos **sintéticos**, no evidencia). Solo hay un
      modo de fallo observado, y elegir el modelo por sus falsos positivos contra ese único
      fallo es sobreajuste. La regla sobre `n_picos` resulta **ciega a 3 de 4** direcciones de
      fallo típicas: detecta lo que añade componentes espectrales, no lo que altera la amplitud
      o la impulsividad.
- ✅ **Corregida la ceguera a la amplitud de las características adimensionales** (2026-08-27).
      Son ciegas por construcción a un fallo que solo cambie el nivel, porque todo es cociente
      respecto a la fundamental. Añadidas `rms_x_rel` y `adom_x_rel`, normalizadas por la
      mediana del **propio** activo: adimensionales en la forma, específicas en el valor. La
      envolvente pasa a detectar el 99 % del desequilibrio de masa simulado.
      *Contrapartida:* el nodo debe aprender la mediana de su activo en una fase de referencia
      antes de poder juzgar.
- ✅ **Elección de modelo REVISADA** (2026-08-27). La conclusión anterior —«la regla supera a
      los modelos de ML»— era **engañosa**. Dando a cada modelo únicamente `n_picos`, los seis
      convergen al **mismo 8,3 %**: con una dimensión hay una sola frontera. La comparación
      original era injusta (una característica bien elegida frente a las 15, varias sin poder de
      separación). **El mérito era de la característica, no del algoritmo.** Y esa característica
      se eligió *sabiendo cuál era el fallo*, así que no generaliza: ciega a 4 de 5 direcciones.
      Además el 25 % del peor episodio de la envolvente estaba mal presentado: son **3 ráfagas
      de 12**, el ponderado por ráfagas es **5,6 %** y 11 de 22 episodios dan 0 %.
      **Detector principal: envolvente robusta** (5 de 5 direcciones, forma cuadrática de
      900 bytes). **Confirmación: `n_picos > 1`.** Auditoría completa en
      `server/analisis/cuadernos/auditoria-fase4.ipynb`.
- ✅ **Protocolo sin sesgo de espionaje** (2026-08-27, `server/analisis/protocolo.py`). Todo el
      análisis anterior usaba el conjunto con fallo para decidir: `n_picos` se eligió ordenando
      las candidatas por separación *frente al fallo*. El protocolo limpio separa desarrollo y
      prueba **cronológicamente por episodios**, toma todas las decisiones solo con el activo
      sano, y mira la evaluación una vez. **Elige un modelo distinto (LOF), con 7,8 % de falsos
      positivos sobre episodios nunca vistos y 100 % de detección.**
- ✅ **Refutado el criterio de embarcabilidad que yo mismo había impuesto** (2026-08-27). Había
      etiquetado modelos como «no embarcables» por suposición. Medido: el mayor ocupa 274 KB y el
      más costoso exige 15 150 operaciones (~0,1 ms a 240 MHz) frente a una ráfaga cada 30 s. La
      placa tiene 8 MB de PSRAM. **Los cinco caben**, y ese criterio sesgó la elección hacia lo
      simple sin base.
- ⬜ **Embarcar el detector** en el ESP32, con histéresis y guardián de reintentos.
- ⬜ Clasificación de estados de salud del sistema.
- ✅ **Validación cruzada por episodios implementada** (`comparar_modelos.py`). Era la que
      faltaba: con un solo episodio nominal, cualquier partición dejaba en entrenamiento y en
      prueba ráfagas de la misma condición, separadas 30 s y correlacionadas.
- ⬜ Métricas de evaluación y matriz de confusión. **El conjunto de evaluación ya existe**
      sin necesidad de inducir ningún fallo: EXP-003 aporta 676 ráfagas de un fallo real con
      etiqueta fiable, y EXP-004 el control nominal. Limitación a declarar: son máquinas
      distintas, de modo que el contraste no separa el efecto del fallo del de la
      variabilidad entre ejemplares.
- ✅ **Segmentación marcha/parada resuelta y corregida** (2026-08-27). El umbral de 0,05 m/s²
      fijado con EXP-004 **era incorrecto**: caía dentro del grupo de parado, cuyo extremo llega
      a 0,06, y producía episodios espurios de una sola ráfaga. Además el valle es propio de
      cada máquina (0,198 en el nodo A, 0,060 en el nodo B), de modo que ningún umbral absoluto
      sirve para las dos. Se deriva ahora de los datos separando los dos modos del logaritmo del
      valor eficaz, sin hiperparámetros.
- ✅ **Descubierto que los reintentos del bus I2C fabrican la firma del fallo** (2026-08-27).
      En el activo NOMINAL, con más de 10 reintentos la mediana de picos significativos pasa de
      1 a 3 y la fundamental estimada cae de 49 Hz a 20 Hz: una muestra corrupta inyecta ruido
      de banda ancha. **El filtro de calidad es parte del detector, no un preproceso**, y el
      corte se recalibró de 5 a **3 reintentos** (467 ráfagas con 0,4 % de artefactos, la misma
      tasa que exigir cero, con un 79 % más de datos).
      **Comprobado que la firma de EXP-003 no es ese artefacto:** restringiendo ambos conjuntos
      a cero reintentos, el nodo A da un pico en 260/261 y el nodo B tres en 430/443, con
      cocientes de **8,0016 (CV 0,029 %)** y 9,0035 (CV 0,106 %). Y la firma del nodo B es
      idéntica con reintentos y sin ellos, mientras la del nodo A se derrumba.

## Fase 5 — Validación experimental 🔄 (~20 h)
*Tarea TFM: "Validación experimental"*
- ✅ **Un caso de fallo real ya validado** (EXP-003). Es mejor evidencia que un fallo
      inducido: la etiqueta no la fija quien monta el experimento, sino que la aporta un tono
      audible ajeno a la instrumentación. Cubre la parte de la validación que consiste en
      demostrar que el sistema detecta algo que ocurre de verdad.
- ⬜ **Provocar paradas en el activo con fallo.** Solo tiene 2 episodios de marcha porque
      permanece en marcha el 99 % del tiempo, de modo que alargar la captura da más horas del
      mismo episodio y no más episodios. Desconectarlo y reconectarlo unas cuantas veces pasa
      de 2 episodios a 5 o 6 en un par de horas, y es lo que permite afirmar que la firma es
      estable entre arranques.
- ⬜ Inducción controlada de fallos **sobre el mismo activo**, que es lo que EXP-003 no
      puede dar: desequilibrio de masa, obstrucción de ventilación, aflojamiento de anclaje.
      Sin comparación dentro de una misma máquina no se separa el efecto del fallo del de la
      variabilidad entre ejemplares.
- ⬜ Calibración de umbrales y verificación de la precisión del diagnóstico por tipo de fallo.
- ⬜ Registro de cada campaña en [EXPERIMENTOS.md](EXPERIMENTOS.md).

## Fase 6 — Inferencia en el Edge 🔄 (~15 h)
- ✅ **Detector embarcado escrito y verificado en el PC** (2026-08-27). `device/detector.h`, sin
      dependencias de Arduino, igual que `signal_processing.h`. Verificado contra scikit-learn
      sobre las **1161 ráfagas reales**: 0 veredictos discrepantes, error de 2,1e-07 en LOF.
- ✅ **Exportación del modelo a cabecera C++** (`server/analisis/exportar_modelo.py` →
      `device/modelo_referencia.h`, generada). Lleva anotada la campaña y la fecha de
      procedencia, de modo que un firmware en la placa siempre se puede rastrear a los datos
      que lo produjeron.
- ✅ **Integrado en `device.ino`** con topic propio `fridge/status`, histéresis de 3 ráfagas y
      guardián de reintentos. Payload de ráfaga **sin cambios** (45 campos verificados): la
      serie histórica sigue siendo comparable.
- ✅ **El registrador guarda el tercer canal** (`YYYY-MM-DD-status.csv`). Era un fallo
      silencioso: el nodo habría publicado y el dato se habría perdido sin que nada protestase.
      `provision-pi.sh comprobar` verifica ahora que el registrador conoce los tres topics.
- ✅ **Histéresis calibrada sobre datos reales**: exigiendo 3 ráfagas consecutivas se emiten
      **0 avisos falsos** en las 505 ráfagas nominales (con 1 ráfaga serían 22), y el fallo se
      notifica.
- ⬜ **Compilar y flashear en el nodo A** (falta `arduino-cli` y la placa). El modelo lleva las
      medianas del nodo A: **flashearlo en el nodo B daría `not_evaluable` en el 100 %** de las
      ráfagas, porque su nivel en marcha queda por debajo del umbral del nodo A. El modelo es
      específico del activo.
- ⬜ Verificar en placa que el ESP32 coincide con Python, cruzando el CSV de ráfaga con el de
      estado por marca de tiempo, y medir `us_inference` y la ocupación real.
- ⬜ Portar el modelo al ESP32 **a mano en C++, sin TensorFlow Lite Micro**. Ese entorno
      ejecuta **redes neuronales** y ninguno de los siete candidatos lo es: LOF es una búsqueda
      de vecinos, la envolvente una forma cuadrática, el bosque un conjunto de árboles. No es
      que TFLite Micro sea excesivo: **no puede ejecutarlos**. Y una red neuronal no era opción
      con 505 observaciones. Son ~15 líneas de C++ para la envolvente, ~60 para LOF.
- ⬜ `server/analisis/exportar_modelo.py` → `device/modelo_referencia.h`, generado y no editado
      a mano, con la campaña y la fecha de procedencia en un comentario.
- ⬜ **Guardián de reintentos**: el nodo debe negarse a emitir veredicto con más de 3
      reintentos, no juzgar la ráfaga. Sin él marca como fallo todo bus inestable.
- ⬜ **Histéresis**: N ráfagas anómalas consecutivas antes de notificar.
- ⬜ **Fase de referencia en el nodo**: las características normalizadas por el propio activo
      exigen que aprenda su propia mediana antes de poder juzgar.
- ⬜ Publicar el veredicto de salud en un topic propio (`fridge/status`), reduciendo el
      tráfico de telemetría cruda.
- ⬜ Medir latencia de inferencia y consumo en el nodo.

## Fase 7 — Prueba en entorno real y memoria ⬜ (~20 h)
*Tarea TFM: "Pruebas en entorno real"*
- ⬜ Despliegue de la PoC sobre un activo operativo en uso diario.
- ⬜ Evaluación de robustez de la arquitectura (uptime, pérdida de mensajes, falsos positivos).
- ⬜ Redacción de la memoria y preparación de la defensa.

---

## Riesgos identificados
| Riesgo | Impacto | Mitigación |
| :--- | :--- | :--- |
| ~~Muestreo a 1 Hz insuficiente para análisis frecuencial~~ | ~~Alto~~ → **Resuelto** (2026-08-19) | Muestreo por ráfagas a 1 kHz con características calculadas en el nodo. Pendiente de validar en placa. |
| ~~Captura contra broker público sin autenticación~~ | ~~Alto~~ → **Resuelto** (2026-08-25) | Broker local en la Pi sobre red aislada. El riesgo residual se traslada a la contraseña del Wi-Fi, que es ahora lo único que impide publicar tramas falsas |
| ~~La comprobación de plausibilidad por módulo no detecta la caída de un solo eje~~ | ~~Alto~~ → **Mitigado** (2026-08-25) — materializado: `kurt_x` = 1001 por una sola muestra corrupta, y con ella se inutilizan la kurtosis **y** la frecuencia dominante | Comprobación de continuidad entre muestras consecutivas (`isContinuous()`), que sí discrimina el artefacto. **Pendiente de verificar en placa.** |
| ~~Pérdida de datos no contabilizada~~ | ~~Alto~~ → **Mitigado** (2026-08-25) — era indistinguible de la ausencia de medida al analizar el CSV | Contador `unpublished_bursts` de ráfagas calculadas y no publicadas por falta de conexión MQTT. **Pendiente de verificar en placa.** |
| Resonancia del acoplamiento adhesivo del sensor (398–448 Hz) | ~~Alto~~ → **Mitigado** (2026-08-26): validado en placa que `kurt_z` recupera su rango y la fundamental se identifica en 6 de 7 ráfagas | Filtro paso bajo a 150 Hz en los estadísticos temporales y tres picos espectrales. Banda fiable: 0–150 Hz. Riesgo residual: sin detección de rodamientos por impulsividad |
| ~~Resonancia sin caracterizar~~ | ~~Alto~~ — se lleva el 95 % de la energía; dejaba `kurt` sin información diagnóstica y desplazaba la fundamental fuera del pico dominante | Filtro paso bajo a 150 Hz en los estadísticos temporales y tres picos espectrales en lugar de uno. Banda fiable resultante: 0–150 Hz. La solución de fondo es un acoplamiento rígido (imán o atornillado), fuera del alcance actual |
| El acelerómetro no transmite la vibración del activo | ~~Alto~~ → **Mitigado** (2026-08-26) por el cambio de punto de medida: el nivel subió de 0,047 a 0,35–0,69 m/s², de 2-3 veces el suelo de ruido a más de 20 | Se abandonó la cúpula del compresor, que el fabricante aísla del motor con muelles internos, por un punto con transmisión directa |
| Reinicios del nodo sin diagnóstico | Medio — rompen la continuidad temporal de la señal, que es lo que analiza el modelo | Verificar la alimentación; vigilar los contadores acumulados durante la campaña |
| ~~El canal acústico mide vibración estructural, no sonido~~ | ~~Medio~~ → **Descartado** (2026-08-26) | Era una interpretación errónea del reparto de energía por bandas. El canal aportó la confirmación independiente del fallo de EXP-003: `aud_b1` 0,987 frente a 0,034 del activo nominal. No es redundante con el acelerómetro y no se toca |
| Manipular ficheros con el logger en ejecución | Medio — el proceso conserva el acceso al fichero eliminado y sigue escribiendo en un destino invisible | Detener el servicio antes de tocar `server/data/`; la cabecera se escribe también si el fichero existe vacío |
| ~~La cadencia de la ráfaga no se sostiene en la placa~~ | ~~Medio~~ → **Descartado** (2026-08-24) | Medido en placa: `ms_capture` = 1024 ms sin desviación. El campo se conserva como control de calidad |
| Corrupción silenciosa por bibliotecas que no propagan errores del bus | **Alto** — materializado en dos puntos independientes; no produce ninguna señal externa y solo se aprecia al analizar la distribución de las características | Validación de la transacción en cuatro puntos y lectura directa de registros. Los contadores `bad_frames` y `retries` hacen medible la calidad del dato |
| Confusión entre el régimen mecánico (≈49 Hz) y la frecuencia de la red (50 Hz) | Medio — atribuir a la máquina una captación eléctrica falsea el diagnóstico | Están separados por menos de dos veces la resolución de 0,98 Hz: exigir acuerdo entre los tres ejes y contrastar con el compresor detenido |
| Fijación del sensor insuficientemente rígida | Medio — atenúa la señal y amplifica el traqueteo que degrada el bus. Se rebaja desde Alto: el montaje adhesivo actual transmitió el noveno armónico en 447,76 Hz con amplitud suficiente para identificarlo en el 99 % de las ráfagas, de modo que no impide la detección | Frecuencia de resonancia del acoplamiento **sin medir**: el corte del filtro a 150 Hz es una cota conservadora sin verificar |
| Ausencia de fallos reales que etiquetar | ~~Alto~~ → **Mitigado** (2026-08-26) | EXP-003 aporta 676 ráfagas de un fallo real con verdad de referencia externa (tono audible). Queda pendiente el fallo inducido **sobre el mismo activo**, que es lo que separa el efecto del fallo del de la variabilidad entre ejemplares |
| Desconexión I2C por vibración | Medio — huecos en el dataset | Ya mitigado por auto-recuperación; monitorizar tasa de ceros |
| `motorTemp` del MPU no es la temperatura real del motor | Medio — variable poco informativa | Tratarla como proxy; considerar segundo DS18B20 en carcasa. Útil en la práctica: distingue el compresor en marcha (42 °C) del parado (ambiente) |
| Desviación de cero de +2 m/s² en el eje vertical del acelerómetro | Bajo — el canal lento no queda calibrado en valor absoluto | Sin efecto sobre el análisis: la extracción de características elimina la continua, y kurtosis y frecuencia dominante son invariantes a la escala. Documentarlo |
| Deriva temporal sin RTC/NTP en el nodo | Bajo — marca de tiempo del hub | Aceptado; documentado en DATA_SCHEMA.md |

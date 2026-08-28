# Informe de avance — TFM Sistema IoT Edge para mantenimiento predictivo

**Fecha:** 2026-08-25 · **Periodo cubierto:** 2026-08-25
**Fase del roadmap:** 3 — Conectividad y captura de datos · **Horas acumuladas:** sin registrar

## 1. Resumen ejecutivo

El hub queda desplegado sobre la Raspberry Pi, que pasa a generar su propia red Wi-Fi para
que el nodo se conecte directamente a ella sin router intermedio. La cadena completa
—nodo, punto de acceso, *broker* y registrador— se ha verificado extremo a extremo y
sobrevive a un corte de corriente sin intervención. En paralelo, el análisis de las primeras
ráfagas registradas ha revelado que la corrupción de muestras aisladas **no está resuelta**,
que se produjo un reinicio no explicado del nodo y que el canal acústico no aporta
información aprovechable en su configuración actual. No se ha capturado ninguna campaña de
medida.

## 2. Trabajo realizado

| Tarea | Estado | Evidencia |
| :--- | :--- | :--- |
| Despliegue del hub sobre Raspberry Pi | Completada | `server/provision-pi.sh`, verificado en la máquina |
| Punto de acceso Wi-Fi propio en la Pi | Completada | Nodo asociado y publicando; IP fija `10.42.0.1` |
| Script de aprovisionamiento por fases, con reversión | Completada | `server/provision-pi.sh` (fases `paquetes`, `broker`, `logger`, `ap`, `todo`, `revertir`) |
| Verificación automática de la cadena de datos | Completada | `server/provision-pi.sh comprobar`, seis eslabones con veredicto |
| Registrador como servicio, con reinicio automático | Completada | Unidad `tfm-logger`, `Restart=always` |
| Persistencia de la configuración tras corte de corriente | Completada | Punto de acceso, *broker* y registrador arrancan solos |
| Corrección de la escala del giróscopo | Completada | `updateGyroScale()`, lee `GYRO_CONFIG` del dispositivo |
| Lectura de 8 bytes en la ráfaga (experimento posicional) | Implementada, **sin concluir** | `readRawAccel()`; el fallo persiste, luego no era posicional |
| Robustez del registrador ante fichero vacío | Completada | `server/mqtt_logger.py`, comprobación de tamaño; probado en PC |
| Retirada de los campos de diagnóstico temporales | Completada | Campos `dbg_*` eliminados del payload |
| Diagnóstico de Wi-Fi del nodo, restaurado | Completada | `setupWifi()`, desglose por código de estado |
| Captura de campañas de medida | **No realizada** | `server/data/` vacío; sin registros en `docs/EXPERIMENTOS.md` |

## 3. Incidencias y decisiones técnicas

**Decisión: la Pi genera su propia red en lugar de depender de un router.** Durante la
puesta a punto, el equipo que aloja el *broker* cambió de subred en cuatro ocasiones
(`10.36.53.x`, `10.245.52.x`, `10.144.94.x`, `10.45.127.x`). Como la dirección del *broker*
es una constante de compilación en el firmware, cada cambio obligaba a reprogramar el nodo.

Se resuelve poniendo la interfaz inalámbrica de la Pi en modo punto de acceso con
NetworkManager en modo compartido, que asigna siempre la dirección `10.42.0.1`. Con ello la
constante del firmware deja de depender de infraestructura ajena, el conjunto resulta
portátil —basta un enchufe— y la red queda aislada, lo que reduce el riesgo de que un
tercero publique tramas falsas en los *topics*. El nodo no necesita salida a Internet: solo
alcanzar el *broker*.

*Contrapartida asumida:* la interfaz inalámbrica no puede ser cliente y punto de acceso a la
vez, de modo que la Pi pierde su acceso a Internet por Wi-Fi. Las dependencias se instalan
antes de activar el punto de acceso, y la gestión puede mantenerse por cable.

**El aprovisionamiento se separa en fases por una razón de seguridad operativa.** Activar el
punto de acceso corta la red por la que llega la sesión remota. Si esa activación ocurriera
en medio de una secuencia de instalación, el proceso recibiría una señal de terminación con
el sistema a medio configurar. Por eso todas las comprobaciones se realizan antes de
modificar nada, la activación del punto de acceso es la última operación, y se lanza
desacoplada de la sesión mediante `systemd-run` para que se complete aunque la conexión se
pierda. Se genera además un informe en el sistema de ficheros de la Pi con los datos de
acceso, escrito antes de la activación.

**El equipo ya tenía un *broker* configurado.** La Pi es una máquina de integración
compartida y contaba con `/etc/mosquitto/conf.d/local.conf` declarando un `listener` en el
puerto 1883 abierto a la red y permitiendo conexiones anónimas: exactamente lo necesario. La
primera versión del script añadía su propia configuración, que colisionaba con la existente
e impedía arrancar el servicio.

*Decisión: inspeccionar antes de escribir, y escribir lo mínimo.* El script analiza ahora la
configuración efectiva —fichero principal más todos los incluidos— y decide entre cuatro
casos: si ya hay un `listener` abierto con conexiones anónimas no escribe nada; si el
`listener` está restringido a la interfaz local se limita a informar, sin modificar un
fichero ajeno; si falta solo el permiso de conexión anónima añade únicamente esa directiva;
y si no hay `listener` declarado crea uno. Ante cualquier fallo retira su propia
configuración y restaura el estado anterior antes de abortar. El criterio de fondo es que en
una máquina compartida dejar un servicio caído es peor que no haber intervenido.

**Corrupción de muestras: no resuelta, y el mecanismo de detección tiene un límite
demostrado.** Las ráfagas registradas presentan valores de kurtosis de 1001 en el eje
horizontal, con un valor de pico de 10,6154 m/s². La predicción analítica para un único
impulso aislado entre 1024 muestras, `kurt = (d⁴/n)/(d²/n + σ²)²`, arroja 1001,6 para esos
mismos valores, frente a los 1001,068 medidos. Se trata por tanto de **una sola muestra
corrupta por ráfaga**, y el valor de pico coincide con la componente continua del eje, lo
que indica que la muestra se lee próxima a cero.

El fallo se ha desplazado del eje vertical al horizontal al reorientar el sensor, siguiendo
al eje que soporta la gravedad. Eso confirma que no es un defecto asociado a un registro
concreto del sensor.

*Limitación de la comprobación de plausibilidad.* La verificación implementada opera sobre el
módulo del vector de aceleración, y **no puede detectar la caída de un solo eje** cuando los
restantes conservan magnitud suficiente. Se observa además que en las mismas ráfagas
afectadas la kurtosis del tercer eje también se eleva, lo que sugiere que la lectura corrupta
altera varios ejes de forma que el módulo permanece dentro de la banda admitida. La
comprobación es complementaria de la validación de la transacción, no sustitutiva, y para
este modo de fallo resulta insuficiente.

*Vía propuesta: continuidad entre muestras consecutivas.* Con un valor eficaz de vibración
entre 0,03 y 0,3 m/s² y el filtro interno del sensor a 260 Hz, la pendiente máxima
físicamente alcanzable es del orden de 0,5 m/s² por milisegundo. Un salto de 10,6 m/s² entre
dos muestras separadas 1 ms excede ese límite en un factor veinte, de modo que un umbral de
3 m/s² por muestra deja seis veces de margen sobre la física y discrimina el artefacto sin
ambigüedad. Pendiente de implementar.

**Consecuencia sobre la frecuencia dominante.** Un impulso aislado presenta espectro plano,
por lo que la muestra corrupta domina el espectro y desplaza el pico real. En las ráfagas
afectadas la frecuencia dominante del eje horizontal toma valores dispersos entre 19,6 y
178,2 Hz sin relación con el régimen de la máquina. La corrupción inutiliza por tanto **las
dos características principales**: la kurtosis y la frecuencia dominante.

**Reinicio no explicado del nodo.** El contador acumulado de reintentos es monótono
creciente por construcción. Se observó su vuelta a cero, desde 29, entre dos ráfagas
consecutivas, lo que solo puede corresponder a un reinicio del microcontrolador. No se
identificó la causa; la hipótesis de trabajo es una caída de tensión durante los picos de
consumo de la radio. Para una campaña prolongada la incidencia es relevante porque el
reinicio no deja más rastro que ese contador.

**Pérdida de ráfagas no contabilizada.** Se registraron intervalos de 102 s y 73 s entre
ráfagas consecutivas, frente a los 30 s nominales, con el contador de ráfagas descartadas a
cero. Las ráfagas se calcularon y se perdieron con posterioridad: la publicación se realiza
condicionada al estado de la conexión y, cuando esta no está establecida, la ráfaga se
descarta sin incrementar ningún contador. Es una carencia de instrumentación, porque impide
distinguir en el conjunto de datos la ausencia de medida de la pérdida de medida.

**El mecanismo de reintento funciona y es medible.** El contador de ráfagas descartadas se
mantiene a cero pese a una tasa de reintentos elevada, lo que confirma que los fallos
aislados se absorben. El coste temporal es observable en la duración de la captura, que pasa
de los 1024 ms nominales a 1036 ms en la ráfaga con 35 reintentos, del orden de 0,34 ms por
reintento. La tasa medida, próxima a 37 reintentos por minuto, indica que el conexionado no
está en condiciones para una exposición prolongada a la vibración.

**El canal acústico no aporta información.** La fracción de energía en la banda de 0 a
250 Hz se mantuvo entre 0,92 y 0,997 en todas las ráfagas observadas, concentrando la
práctica totalidad de la energía en quince de los quinientos doce intervalos frecuenciales
disponibles. La frecuencia dominante de vibración medida en el mismo instante, en torno a
43,8 Hz, apunta a la causa: el micrófono está solidario al chasis y recibe la vibración
estructural por conducción, que enmascara el sonido transmitido por el aire. El canal
duplica así lo que el acelerómetro ya mide con mejor sensor, y una característica
prácticamente constante no aporta capacidad discriminante al modelo.

*Vías de corrección.* La solución de fondo es mecánica: desacoplar el micrófono del chasis.
Como alternativa por software, elevar el límite inferior de las bandas por encima de la
componente estructural, lo que exige además normalizar la energía sobre el rango analizado y
no sobre el espectro completo, ya que en caso contrario las bandas superiores seguirían
resultando fracciones despreciables.

**La variable de nivel acústico del canal lento no es utilizable.** Se registraron valores
consecutivos entre 150 y 6832 con la máquina en régimen estable, un factor cuarenta y cinco.
La causa es la ventana de promediado: 64 muestras a 16 kHz equivalen a 4 ms, mientras que el
periodo de la señal dominante a 43,8 Hz es de 22,8 ms. Cada lectura captura en torno al 18 %
de un ciclo en una fase arbitraria, de modo que el valor obtenido depende del instante de
muestreo y no del nivel acústico. Corregirlo requiere ampliar la ventana hasta cubrir varios
ciclos.

**Fragilidad del registrador ante manipulación de los ficheros.** Durante una limpieza del
directorio de datos se eliminaron los ficheros con el servicio en ejecución y se volvieron a
crear vacíos. El resultado fue doble. Por un lado, la cabecera no se escribió, porque el
código solo la generaba cuando el fichero no existía. Por otro, y de mayor alcance, el
descriptor abierto por el proceso siguió apuntando al fichero original ya desvinculado del
sistema de ficheros, de modo que el registrador continuó escribiendo en un destino
inaccesible mientras el fichero visible permanecía vacío. La reapertura solo se produce al
cambiar la fecha, por lo que la situación se habría prolongado hasta la medianoche.

*Corrección adoptada:* la cabecera se escribe también cuando el fichero existe pero está
vacío, verificando su tamaño. Queda documentado como procedimiento que toda manipulación del
directorio de datos exige detener el servicio previamente.

## 4. Datos capturados

**No hubo campañas de medida en el periodo.** El directorio `server/data/` está vacío y
`docs/EXPERIMENTOS.md` no registra ninguna campaña.

| Campaña | Fichero | Muestras | Muestras válidas | Observaciones |
| :--- | :--- | :--- | :--- | :--- |
| — | — | — | — | Sin campañas en el periodo |

Las ráfagas analizadas en este informe proceden de la puesta a punto del hub y contienen
tanto muestras corruptas como una trama sintética inyectada por el propio script de
aprovisionamiento para verificar la cadena. Se apartaron a un subdirectorio identificado
como descarte, sin eliminarlas, por su valor como evidencia del diagnóstico.

## 5. Bloqueos

**La corrupción de una muestra por ráfaga sigue sin resolver, e inutiliza las dos
características principales.** Es el bloqueo determinante: mientras persista, la kurtosis y
la frecuencia dominante no son aprovechables y una campaña prolongada no produciría un
conjunto de datos válido. Requiere implementar la comprobación de continuidad entre muestras
consecutivas.

**El conexionado no resiste la vibración.** Una tasa próxima a 37 reintentos por minuto es
incompatible con una exposición de veinticuatro horas. Requiere soldar las uniones con alivio
de tensión.

**Alimentación del nodo sin verificar.** El reinicio observado apunta a una caída de tensión.
Requiere comprobar la fuente y el cableado de alimentación.

**Acoplamiento mecánico del sensor sin verificar.** El valor eficaz de vibración con la
máquina en marcha se mantiene en el orden de las centésimas y décimas de m/s², magnitud baja
para el activo. Requiere fijación rígida al chasis y contrastar la medida antes y después.

**Registro de dedicación inexistente.** Sin constancia de las horas invertidas no es posible
contrastar el avance con el reparto previsto.

## 6. Riesgos

**Nuevo — la comprobación de plausibilidad por módulo no detecta la caída de un solo eje.**
Materializado. Es una limitación de diseño de la verificación implementada, no un defecto de
programación, y queda documentada como tal. Se mitiga con una comprobación de continuidad
entre muestras consecutivas, que sí discrimina el artefacto.

**Nuevo — pérdida de datos no contabilizada.** Cuando la conexión con el *broker* no está
establecida, las ráfagas se descartan sin dejar registro. En el análisis resulta
indistinguible de la ausencia de medida. Se mitiga añadiendo un contador de ráfagas no
publicadas.

**Nuevo — reinicios del nodo sin diagnóstico.** Un reinicio interrumpe la continuidad
temporal de la señal, que es precisamente lo que analiza el modelo, y solo es detectable por
la vuelta a cero de los contadores acumulados. Se mitiga verificando la alimentación y
vigilando esos contadores durante la campaña.

**Nuevo — el canal acústico mide vibración estructural en lugar de sonido.** Convierte una
de las tres modalidades de medida en redundante con el acelerómetro. Se mitiga desacoplando
mecánicamente el micrófono.

**Nuevo — manipulación de ficheros con el servicio en ejecución.** Un proceso conserva el
acceso a un fichero eliminado, de modo que la escritura continúa sobre un destino invisible.
Se mitiga con el procedimiento de detener el servicio antes de intervenir en el directorio
de datos, y con la comprobación de tamaño ya incorporada.

**Actualizado — dependencia de la infraestructura de red ajena.** Queda **resuelto** con el
punto de acceso propio en la Pi: la dirección del *broker* pasa a ser fija.

**Actualizado — captura contra *broker* público sin autenticación.** Queda **resuelto**: el
nodo publica contra el *broker* local de la Pi en una red aislada. El riesgo residual se
traslada a la contraseña de la red inalámbrica, que es ahora lo único que impide a un tercero
publicar tramas falsas en los *topics*.

## 7. Próximos pasos

1. Comprobación de continuidad entre muestras consecutivas de la ráfaga, con su verificación
   numérica en el PC *(Fase 3)*.
2. Contador de ráfagas calculadas pero no publicadas *(Fase 3)*.
3. Soldar el conexionado del sensor con alivio de tensión y verificar la reducción de la tasa
   de reintentos *(Fase 3)*.
4. Verificar la alimentación del nodo y descartar caídas de tensión *(Fase 3)*.
5. Fijación rígida del sensor al chasis, contrastando el valor eficaz antes y después
   *(Fase 3)*.
6. Corregir la ventana de promediado del nivel acústico y los límites de las bandas, o
   desacoplar mecánicamente el micrófono *(Fase 3)*.
7. Actualizar `docs/DATA_SCHEMA.md`: rango del giróscopo, banda útil limitada por el filtro
   interno, contadores de salud y valor de reposo del acelerómetro *(Fase 3)*.
8. Campaña de referencia en estado nominal, con registro en `docs/EXPERIMENTOS.md`
   *(Fase 3)*.

## 8. Impacto en la memoria

Con lo avanzado en este periodo pueden redactarse ya:

- **`05-diseno.tex`**: la arquitectura del hub con punto de acceso propio, con su
  justificación —independencia de la infraestructura ajena, portabilidad y aislamiento de la
  red— y la contrapartida asumida. También el diseño de la persistencia del servicio frente a
  cortes de alimentación.
- **`04-metodologia.tex`**: el procedimiento de despliegue por fases y el criterio de
  intervención mínima sobre un equipo compartido, así como el método de verificación de la
  cadena de datos eslabón por eslabón.
- **`A2-anexo-software.tex`**: el aprovisionamiento del hub y la verificación automática.
- **`A1-anexo-hardware.tex`**: la caracterización del canal acústico y por qué su montaje
  actual lo hace redundante.

Un apartado que este periodo permite escribir con solidez es el de **tratamiento de la
integridad del dato**: la validación de la transacción, el reintento acotado, la
comprobación de plausibilidad y su limitación demostrada, y los contadores que hacen medible
la calidad de cada medida. Es material de diseño respaldado por medidas concretas, no por
suposiciones.

Siguen bloqueados por falta de datos experimentales todos los `% TODO` de
`06-resultados.tex` y los apartados de `07-conclusiones.tex` que dependen de métricas de
detección.

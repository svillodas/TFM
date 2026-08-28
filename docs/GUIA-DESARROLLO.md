# Guía de desarrollo del proyecto

**TFM — Sistema IoT Edge para mantenimiento predictivo**
Máster Universitario en Internet das Cousas (MUIoT) · UDC · Curso 2025/2026
Autor: Sergio Villodas Zapata · Tutor: Tiago Manuel Fernández Caramés (Dpto. Enxeñería de Computadores)
Carga: 6 ECTS (≈150 h) · Idioma de la memoria: castellano (términos técnicos en inglés)

## Objetivo académico
Desplazar la lógica de diagnóstico al **borde de la red (Edge)**: detectar de forma temprana
anomalías en sistemas electromecánicos (compresor de refrigeración como activo de prueba)
analizando vibración, temperatura y sonido con técnicas de Machine Learning, **sin depender
de un flujo masivo de datos hacia la nube**.

Implicación para el código: la nube/servidor es soporte de *entrenamiento y análisis*, no
requisito de operación. El inferencia final debe poder ejecutarse en el nodo.

## Arquitectura del Sistema
- **Nodo Sensor (Edge):** ESP32 en C++ (framework Arduino). Ver [device/device.ino](device/device.ino).
- **Servidor Local (Hub):** Raspberry Pi con broker MQTT (Mosquitto) + data logger en Python.
- **Protocolo:** MQTT sobre TCP/IP (Wi-Fi 2.4 GHz). **Tres canales**:
  `fridge/sensors` (9 campos, 1 Hz), `fridge/vibration` (45 campos, cada 30 s) y
  `fridge/status` (7 campos, el veredicto del detector embarcado).
- **Estructura de Datos:** payload JSON. Ver [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md) —
  incluye las reglas para consumir los picos espectrales, que no son evidentes.
- Detalle completo en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Estado actual
Cadena de adquisición cerrada y en captura. El trabajo activo está en la **Fase 4** (análisis).
- Nodo y hub operativos: la Pi genera su propia red Wi-Fi, Mosquitto y el logger arrancan solos.
- Firmware cerrado y verificado en placa: 3 picos espectrales por eje, filtro a 150 Hz en los
  estadísticos temporales, validación de la transacción I2C y comprobación de continuidad.
- **Se dispone de un fallo real** (segundo compresor, tono audible) además del activo nominal:
  **familia armónica 8×, 9× y 10×** del giro (398, 448, 497 Hz), cada uno dentro del 0,05 % del
  entero, confirmada por el canal acústico. Ver
  [informe](docs/informes/2026-08-26-fallo-real-noveno-armonico.md).
- **Pipeline de Fase 4 en pie** en [server/analisis/](server/analisis/) — ver su
  [README](server/analisis/README.md): carga con candados de firmware, limpieza, segmentación
  por episodios, características adimensionales y selección del modelo entre 7 candidatos con
  criterios declarados.
- **Campaña de referencia cerrada** (EXP-005): 19,04 h, 467 ráfagas útiles en **22 episodios**.
  Validación cruzada por episodios: la regla elegida da 0,5 % de falsos positivos de media y
  8,3 % en el peor arranque, frente al 25-34 % de los seis candidatos restantes.
- Pendiente: el despliegue en el ESP32 y el capítulo 7 de la memoria.

**Cuatro trampas del análisis, todas pisadas ya una vez:**
1. Un detector sobre `rms`/`peak`/`kurt` da el 99,4 % **sin usar ninguna característica que
   contenga la firma del fallo**: el nivel de los dos activos difiere en un factor 5,5, así que
   separa máquinas y no estados. Las características deben ser adimensionales.
2. `bad_frames` y los contadores `total_*` son **acumulados desde el arranque**. Exigirles cero
   como filtro de calidad descarta el 100 % de las ráfagas, sin aviso.
3. El firmware publica los tres picos **ordenados por amplitud**. Cualquier cociente `f2/fdom`
   es inestable: cuando el armónico supera a la fundamental por un 2 %, el mismo fenómeno pasa
   de 9,0 a 0,111. Hay que reordenar por frecuencia y descartar antes los picos por debajo del
   20 % de la amplitud mayor.
4. La unidad de observación independiente es el **episodio de marcha**, no la ráfaga. Las
   ráfagas salen cada 30 s y las de un mismo episodio están fuertemente correlacionadas. La
   validación buena es dejar fuera un episodio completo, y mirar el **peor** episodio.
5. **Los reintentos del bus I2C fabrican la firma del fallo sobre un activo sano.** Con más de
   10 reintentos, los picos significativos del nodo NOMINAL pasan de 1 a 3 y la fundamental cae
   de 49 Hz a 20 Hz. El filtro `retries <= 3` es parte del detector, no limpieza previa: el
   nodo debe **negarse a juzgar** una ráfaga con más reintentos.
6. El umbral marcha/parada **no puede ser absoluto**: el valle es 0,198 m/s² en el nodo A y
   0,060 en el nodo B. Se deriva de los datos. El primer valor que puse, 0,05, caía dentro del
   grupo de parado.
7. **Solo hay UN modo de fallo observado.** Elegir el modelo por sus falsos positivos contra ese
   único fallo es sobreajuste: la regla `n_picos` está ciega a 4 de 5 direcciones de fallo
   típicas. Ver `server/analisis/cobertura_modos.py` (datos sintéticos, no evidencia).
   Y una regla de una sola característica **no supera** a los modelos de ML: dándoles esa misma
   característica, todos convergen al mismo resultado.
9. **SESGO DE ESPIONAJE.** El análisis inicial elegía características ordenándolas por su
   separación *frente al conjunto con fallo*. Eso es usar el conjunto de evaluación para
   decidir. El protocolo limpio está en `server/analisis/protocolo.py`: partición cronológica
   por episodios, decisiones solo con el activo sano, evaluación una vez. **Elige un modelo
   distinto (LOF)**: 7,8 % de FP sobre episodios nunca vistos, 100 % de detección.
10. **La embarcabilidad no es una restricción real.** Los cinco modelos caben: de 8 B a 274 KB,
   y como máximo 15 150 operaciones (~0,1 ms) frente a una ráfaga cada 30 s. No usar ese
   criterio para descartar modelos. Auditoría en
   `server/analisis/cuadernos/auditoria-fase4.ipynb`.
8. Las características adimensionales son **ciegas a un fallo que solo cambie el nivel**, porque
   todo es cociente respecto a la fundamental. Se corrige normalizando por la mediana del propio
   activo (`rms_x_rel`), no suprimiendo la magnitud.

Progreso por fases en [docs/ROADMAP.md](docs/ROADMAP.md) — mantener actualizado ahí, no aquí.

## Directrices de Código (C++ ESP32)
1. **Prioridad industrial:** mantener intactas las rutinas de auto-recuperación
   (`checkAndRecoverI2C()`). El nodo debe sobrevivir a fallos físicos de cableado por
   la vibración del motor. Cualquier refactor debe preservar ese comportamiento.
2. **No bloqueante:** el bucle usa `millis()` con dos cadencias (canal lento a 1 Hz, ráfaga
   cada 30 s) y el DS18B20 en conversión asíncrona. No reintroducir `delay()` largos.
   **Única excepción deliberada:** el bucle de captura de la ráfaga bloquea ~1,02 s, porque
   el análisis frecuencial exige muestras equiespaciadas y cualquier trabajo intercalado
   introduciría jitter en el espectro. Está acotado y muy por debajo del keepalive MQTT.
3. **Gestión de memoria:** los payloads se generan con `snprintf` sobre buffer estático y
   las ráfagas usan buffers estáticos (~23 KB en total). No volver a `String` para construir
   JSON: el nodo publica de forma continua durante días. Si se añaden campos al payload de
   ráfaga, comprobar que sigue cabiendo en `payload[768]` y en `setBufferSize(1024)` de
   PubSubClient — un desbordamiento hace que `snprintf` truncue y publique JSON inválido en
   silencio.
4. **Pines críticos:** respetar el pinout de [README.md](README.md#-esquema-de-conexiones-pinout).
   La placa es una **DFRobot FireBeetle 2 ESP32-S3**, no un ESP32 clásico: en el S3 no
   existen los GPIO 22–25, la PSRAM octal reserva los GPIO 33–37 y los pines de *strapping*
   son GPIO0, GPIO3, GPIO45 y GPIO46. El bus I2C va por GPIO1/GPIO2 y se declara de forma
   explícita (`I2C_SDA`/`I2C_SCL`) para no depender del fichero de variante de la placa.
5. **Credenciales:** nunca escribir SSID/password/IPs reales en código versionado. Usar
   `device/secrets.h` (ignorado por git); la plantilla es `device/secrets.h.example`.
6. **Sin resets silenciosos:** no añadir `ESP.restart()` como remedio genérico. Un reinicio
   pierde el contexto temporal de la señal, que es justo lo que analiza el modelo.

## Directrices de Código (Python — Hub)
- Python 3.11+, `paho-mqtt` para MQTT, `pandas`/`numpy` para dataset, `scikit-learn` para
  el baseline de anomalías.
- El logger debe ser **tolerante a fallos**: un JSON malformado se descarta y se registra,
  nunca tumba el proceso. Los datos crudos son irrecuperables si se pierden.
- Un CSV por día, `server/data/YYYY-MM-DD.csv`, con `ts` ISO-8601 en primera columna.
- Configuración por variables de entorno / `.env`, no hardcodeada.

## Reglas de trabajo con este repositorio
- **Idioma del código:** los **identificadores van en inglés** (variables, funciones,
  constantes, campos del JSON, columnas del CSV, topics MQTT y nombres de fichero). Los
  **comentarios, la documentación, los mensajes por puerto serie y los commits van en
  castellano**, igual que la memoria. Es la convención habitual: el código se lee como
  código y la explicación del *por qué* físico se lee como prosa.
  Ejemplo: `bool captureVibrationBurst()` con el comentario en castellano encima.
- **Datos experimentales:** nunca borrar ni regenerar ficheros de `server/data/`. Son
  medidas de laboratorio no reproducibles.
- **Trazabilidad académica:** cada campaña de medida debe quedar registrada en
  [docs/EXPERIMENTOS.md](docs/EXPERIMENTOS.md) (activo, condición, fecha, fichero, notas).
  Sin esa anotación, el dataset no sirve como evidencia en la memoria.
- No introducir dependencias cloud (AWS/Azure/GCP): contradicen la tesis del TFM.
- Antes de tocar el firmware, comprobar si el cambio afecta al pinout o al formato del
  payload; si lo hace, actualizar README y `docs/DATA_SCHEMA.md` en el mismo cambio.

## Procesado de señal
La extracción de características está en [device/signal_processing.h](device/signal_processing.h), **sin dependencias de
Arduino a propósito**: permite compilarla y verificarla en el PC antes de subirla a la placa.

```bash
g++ -std=c++11 -O2 -o /tmp/test_signal device/test/test_signal_processing.cpp && /tmp/test_signal
```

**Regla: cualquier cambio en `signal_processing.h` exige ejecutar ese test y que pase.** Depurar
matemáticas a través del puerto serie es una pérdida de tiempo evitable. Si se añade una
característica nueva, se añade también su prueba con un valor esperado analítico (por
ejemplo: kurtosis de un seno = 1,5; RMS de un seno = A/√2).

Frecuencias de muestreo y su justificación física en
[docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md). Resumen: el canal lento a 1 Hz solo sirve para
tendencias; el contenido frecuencial vive en el canal de ráfaga a 1 kHz.

## Documentación académica (memoria del TFM)
La entrega evaluable es la **memoria**, no el código. El código es el medio; la memoria es
el producto. Trabajar en el repositorio sin dejar rastro documentado es trabajo perdido.

- **Normativa operativa:** [docs/normativa/GUIA_MEMORIA.md](docs/normativa/GUIA_MEMORIA.md).
  Es el destilado de la guía oficial: formato, estilo, estructura, bibliografía. **Leerlo
  antes de redactar cualquier cosa**; los PDF oficiales están en `docs/normativa/` para el
  detalle literal.
- **Documento:** [memoria_TFM/](memoria_TFM/). Maestro `memoria_TFM.tex`, contenido en
  `capitulos/`, figuras en `figuras/`, bibliografía en `referencias.bib`.
- **Compilar:** `bash memoria_TFM/compilar.sh` (requiere XeLaTeX/tectonic: la plantilla usa
  `fontspec`, `pdflatex` no sirve).
- **Ficheros intocables:** `tfm-muiot.sty`, `IEEEtran.bst`, `logo_*.pdf`, `portada_TFM.pdf`.
  Son plantilla oficial; copia intacta en `memoria_TFM/plantilla/`. Única adaptación local
  documentada: fuente activa Times New Roman (XeTeX en macOS no resuelve *TeX Gyre Termes*
  por nombre; Times New Roman es la primera fuente que recomienda la guía).

### Reglas de redacción de obligado cumplimiento
1. **Tercera persona impersonal.** "Se implementó", nunca "he implementado". Lo exige la guía.
2. **Máximo dos niveles jerárquicos:** `\chapter` + `\section`. **Nunca `\subsection`.**
3. **Unidades:** símbolo sin punto y con espacio (`10 m`, `2,4 GHz`, `750 ms`), sin decimales
   excesivos. `siunitx` no está cargado.
4. **Cursiva** solo para énfasis, extranjerismos no adoptados (*edge*, *broker*) y nombres
   propios en otras lenguas.
5. **Figuras y tablas:** `\caption` + `\label` + `\ref` que las cite en el texto. Títulos
   de tabla arriba.
6. **Extensión:** 25–50 páginas sin contar anexos.
7. **Sin resultados inventados y sin citas fantasma.** Toda cifra del capítulo de resultados
   procede de una campaña registrada en [docs/EXPERIMENTOS.md](docs/EXPERIMENTOS.md); toda
   `\cite` tiene entrada real en `referencias.bib`. Si el dato no existe, se deja el
   `% TODO` y se dice. Es un documento académico evaluable: una cifra inventada es una falta
   grave, no un detalle de estilo.

### Flujo de trabajo documental

**Flujo esperado:** avance técnico → `/experimento` si hubo captura → `/informe-avance` al
cerrar un hito → `/memoria` para volcar lo consolidado al capítulo correspondiente. Los
informes se redactan para ser reutilizables en el capítulo de metodología.

## Comandos de entorno
```bash
# Firmware (arduino-cli) — DFRobot FireBeetle 2 ESP32-S3
FQBN='esp32:esp32:dfrobot_firebeetle2_esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB'
arduino-cli board list                       # el puerto USB-CDC cambia entre reinicios
arduino-cli compile --fqbn "$FQBN" device/
arduino-cli upload  --fqbn "$FQBN" -p /dev/cu.usbmodem101 device/
arduino-cli monitor -p /dev/cu.usbmodem101 -c baudrate=115200

# Hub (desde la raíz del repo)
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
python server/mqtt_logger.py

# Verificación del procesado de señal (en el PC, sin placa)
g++ -std=c++11 -O2 -o /tmp/test_signal device/test/test_signal_processing.cpp && /tmp/test_signal

# Fase 4 — análisis (solo en el portátil, NO en la Pi)
pip install -r server/requirements-analisis.txt
.venv/bin/python server/analisis/pipeline.py           # qué datos hay y qué se descarta
.venv/bin/python server/analisis/comparar_modelos.py   # 7 modelos + validación por episodios
.venv/bin/python server/analisis/cobertura_modos.py    # puntos ciegos (datos SINTÉTICOS)
.venv/bin/python server/analisis/protocolo.py          # selección SIN sesgo de espionaje
.venv/bin/python server/analisis/baseline_anomalias.py # el detector y sus limitaciones
.venv/bin/jupyter notebook server/analisis/cuadernos/auditoria-fase4.ipynb   # auditoría

# Diagnóstico MQTT (los tres canales)
mosquitto_sub -h 10.42.0.1 -t 'fridge/#' -v

# Detector embarcado: verificar en el PC antes de flashear
g++ -std=c++11 -O2 -o /tmp/td device/test/test_detector.cpp    && /tmp/td
g++ -std=c++11 -O2 -o /tmp/ti device/test/test_integracion.cpp && /tmp/ti
.venv/bin/python server/analisis/exportar_modelo.py        # -> device/modelo_referencia.h
.venv/bin/python server/analisis/exportar_casos_prueba.py  # -> device/test/casos_modelo.h

# Sincronizar el concentrador. El USUARIO ES OBLIGATORIO: 10.42.0.1 usa iiot-c
# y los 10.45.127.x usan admin. Si pide contraseña, el usuario es el equivocado.
./server/sync-pi.sh 10.42.0.1 iiot-c

# Memoria del TFM
bash memoria_TFM/compilar.sh
grep -rn '% TODO' memoria_TFM/capitulos/     # qué queda por redactar
```

## Próximos hitos (backlog inmediato)
1. **Portar la regla al ESP32** (`n_picos > 1`, más histéresis y el guardián de reintentos) y
   publicar el veredicto en `fridge/status`. Es la tesis del TFM y está sin demostrar en
   hardware: ahora el detector corre en Python en el portátil.
2. Dimensionar toda captura nominal sobre **24 ráfagas útiles/h** (no sobre la cadencia de
   publicación): solo el 27 % de las ráfagas del nodo A pillan el compresor en marcha.
3. Segmentar la campaña nominal por estado (marcha / parada) antes de comparar CV con EXP-003.
4. Fallo inducido **sobre el mismo activo** — es lo que EXP-003 no puede dar: sin comparación
   dentro de una misma máquina no se separa el fallo de la variabilidad entre ejemplares.
5. Portar la regla `f2_x/fdom_x` al ESP32. Dos umbrales sobre una magnitud adimensional dan la
   misma discriminación que el modelo completo, sin entorno de inferencia.
6. Umbral de continuidad **relativo a la continua de cada eje**: con el umbral absoluto de
   6 m/s², los cortes del eje Z del nodo A no se detectan (la gravedad reposa sobre X y la
   continua de Z es de solo 1,66 m/s²). No reflashear con una campaña en curso.

## Estructura del repositorio
```
device/                Firmware ESP32 (C++/Arduino)
server/                Hub: logger MQTT→CSV, aprovisionamiento de la Pi
  ├── data/            Datasets, un directorio por nodo y firmware. Ver data/README.md
  └── analisis/        Fase 4: pipeline de detección. Ver analisis/README.md
      └── cuadernos/   Auditoría de las decisiones de ML (los scripts son la fuente de verdad)
docs/                  Documentación de ingeniería
  ├── normativa/       Normativa del TFM + PDF oficiales (solicitud y guía)
  └── informes/        Informes de avance generados
memoria_TFM/           Memoria LaTeX (plantilla oficial MUIoT)
  ├── capitulos/       Contenido por capítulo (estructura A–I obligatoria)
  ├── figuras/         Figuras y gráficas de la memoria
  └── plantilla/       Copia intacta de la plantilla oficial
hardware/              Notas de montaje, fotos y esquemas del banco de pruebas
```

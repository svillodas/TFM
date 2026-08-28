# Datos capturados

Un directorio por **nodo de captura**, y dentro uno por **versión de firmware**, porque
ninguna de las dos cosas se puede mezclar:

- **Por nodo:** la firma de vibración es específica de cada máquina y de cada montaje. Un
  modelo ajustado sobre un activo marca todo lo de otro como anómalo, y no hay forma de
  distinguir si señala un fallo o simplemente que es otra máquina.
- **Por firmware:** el de 31 columnas publica `rms`, `peak` y `kurt` sin filtrar y un solo
  pico espectral. El de 46 los filtra a 150 Hz y publica tres picos. Son **definiciones
  distintas de la misma característica**: compararlas entre sí no significa nada.

## Identificación de los nodos

Se distinguen por el módulo del vector de aceleración en reposo, que es la desviación de cero
propia de cada MPU-6050 y no cambia al remontar el sensor:

| Directorio | Activo | \|a\| | Notas |
| :--- | :--- | ---: | :--- |
| `nodo-a-nevera-buena/` | Compresor de referencia | 10,33 | **Estado nominal.** El del baseline |
| `nodo-b-otro-compresor/` | Segundo compresor | 11,79 | **Fallo real confirmado.** Armónicos 8×, 9× y 10× del giro (398, 448, 497 Hz) |

## Los dos activos no son intercambiables

El nodo B tiene un **fallo real, no inducido**, con verdad de referencia independiente de la
instrumentación: emite un tono audible sostenido que el operador percibe. El nodo A está en
estado nominal. Eso convierte el par en lo que el proyecto necesita para la Fase 4: un
conjunto de entrenamiento y un caso de evaluación con etiqueta fiable.

La firma del fallo está en `f2_*`, `f3_*`, `aud_b1` y `aud_rms`. **No está en `rms`, `peak`
ni `kurt`**, porque el filtro paso bajo a 150 Hz la elimina de los estadísticos temporales.

> **Los tres picos vienen ordenados por amplitud, no por frecuencia.** Cualquier cociente del
> tipo `f2_x / fdom_x` es inestable: en el activo con fallo el armónico supera a la fundamental
> por un 2 % en 60 de 676 ráfagas y le quita la posición de dominante, con lo que el mismo
> fenómeno da 9,0 y 0,111. Hay que reordenar por frecuencia y descartar antes los picos con
> amplitud inferior al 20 % de la mayor. Lo hace
> [`server/analisis/pipeline.py`](../analisis/pipeline.py); ver su
> [README](../analisis/README.md).
Un detector ajustado solo sobre esas tres características no encuentra este fallo. Detalle en
[el informe](../../docs/informes/2026-08-26-fallo-real-noveno-armonico.md).

La limitación que debe declararse en toda métrica obtenida sobre este par: son **máquinas
distintas**, de modo que el contraste no separa el efecto del fallo del de la variabilidad
entre ejemplares.

## Contenido

| Serie | Columnas | Filas | Periodo |
| :--- | ---: | ---: | :--- |
| `nodo-a-nevera-buena/fw-46col/2026-08-26-vibration.csv` | 46 | 195 | 26 · 15:13 → 16:55 |
| `nodo-a-nevera-buena/fw-46col/2026-08-26.csv` | 10 | 5 934 | idem |
| `nodo-a-nevera-buena/fw-31col/2026-08-25-vibration.csv` | 31 | 658 | 25 · 17:48 → 23:59 |
| `nodo-a-nevera-buena/fw-31col/2026-08-25.csv` | 10 | 21 607 | idem |
| `nodo-a-nevera-buena/fw-31col/2026-08-26-vibration.csv` | 31 | 1 456 | 26 · 00:00 → 14:22 |
| `nodo-a-nevera-buena/fw-31col/2026-08-26.csv` | 10 | 50 212 | idem |
| `nodo-b-otro-compresor/fw-46col/2026-08-26-vibration.csv` | 46 | 245 | 26 · 11:44 → 13:53 |
| `nodo-b-otro-compresor/fw-46col/2026-08-26.csv` | 10 | 7 515 | 26 · 11:44 → 13:54 |
| `nodo-b-otro-compresor/fw-31col/2026-08-25-vibration.csv` | 31 | 92 | 25 · 20:14 → 21:02 |
| `nodo-b-otro-compresor/fw-31col/2026-08-25.csv` | 10 | 3 428 | 25 · 20:14 → 21:13 |
| `nodo-b-otro-compresor/fw-33col/2026-08-25-vibration.csv` | 33 | 22 | 25 · 21:02 → 21:13 |

## Clasificación de las series

No todo lo que hay se puede usar para lo mismo, y la distinción no se aprecia mirando los
ficheros. [`manifiesto.json`](manifiesto.json) la recoge en formato legible por el pipeline,
con cuatro usos:

| Uso | Significado |
| :--- | :--- |
| `entrenamiento` | Apta para ajustar el modelo de estado nominal |
| `fallo` | Activo con fallo confirmado por verdad externa. Conjunto de evaluación, nunca de entrenamiento |
| `contraste` | Activo o montaje distinto. Utilizable solo como comparación, nunca mezclada |
| `evidencia` | No apta para análisis. Se conserva porque respalda una afirmación de la memoria |
| `descartada` | Sin uso previsto. Conservada por la regla de no eliminar medidas |

La clasificación es **por canal y no por directorio**, porque no coinciden. El caso de
`nodo-a-nevera-buena/fw-31col` lo ilustra: su canal lento es dato de entrenamiento —el canal
lento no depende de la versión del firmware, de modo que la caracterización térmica y de
ciclos sobre esas 20,6 h es válida— mientras su canal de ráfaga solo sirve como evidencia,
porque publica los estadísticos sin filtrar y un único pico espectral.

## Dónde escribe el registrador

El registrador no conoce esta estructura: vuelca en el directorio que le indique `DATA_DIR`.
Para que cada nodo escriba en su sitio, en el `server/.env` **del concentrador**:

```
DATA_DIR=/home/<usuario>/TFM/server/data/nodo-a-nevera-buena/fw-46col
```

Si se deja el valor por omisión, el dato nuevo aparece en la raíz de `server/data/` y hay que
archivarlo a mano. Conviene ajustarlo **antes** de lanzar una captura larga.

## Sincronización con el concentrador

Para enviar código al concentrador, usar `server/sync-pi.sh`, que fija las exclusiones y las
barras finales. Escribir el `rsync` a mano ha producido ya tres incidentes: directorios
anidados (`data/data/data`), sobrescritura de `server/.env` —que dejó el registrador suscrito
al intermediario público— y **eliminación de esta estructura completa** al sincronizar en
sentido contrario.

Para **traer** datos del concentrador, nunca con `--delete` sobre este directorio: el
concentrador solo tiene la captura en curso, de modo que un borrado espejo se lleva todo lo
demás.

## Incidencias resueltas en los datos

**Consolidación de fragmentos.** Los seis fragmentos del canal lento del nodo B, que un
defecto del procedimiento de actualización había separado, se unieron en una serie ordenada
por marca de tiempo. Igual con los del nodo A del día 25. La deduplicación usa `ts` como
clave, de modo que un solapamiento no produce filas repetidas.

**Bytes nulos.** Se retiraron 2519 bytes de las series del nodo B. Son huecos del sistema de
ficheros por parada sucia del concentrador: los bloques quedaron reservados pero los datos
nunca se escribieron. Las filas a ambos lados estaban íntegras, de modo que no se perdió
ninguna medida.

**Desalineamiento de columnas.** El fichero de ráfaga del nodo B del día 25 contenía 92 filas
de 31 campos y 22 de 33: el registrador se actualizó a mitad de la jornada añadiendo
`cont_rejects` y `total_cont_rejects`, y como el fichero ya existía la cabecera no se
reescribió. Las 22 filas posteriores quedaron **desplazadas dos posiciones**.

No es un defecto detectable a simple vista: leídas con la cabecera equivocada devuelven
`rms_x` = 7 y `aud_b3` = 0,986, valores que un cargador aceptaría sin protestar aunque son
físicamente imposibles. Con la cabecera correcta dan 0,0951 y 0,0005. Se separaron en
`fw-33col/` sin perder ninguna fila.

El registrador escribe ya la cabecera también cuando el fichero existe pero está vacío, y
`provision-pi.sh actualizar` archiva los ficheros cuya cabecera no corresponda al código, de
modo que este caso no debería repetirse.

## Advertencias para el análisis

- **Los bytes nulos van a volver a aparecer.** El registrador vuelca al sistema operativo con
  `flush()`, no al disco con `fsync()`, así que una parada sucia deja ceros. El cargador debe
  retirarlos al leer, no descubrirlos a mitad del entrenamiento.
- **Filtrar los centinelas antes de cualquier estadístico**: `tempExt = -127` y bloques del
  acelerómetro a cero. Un solo `-127` arrastra la media térmica de la jornada.
- **Los contadores de salud son criterio de filtrado.** Se comprobó que la ráfaga con más
  reintentos de una ventana era también la de mayor kurtosis, de modo que `retries` y
  `cont_rejects` califican la calidad de cada medida de forma objetiva. La fracción descartada
  y su umbral deben declararse: forman parte del resultado.
- **Un retroceso en un contador acumulado indica reinicio del nodo**, no un error de lectura.
- **`rms` y `kurt` describen la banda 0–150 Hz** en el firmware de 46 columnas, mientras
  `fdom`, `adom` y los picos 2 y 3 describen todo el espectro. No son magnitudes de la misma
  señal.

## Regla

Los ficheros de este directorio son **medidas de laboratorio no reproducibles**. No se borran
ni se regeneran. Toda campaña destinada a la memoria debe estar anotada en
[docs/EXPERIMENTOS.md](../../docs/EXPERIMENTOS.md); sin esa anotación, un CSV es un fichero de
números sin condiciones experimentales asociadas.

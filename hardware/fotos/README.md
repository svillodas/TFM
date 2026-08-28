# Fotografías del banco de pruebas

Archivo fotográfico del montaje. De aquí salen las figuras del capítulo de diseño y del
anexo de hardware de la memoria.

## Por qué una foto sin contexto no sirve

La firma de vibración depende del **punto y la rigidez de la fijación**: un sensor acoplado
de otra forma mide otra cosa. Durante la puesta a punto el sensor se remontó varias veces y
la componente de gravedad pasó del eje Z al X, lo que significa que **cada remontaje invalida
el baseline anterior**.

Consecuencia práctica: una foto del montaje es la única evidencia de en qué configuración
física se tomó una campaña. Sin esa trazabilidad, ni la foto ni el conjunto de datos sirven
como prueba en la memoria.

## Nomenclatura

```
YYYY-MM-DD-<asunto>.jpg
```

Fecha primero para que orden alfabético y cronológico coincidan. Ejemplos:

```
2026-08-25-fijacion-acelerometro-detalle.jpg
2026-08-25-compresor-conjunto.jpg
2026-08-26-nodo-cableado-soldado.jpg
```

## Qué anotar de cada foto

Añadir una línea en la tabla de abajo. Si la foto documenta el montaje con el que se capturó
una campaña, citarla también en la entrada correspondiente de
[docs/EXPERIMENTOS.md](../../docs/EXPERIMENTOS.md).

| Fichero | Fecha | Qué muestra | Campaña asociada |
| :--- | :--- | :--- | :--- |
| `nevera_vieja.jpeg` | 2026-08-25 | Compresor `TW146-US-416` del activo antiguo, con el módulo del acelerómetro apoyado sobre la cúpula y el nodo sobre protoboard. Documenta el montaje de la fase de depuración | — (depuración) |
| `nevera baseline/…18.16.55.jpeg` | 2026-08-25 | Conjunto del banco: activo, nodo y concentrador Raspberry Pi con cable de gestión | Baseline (pendiente) |
| `nevera baseline/…18.16.56.jpeg` | 2026-08-25 | Compresor `PW58B` del activo de referencia, con el acelerómetro adherido al lateral de la cúpula. Se aprecia el cableado I2C sobre protoboard discurriendo en paralelo al cableado de red del compresor | Baseline (pendiente) |
| `nevera baseline/…18.16.56 (1).jpeg` | 2026-08-25 | Vista complementaria del montaje | Baseline (pendiente) |
| `nevera baseline/…18.16.56 (2).jpeg` | 2026-08-25 | Vista complementaria del montaje | Baseline (pendiente) |

Las tres primeras se han incorporado a la memoria como
`memoria_TFM/figuras/banco-compresor-antiguo.jpg`, `banco-conjunto-hub.jpg` y
`banco-fijacion-sensor.jpg` respectivamente.

## Puntos de medida probados

Registro de las posiciones ensayadas y su resultado. La guía visual anotada sobre la
fotografía del banco está en el artefacto publicado el 2026-08-25.

| Posición | Fecha | `rms_z` sin filtrar | Fundamental de 49 Hz | Veredicto |
| :--- | :--- | ---: | :--- | :--- |
| Cúpula del compresor | 2026-08-25 | 0,047 | 4 de 52 ráfagas | ❌ Descartada. El fabricante aísla la cúpula del motor con muelles internos, de modo que se medía por el lado tranquilo de la suspensión |
| Anclaje al chasis (posición 1) | 2026-08-26 | — | — | Evaluada, no adoptada |
| **Tubo de descarga (posición 2)** | 2026-08-26 | 0,35 – 0,69 | **6 de 7 ráfagas** (tercer pico) | ✅ **Adoptada.** El nivel subió entre 9 y 20 veces según el eje. Unido rígidamente al cuerpo de la bomba, transporta la pulsación sin atravesar la suspensión interna del compresor |

De la posición adoptada, dos observaciones que condicionan el análisis:

- El 95 % de esa energía está en componentes de alta frecuencia (398-497 Hz), no en la banda
  que describen los estadísticos filtrados: el valor eficaz en 0-150 Hz es de 0,062 m/s² y no
  de 0,35, de modo que la ganancia sobre esos estadísticos es de ~1,6 veces y no de 15.
  **Se interpretó como una resonancia del pegado adhesivo y era falso**: son los armónicos 8×,
  9× y 10× del giro, es decir la firma de un fallo real. Lo que el cambio de punto de medida
  hizo accesible es justamente la banda donde estaba el fallo.
- La fundamental del compresor aparece como **tercer** pico espectral, por detrás de dos de
  esos armónicos. Es la razón por la que el firmware publica tres picos y no solo el dominante:
  con uno, esta información se perdía en el nodo y no era recuperable en el hub.

Detalle completo en [EXP-002](../../docs/EXPERIMENTOS.md).

**Pendiente:** fotografía de detalle de la posición adoptada. Al añadirla, nombrarla
`2026-08-26-fijacion-adoptada.jpg` y anotarla en la tabla de arriba.

## Fotos que hacen falta para la memoria

Del montaje actual:

- [ ] **Conjunto del activo**: la nevera completa, para situar al lector
- [ ] **Punto de fijación del acelerómetro, en detalle** — la más importante: es la que
      justifica si el acoplamiento es rígido y sostiene la validez de todo el dataset
- [ ] **Nodo completo**: ESP32 con los tres sensores, identificables
- [ ] **Cableado del bus I2C**, antes y después de soldar (documenta la incidencia de los
      37 reintentos/minuto)
- [ ] **Hub**: la Raspberry Pi del punto de acceso
- [ ] **Montaje en funcionamiento**: vista general de todo el sistema operando

De la Fase 5, una por cada fallo inducido:

- [ ] Desequilibrio de masa
- [ ] Aflojamiento de anclaje
- [ ] Obstrucción de ventilación
- [ ] Sobrecarga térmica

Estas cuatro son imprescindibles: sin fotografía del fallo provocado, la etiqueta del
conjunto de datos no queda respaldada por nada.

## Convenciones técnicas

- **Fondo y enfoque:** el detalle de la fijación requiere primer plano y luz suficiente. Una
  foto borrosa del punto de acoplamiento no demuestra nada.
- **Escala:** incluir una referencia de tamaño reconocible (una moneda, un calibre) en las
  fotos de detalle.
- **Resolución:** redimensionar a un ancho máximo de unos 2000 px antes de llevarlas a
  `memoria_TFM/figuras/`. XeLaTeX con imágenes de móvil sin procesar genera un PDF
  innecesariamente grande y ralentiza la compilación.

## Relación con `memoria_TFM/figuras/`

Esta carpeta es el **archivo de trabajo**: todas las fotos, incluidas las descartadas y las
que documentan montajes ya sustituidos.

[`memoria_TFM/figuras/`](../../memoria_TFM/figuras/) contiene solo las que se incluyen en el
documento, ya recortadas y redimensionadas. Se copian, no se mueven: el archivo conserva el
original.

Toda figura de la memoria necesita `\caption`, `\label` y una `\ref` que la cite en el texto,
según [docs/normativa/GUIA_MEMORIA.md](../../docs/normativa/GUIA_MEMORIA.md).

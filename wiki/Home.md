# Sistema IoT Edge para mantenimiento predictivo

Nodo ESP32-S3 que mide vibración, temperatura y sonido de un compresor de refrigeración,
extrae las características **en el propio nodo** y emite un veredicto de salud del activo.

La tesis del trabajo es que el diagnóstico ocurre en el borde: la nube y el concentrador son
soporte de entrenamiento y almacenamiento, **no requisito de operación**.

TFM del Máster Universitario en Internet das Cousas · UDC · curso 2025/2026.

## Páginas

| Página | Contenido |
| :--- | :--- |
| [Arquitectura](Arquitectura) | Diagramas del sistema, los tres canales, presupuesto de cómputo |
| [Conexionado](Conexionado) | Pinout, lista de conexiones y restricciones de la placa |
| [Pipeline de análisis](Pipeline-de-analisis) | De los CSV al modelo embarcado, y el por qué de cada etapa |
| [Trampas conocidas](Trampas-conocidas) | **Los nueve defectos que ya se han cometido.** Leer antes de tocar el análisis |
| [Puesta en marcha](Puesta-en-marcha) | Procedimiento completo con comandos literales |

## Resultados

**Un fallo real detectado, con verdad de referencia externa.** Un segundo compresor presentaba
un fallo no inducido, perceptible como un tono audible. El sistema identificó una familia de
armónicos en **8×, 9× y 10×** la frecuencia de giro (398, 448 y 497 Hz), cada uno dentro del
0,05 % del entero.

Una resonancia estructural no produce tres componentes simultáneas en múltiplos enteros exactos
de una frecuencia que además varía. Confirmado de forma independiente por el canal acústico, que
no comparte sensor ni cadena de acondicionamiento: el reparto de energía está **invertido** entre
los dos activos.

**Detector validado por validación cruzada por episodios:**

| Magnitud | Valor |
| :--- | ---: |
| Falsos positivos sobre condiciones no vistas | 7,8 % |
| Detección sobre el activo con fallo | 100 % |
| Avisos falsos con histéresis de 3 ráfagas | **0** de 505 |

**Inferencia en el nodo:** 1,3 ms, el **0,004 %** del ciclo, con veredicto idéntico al de la
implementación de referencia en 1161 ráfagas contrastadas.

## Lo que la evidencia no permite afirmar

Se consigna aquí porque es la limitación de mayor peso del trabajo.

Los dos activos medidos son **máquinas distintas**, de modo que el contraste no separa el efecto
del fallo del de la variabilidad entre ejemplares. Las características adimensionales acotan ese
sesgo pero no lo eliminan. Solo un fallo inducido sobre el activo de referencia lo elimina, y
está prerregistrado pero sin ejecutar.

Hay además **un solo modo de fallo real observado**. El análisis de cobertura frente a otros
modos emplea perturbaciones sintéticas y no constituye evidencia experimental.

## Sin TinyML, y por un motivo de fondo

Los entornos de ejecución de modelos reducidos para microcontroladores operan sobre **redes
neuronales**. Ninguno de los modelos candidatos lo es: no es que resulten excesivos, es que **no
pueden ejecutarlos**.

Y una red neuronal no era alternativa: con 505 observaciones nominales de 24 episodios,
cualquier arquitectura con capacidad apreciable se sobreajustaría. La familia de modelos la
determinó el tamaño de muestra, no la plataforma.

La inferencia se programa directamente: ~15 líneas de C++ para la envolvente, ~60 para el modelo
seleccionado.

## Estructura del repositorio

```
device/     Firmware C++/Arduino. El procesado de señal y el detector se
            compilan y verifican en el PC, sin placa
server/     Concentrador y, en analisis/, el pipeline de detección
docs/       Documentación de ingeniería, campañas de medida e informes
memoria_TFM/  Memoria académica en LaTeX
hardware/   Notas de montaje y fotografías del banco de pruebas
```

#!/usr/bin/env python3
"""
Analisis de sensibilidad: puntos ciegos del detector frente a modos de fallo
que NO se han observado.

ADVERTENCIA. Los datos que genera este script son SINTETICOS. Se obtienen
perturbando el conjunto nominal en las direcciones que la literatura asocia a
modos de fallo caracteristicos. NO SON EVIDENCIA EXPERIMENTAL y no deben
citarse como rendimiento del detector: localizan puntos ciegos, que es una
pregunta distinta de con que acierto detecta.

El motivo de que exista: la evidencia real corresponde a UN solo modo de fallo.
Elegir el modelo por su tasa de falsos positivos contra ese unico modo es una
forma de sobreajuste, y este script lo hace visible.

    .venv/bin/python server/analisis/cobertura_modos.py
"""
import numpy as np

import pipeline as pl
from comparar_modelos import catalogo, evaluar


# Direcciones de fallo. Cada una perturba el conjunto nominal segun la
# manifestacion fisica esperable del modo, sobre las caracteristicas que el
# nodo publica.
def perturbar(d, modo):
    g = d.copy()
    if modo == "desequilibrio":
        # Masa desequilibrada: sube la amplitud A LA FRECUENCIA DE GIRO sin
        # anadir componentes nuevas. Es el modo al que las caracteristicas
        # puramente adimensionales son ciegas por construccion.
        g["rms_x_rel"] *= 1.8
        g["adom_x_rel"] *= 2.0
        g["q2"] *= 0.5
        g["q3"] *= 0.5
    elif modo == "holgura":
        # Holgura mecanica: aparecen armonicos de orden bajo del giro.
        g["n_picos"] = 3.0
        g["r2"] = 2.0
        g["r3"] = 3.0
        g["q2"] = 0.35
        g["q3"] = 0.25
    elif modo == "rodamiento":
        # Deterioro incipiente de rodamiento: impulsos repetitivos. Sube la
        # kurtosis y el factor de cresta, y desplaza energia acustica a banda
        # alta.
        g["kurt_x"] *= 2.2
        g["crest"] *= 1.6
        g["aud_b2"] = 0.25
        g["aud_b3"] = 0.15
        g["aud_b0"] *= 0.6
    elif modo == "obstruccion":
        # Obstruccion de la ventilacion: la vibracion NO cambia en absoluto. El
        # condensador no evacua calor, de modo que el diferencial termico sube y
        # el motor no llega a enfriarse entre marchas. Es el modo que justifica
        # que el sistema sea multimodal: ninguna caracteristica de vibracion ni
        # de sonido lo registra.
        g["dif_rel"] *= 1.5
        g["grad_motor"] += 0.8
    elif modo == "roce":
        # Roce o friccion: banda ancha de alta frecuencia, sin tonos.
        g["aud_b2"] = 0.40
        g["aud_b3"] = 0.30
        g["aud_b0"] *= 0.4
        g["crest"] *= 1.3
    else:
        raise ValueError(modo)
    return g


MODOS = ["holgura", "rodamiento", "roce", "desequilibrio", "obstruccion"]


def main():
    nom, tn = pl.preparar("entrenamiento", verboso=False)
    fal, _ = pl.preparar("fallo", verboso=False)
    cols = pl.COLUMNAS
    Xn = nom[cols].values

    print("=" * 78)
    print("ANALISIS DE SENSIBILIDAD — DATOS SINTETICOS, NO EVIDENCIA")
    print("=" * 78)
    print(f"Ajustado sobre {len(nom)} rafagas nominales reales en {tn['episodios']} episodios.")
    print("Las columnas de modos son perturbaciones sinteticas del propio conjunto")
    print("nominal. La ultima columna si es real: el activo con fallo confirmado.\n")
    print(f"{'modelo':<20}" + "".join(f"{m[:13]:>15}" for m in MODOS) + f"{'FALLO REAL':>13}")
    for nombre, modelo in catalogo().items():
        fila = [evaluar(modelo, Xn, Xn[:0], perturbar(nom, m)[cols].values, cols)[1]
                for m in MODOS]
        real = evaluar(modelo, Xn, Xn[:0], fal[cols].values, cols)[1]
        print(f"{nombre:<20}" + "".join(f"{100*x:13.0f} %" for x in fila)
              + f"{100*real:11.0f} %")

    print("""
LECTURA. Un 0 % es un punto ciego: el modelo no reaccionaria a ese modo de
fallo. La regla sobre el numero de picos detecta lo que ANADE componentes
espectrales y no lo que altera la amplitud o la impulsividad, de modo que su
ventaja en falsos positivos —medida contra el unico modo de fallo disponible—
es en parte sobreajuste a ese modo.

La columna 'obstruccion' es la que justifica el planteamiento multimodal: ese
modo NO altera la vibracion ni el sonido en absoluto, y solo se detecta porque
el canal termico esta unido al de rafaga. Sin esa union, todos los modelos
darian 0 % en esa columna.""")


if __name__ == "__main__":
    main()

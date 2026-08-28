#!/usr/bin/env python3
"""
Exporta los vectores de caracteristicas REALES y el veredicto que produce
scikit-learn sobre cada uno, para que el detector en C++ pueda verificarse en
el PC contra la referencia de Python antes de subirlo a la placa.

    .venv/bin/python server/analisis/exportar_casos_prueba.py

Escribe device/test/casos_modelo.h. Es un fichero de PRUEBA: no lo incluye el
firmware, solo test_detector.cpp.

Por que esto y no comprobarlo en la placa: una discrepancia entre el C++ y el
Python sobre datos reales es un defecto de la implementacion, y localizarlo por
el puerto serie cuesta un orden de magnitud mas que en el PC. Cuando este arnes
pasa, lo unico que queda por verificar en hardware es el tiempo de ejecucion y
la ocupacion de memoria.

Se exportan TODAS las rafagas de los dos conjuntos y no una muestra: una
discrepancia en 1 de 1161 importa, y ocultarla muestreando seria el mismo error
que este proyecto ya ha cometido en otro sitio.
"""
from pathlib import Path

import numpy as np
from sklearn.covariance import EllipticEnvelope
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

import pipeline as pl
from comparar_modelos import ALFA
from exportar_modelo import K_VECINOS

SALIDA = Path(__file__).resolve().parents[2] / "device" / "test" / "casos_modelo.h"


def main():
    nom, tn = pl.preparar("entrenamiento", verboso=False)
    fal, tf = pl.preparar("fallo", verboso=False)
    cols = pl.COLUMNAS

    esc = StandardScaler().fit(nom[cols].values)
    Xn = esc.transform(nom[cols].values)
    Xf = esc.transform(fal[cols].values)

    env = EllipticEnvelope(support_fraction=0.9, contamination=ALFA,
                           random_state=0).fit(Xn)
    lof = LocalOutlierFactor(n_neighbors=K_VECINOS, novelty=True).fit(Xn)

    casos = []
    for etiqueta, d, Z in (("nominal", nom, Xn), ("fallo", fal, Xf)):
        s_env = env.score_samples(Z)
        s_lof = lof.score_samples(Z)
        for i in range(len(d)):
            casos.append((d[cols].iloc[i].values, s_env[i], s_lof[i], etiqueta))

    n = len(casos)
    dd = len(cols)
    txt = f"""// =====================================================================
// FICHERO GENERADO — NO EDITAR A MANO
//
// Generado por server/analisis/exportar_casos_prueba.py
//
// {n} vectores de caracteristicas REALES ({len(nom)} del activo nominal y
// {len(fal)} del activo con fallo) con la puntuacion que produce scikit-learn
// sobre cada uno. Sirven para verificar en el PC que el detector en C++
// reproduce la referencia de Python antes de subirlo a la placa.
//
// Fichero de PRUEBA: no lo incluye el firmware.
// =====================================================================
#ifndef CASOS_MODELO_H
#define CASOS_MODELO_H

#define CASOS_N {n}
#define CASOS_D {dd}
#define CASOS_N_NOMINAL {len(nom)}

// Caracteristicas SIN normalizar, en el orden de MODELO_N_CARACTERISTICAS.
static const float CASOS_X[CASOS_N][CASOS_D] = {{
"""
    for x, _, _, _ in casos:
        txt += "  {" + ", ".join(f"{v:.8e}f" for v in x) + "},\n"
    # Medida CRUDA de cada rafaga, para verificar la derivacion de
    # caracteristicas y no solo la puntuacion. Es donde una discrepancia entre
    # el C++ y el Python seria silenciosa.
    CRUDAS = ["rms_x", "peak_x", "kurt_x", "fdom_x", "adom_x", "f2_x", "a2_x",
              "f3_x", "a3_x", "aud_b0", "aud_b1", "aud_b2", "dif_termico",
              "grad_motor", "retries", "cont_rejects"]
    txt += "};\n\n// Medida CRUDA: " + ", ".join(CRUDAS) + "\n"
    txt += f"#define CASOS_N_CRUDAS {len(CRUDAS)}\n"
    txt += "static const float CASOS_CRUDO[CASOS_N][CASOS_N_CRUDAS] = {\n"
    for etiqueta, d in (("nominal", nom), ("fallo", fal)):
        for i in range(len(d)):
            fila = d[CRUDAS].iloc[i].values
            txt += "  {" + ", ".join(f"{v:.8e}f" for v in fila) + "},\n"
    txt += "};\n\n// Puntuacion de referencia de scikit-learn, envolvente robusta.\nstatic const float CASOS_ENV[CASOS_N] = {\n"
    for _, e, _, _ in casos:
        txt += f"  {e:.8e}f,\n"
    txt += "};\n\n// Puntuacion de referencia de scikit-learn, LOF.\nstatic const float CASOS_LOF[CASOS_N] = {\n"
    for _, _, l, _ in casos:
        txt += f"  {l:.8e}f,\n"
    txt += f"""}};

// Umbrales, los mismos que exporta modelo_referencia.h.
#define CASOS_ENV_UMBRAL {float(np.quantile(env.score_samples(Xn), ALFA)):.8e}f
#define CASOS_LOF_UMBRAL {float(np.quantile(lof.score_samples(Xn), ALFA)):.8e}f

#endif  // CASOS_MODELO_H
"""
    SALIDA.write_text(txt, encoding="utf-8")
    print(f"escrito {SALIDA.name}: {n} casos ({len(nom)} nominal + {len(fal)} fallo), "
          f"{SALIDA.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()

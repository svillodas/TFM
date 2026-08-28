#!/usr/bin/env python3
"""
Exporta el modelo ajustado a un fichero de cabecera C++ para el firmware.

    .venv/bin/python server/analisis/exportar_modelo.py

Escribe device/modelo_referencia.h. ESE FICHERO ES GENERADO: no se edita a mano.
Reentrenar consiste en volver a ejecutar este script y recompilar el firmware.
Lleva anotada la campana y la fecha de las que procede, para que un firmware en
la placa siempre pueda rastrearse a los datos que lo produjeron.

QUE SE EXPORTA Y POR QUE
------------------------
Tres cosas, en orden de coste:

  1. La REGLA sobre el numero de picos significativos. 8 bytes. No es el detector
     principal —es ciega a 4 de las 5 direcciones de fallo examinadas— pero
     identifica QUE clase de desviacion hay y no solo que la hay.

  2. La ENVOLVENTE robusta: vector de medias e inversa de la covarianza. 960 B y
     240 operaciones. Cubre las cinco direcciones.

  3. LOF, el modelo que selecciono el protocolo sin sesgo de espionaje. Exige
     conservar la matriz de ajuste, de modo que ocupa 33 KB. Se emite entre
     guardas de compilacion para poder excluirlo si interesa.

SOBRE EL CONJUNTO DE AJUSTE
---------------------------
El modelo se ajusta sobre TODO el conjunto nominal, no solo sobre el de
desarrollo. Es la practica habitual una vez concluida la seleccion: aprovechar
todas las observaciones disponibles. Debe consignarse la consecuencia: la cifra
validada del 7,8 % de falsos positivos corresponde a la variante ajustada
unicamente sobre desarrollo, que es la que se evaluo contra episodios no vistos.
Para la variante que aqui se exporta no existe estimacion independiente, si bien
incorporar mas episodios solo puede ampliar la variedad de condiciones que el
modelo reconoce como normales.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.covariance import EllipticEnvelope
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

import pipeline as pl
from comparar_modelos import ALFA
from protocolo import particion

SALIDA = Path(__file__).resolve().parents[2] / "device" / "modelo_referencia.h"
K_VECINOS = 10


def vector_c(v, por_linea=6, sangria="  "):
    """Formatea un vector como inicializador de C, con saltos legibles."""
    trozos = [f"{x:.8e}f" for x in np.asarray(v).ravel()]
    lineas, actual = [], []
    for t in trozos:
        actual.append(t)
        if len(actual) == por_linea:
            lineas.append(sangria + ", ".join(actual)); actual = []
    if actual:
        lineas.append(sangria + ", ".join(actual))
    return ",\n".join(lineas)


def main():
    nom, tn = pl.preparar("entrenamiento", verboso=False)
    des, pru, eps_d, eps_p = particion(nom)
    cols = pl.COLUMNAS
    d = len(cols)

    esc = StandardScaler().fit(nom[cols].values)
    X = esc.transform(nom[cols].values)

    # Umbral: cuantil ALFA de las puntuaciones del propio conjunto de ajuste.
    env = EllipticEnvelope(support_fraction=0.9, contamination=ALFA,
                           random_state=0).fit(X)
    u_env = float(np.quantile(env.score_samples(X), ALFA))
    mu = env.location_
    prec = env.get_precision()

    lof = LocalOutlierFactor(n_neighbors=K_VECINOS, novelty=True).fit(X)
    u_lof = float(np.quantile(lof.score_samples(X), ALFA))
    Xf = lof._fit_X
    kdist = lof._distances_fit_X_[:, -1]
    lrd = lof._lrd

    # Regla sobre el numero de picos: intervalo a dos colas del nominal.
    v = nom["n_picos"].values
    lo_p, hi_p = float(np.quantile(v, ALFA / 2)), float(np.quantile(v, 1 - ALFA / 2))

    # Medianas del PROPIO activo. El nodo las necesita para normalizar las
    # magnitudes con unidades sin reintroducir el sesgo entre maquinas, y no
    # puede calcularlas en la primera rafaga: se aprenden en la campana de
    # referencia y viajan en esta cabecera.
    med_rms = float(nom["rms_x"].median())
    med_adom = float(nom["adom_x"].median())
    med_dif = float(nom["dif_termico"].median())

    sello = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    cab = f"""// =====================================================================
// FICHERO GENERADO — NO EDITAR A MANO
//
// Generado por server/analisis/exportar_modelo.py el {sello}
//
// Procedencia de los datos
//   campana         EXP-005 (activo de referencia, estado nominal)
//   duracion        {tn['horas']:.2f} h
//   rafagas         {tn['crudas']} capturadas, {tn['utiles']} utilizables
//   episodios       {tn['episodios']} de marcha
//   filtro calidad  retries <= {pl.MAX_RETRIES}, cont_rejects <= {pl.MAX_CONT_REJECTS},
//                   kurtosis en [{pl.KURT_RANGO[0]:.0f}, {pl.KURT_RANGO[1]:.0f}]
//   umbral marcha   {tn['umbral_marcha']:.6f} m/s^2 (derivado de los datos)
//
// Reentrenar: volver a ejecutar el script y recompilar. No copiar valores.
//
// ADVERTENCIA. El nodo debe NEGARSE A EMITIR VEREDICTO sobre una rafaga con
// mas de {pl.MAX_RETRIES} reintentos del bus, en lugar de juzgarla. Los reintentos FABRICAN
// la firma del fallo sobre un activo sano: con mas de diez, el numero de picos
// significativos de un activo NOMINAL pasa de 1 a 3 y la fundamental estimada
// se derrumba de 49 Hz a 20 Hz. El filtro de calidad es parte del detector.
// =====================================================================
#ifndef MODELO_REFERENCIA_H
#define MODELO_REFERENCIA_H

#include <stdint.h>

// Numero de caracteristicas y su orden. El firmware debe rellenar el vector en
// ESTE MISMO ORDEN o el modelo carece de sentido.
#define MODELO_N_CARACTERISTICAS {d}
"""
    for i, c in enumerate(cols):
        cab += f"//   [{i:2d}] {c:<12} {pl.CARACTERISTICAS[c][:96]}\n"

    cuerpo = f"""
// ---------------------------------------------------------------------
// Constantes de derivacion de caracteristicas. El firmware DEBE construir el
// vector con estos mismos valores y en el mismo orden que la lista de arriba:
// una discrepancia no produce ningun error, solo un veredicto sin sentido.
// ---------------------------------------------------------------------

// Umbral de significacion de un pico espectral, relativo a la mayor amplitud.
#define MODELO_AMP_MIN_RELATIVA {pl.AMP_MIN_RELATIVA:.4f}f

// Medianas del PROPIO activo, aprendidas en la campana de referencia. Sirven
// para normalizar las magnitudes con unidades: el nivel de vibracion difiere
// en un factor 12,5 entre los dos activos medidos, de modo que un valor
// absoluto separaria maquinas en lugar de estados.
#define MODELO_MEDIANA_RMS  {med_rms:.8e}f
#define MODELO_MEDIANA_ADOM {med_adom:.8e}f
#define MODELO_MEDIANA_DIF  {med_dif:.8e}f

// Umbral marcha/parada, derivado de los datos (valle de la distribucion
// bimodal del valor eficaz). Con el compresor detenido no hay vibracion que
// analizar: el nodo NO debe emitir veredicto.
#define MODELO_UMBRAL_MARCHA {tn['umbral_marcha']:.8e}f

// Limites de calidad. Por encima de ellos el nodo debe NEGARSE A JUZGAR: los
// reintentos del bus fabrican la firma del fallo sobre un activo sano.
#define MODELO_MAX_RETRIES {pl.MAX_RETRIES}
#define MODELO_MAX_CONT_REJECTS {pl.MAX_CONT_REJECTS}
#define MODELO_KURT_MIN {pl.KURT_RANGO[0]:.1f}f
#define MODELO_KURT_MAX {pl.KURT_RANGO[1]:.1f}f

// Ventana sobre la que se estima la pendiente termica, en segundos.
#define MODELO_VENTANA_GRADIENTE_S {pl.VENTANA_GRADIENTE_S}

// ---------------------------------------------------------------------
// Normalizacion. Cada caracteristica se centra y se escala antes de
// evaluar cualquier modelo: (x - media) / escala.
// ---------------------------------------------------------------------
static const float MODELO_MEDIA[{d}] = {{
{vector_c(esc.mean_)}
}};
static const float MODELO_ESCALA[{d}] = {{
{vector_c(esc.scale_)}
}};

// ---------------------------------------------------------------------
// 1. REGLA sobre el numero de picos espectrales significativos.
//    Significativo = amplitud >= {pl.AMP_MIN_RELATIVA:.2f} de la mayor de las tres.
//    Sobre la caracteristica SIN normalizar.
//
//    No es el detector principal: es ciega a 4 de las 5 direcciones de
//    fallo examinadas. Su valor es que identifica QUE clase de
//    desviacion hay, no solo que la hay.
// ---------------------------------------------------------------------
#define MODELO_PICOS_MIN {lo_p:.4f}f
#define MODELO_PICOS_MAX {hi_p:.4f}f

// ---------------------------------------------------------------------
// 2. ENVOLVENTE robusta. Distancia de Mahalanobis al centro de la nube
//    nominal. La puntuacion es -(x-mu)' P (x-mu); es anomala si queda
//    por debajo del umbral.
//    Coste: {4*(d*d+d)} B y del orden de {d*d+d} operaciones por rafaga.
// ---------------------------------------------------------------------
static const float MODELO_ENV_CENTRO[{d}] = {{
{vector_c(mu)}
}};
static const float MODELO_ENV_PRECISION[{d}][{d}] = {{
"""
    for fila in prec:
        cuerpo += "  {\n" + vector_c(fila, sangria="    ") + "\n  },\n"
    cuerpo += f"""}};
#define MODELO_ENV_UMBRAL {u_env:.8e}f

// ---------------------------------------------------------------------
// 3. LOF. Es el modelo que selecciono el protocolo sin sesgo de
//    espionaje (server/analisis/protocolo.py), con un 7,8 % de falsos
//    positivos sobre episodios nunca vistos y 100 % de deteccion.
//
//    Exige conservar la matriz de ajuste: {4*(Xf.size+kdist.size+lrd.size)/1024:.1f} KB. Se emite entre
//    guardas para poder excluirlo. La placa tiene 8 MB de PSRAM, de modo
//    que la restriccion no es real; la guarda existe para poder medir el
//    coste de cada alternativa por separado.
//
//    Puntuacion de una observacion z, verificada contra scikit-learn con
//    un error maximo de 1,8e-15:
//      1. distancias euclideas de z a las {Xf.shape[0]} filas de la matriz
//      2. sus {K_VECINOS} vecinos mas cercanos
//      3. alcance_i = max(KDIST[i], dist_i) para cada vecino
//      4. lrd_z = 1 / media(alcance)
//      5. puntuacion = -media(LRD[i] / lrd_z)
// ---------------------------------------------------------------------
#ifndef MODELO_SIN_LOF
#define MODELO_LOF_N {Xf.shape[0]}
#define MODELO_LOF_K {K_VECINOS}
#define MODELO_LOF_UMBRAL {u_lof:.8e}f

static const float MODELO_LOF_AJUSTE[{Xf.shape[0]}][{d}] = {{
"""
    for fila in Xf:
        cuerpo += "  {" + ", ".join(f"{x:.6e}f" for x in fila) + "},\n"
    cuerpo += f"""}};
static const float MODELO_LOF_KDIST[{len(kdist)}] = {{
{vector_c(kdist)}
}};
static const float MODELO_LOF_LRD[{len(lrd)}] = {{
{vector_c(lrd)}
}};
#endif  // MODELO_SIN_LOF

#endif  // MODELO_REFERENCIA_H
"""
    SALIDA.write_text(cab + cuerpo, encoding="utf-8")
    tam = SALIDA.stat().st_size
    print(f"escrito {SALIDA.relative_to(SALIDA.parents[1])}: {tam/1024:.0f} KB de fuente")
    print(f"  {d} caracteristicas, ajustado sobre {len(nom)} rafagas de {tn['episodios']} episodios")
    print(f"  regla n_picos:  intervalo [{lo_p:.3f}, {hi_p:.3f}]")
    print(f"  envolvente:     umbral {u_env:.6e}   {4*(d*d+d)} B")
    print(f"  LOF:            umbral {u_lof:.6e}   {4*(Xf.size+kdist.size+lrd.size)/1024:.1f} KB")
    print(f"  medianas del activo: rms {med_rms:.4f}  adom {med_adom:.4f}  dif {med_dif:.4f}")
    print(f"  umbral marcha: {tn['umbral_marcha']:.4f} m/s2   calidad: retries<={pl.MAX_RETRIES}")


if __name__ == "__main__":
    main()

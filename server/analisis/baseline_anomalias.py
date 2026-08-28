#!/usr/bin/env python3
"""
Detector de anomalias: el modelo elegido, con su evaluacion y sus limitaciones.

La eleccion del modelo esta razonada en README.md y medida en
comparar_modelos.py: es la regla de dos umbrales sobre r2 = f2_x / fdom_x. Iguala
a Isolation Forest en estabilidad y en falsos positivos, tiene un hiperparametro
frente a tres, y es el unico candidato que se embarca en el ESP32 con dos
comparaciones en coma flotante.

Se conserva ademas el Isolation Forest como contraste, y el detector sobre
caracteristicas DIMENSIONALES como demostracion del sesgo que hay que evitar.

    .venv/bin/python server/analisis/baseline_anomalias.py
"""
import numpy as np
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

import pipeline as pl

ALFA = 0.05          # tasa de falsos positivos objetivo

# ELECCION REVISADA (2026-08-27). La primera version de este script elegia una
# regla de dos umbrales sobre n_picos, por su tasa de falsos positivos. La
# eleccion era incorrecta por dos motivos que se comprobaron despues:
#
#  1. La regla no gana a los modelos de ML: dandoles UNICAMENTE n_picos, los
#     seis candidatos convergen al mismo 8,3 % de falsos positivos en el peor
#     episodio. Con una sola caracteristica hay una sola frontera que encontrar.
#     El merito era de la caracteristica y no del algoritmo, y la comparacion
#     original era injusta porque a los modelos se les daban las 15
#     caracteristicas, incluidas varias sin capacidad de separacion.
#
#  2. Esa caracteristica se eligio SABIENDO cual era el fallo, de modo que su
#     ventaja no sobrevive a un fallo distinto. El analisis de cobertura
#     (cobertura_modos.py) lo confirma: la regla es ciega a 4 de las 5
#     direcciones de fallo examinadas. Un detector de anomalias tiene por objeto
#     precisamente los fallos que no se conocen de antemano, de modo que
#     optimizar contra el unico fallo disponible es sobreajuste.
#
# El detector principal es por tanto la ENVOLVENTE ROBUSTA sobre todas las
# caracteristicas: cubre las 5 direcciones y su tasa de falsos positivos
# ponderada por rafagas es del 5,6 %. La regla se conserva como confirmacion de
# alta confianza para fallos de naturaleza armonica.
CARACTERISTICA = "n_picos"      # regla de confirmacion, ya no el detector principal
SECUNDARIA = "r2"               # identifica QUE armonico, no solo cuantos picos


def intervalo(v, alfa=ALFA):
    """Intervalo nominal a dos colas para la tasa de falsos positivos dada."""
    return np.quantile(v, alfa / 2), np.quantile(v, 1 - alfa / 2)


def main():
    print("=" * 74)
    print("ETAPAS 1-4: DATOS, LIMPIEZA Y SEGMENTACION")
    print("=" * 74)
    nom, tn = pl.preparar("entrenamiento"); pl.resumen("nominal", tn)
    fal, tf = pl.preparar("fallo");         pl.resumen("fallo", tf)

    print("\n" + "=" * 74)
    print("ETAPA 5: CARACTERISTICAS")
    print("=" * 74)
    print(f"{'caracteristica':<10}{'nominal':>20}{'fallo':>20}{'separacion':>12}")
    for c in pl.COLUMNAS:
        a, b = nom[c], fal[c]
        sep = abs(a.median() - b.median()) / (a.std() + b.std() + 1e-12)
        print(f"{c:<10}{a.median():10.3f} +-{a.std():7.3f}"
              f"{b.median():10.3f} +-{b.std():7.3f}{sep:9.2f} sd")

    print("\nel nivel absoluto, que NO se usa y por que:")
    for c in pl.DIMENSIONALES:
        print(f"  {c:8s} nominal {nom[c].median():8.4f}   fallo {fal[c].median():8.4f}"
              f"   -> factor {nom[c].median()/fal[c].median():5.1f}x")

    print("\n" + "=" * 74)
    print(f"ETAPA 6a: REGLA DE CONFIRMACION — dos umbrales sobre {CARACTERISTICA}")
    print("=" * 74)
    v_nom, v_fal = nom[CARACTERISTICA].values, fal[CARACTERISTICA].values
    lo, hi = intervalo(v_nom)
    fp = ((v_nom < lo) | (v_nom > hi)).mean()
    det = ((v_fal < lo) | (v_fal > hi)).mean()
    print(f"  intervalo nominal: [{lo:.3f}, {hi:.3f}]"
          + ("   sin margen: las discrepantes caen fuera del cuantil" if hi == lo else ""))
    print(f"  nominal: mediana {np.median(v_nom):.3f}   fallo: mediana {np.median(v_fal):.3f}")
    print(f"  falsos positivos {int(fp*len(v_nom)):4d}/{len(v_nom):4d} = {100*fp:5.1f} %")
    print(f"  detectados       {int(det*len(v_fal)):4d}/{len(v_fal):4d} = {100*det:5.1f} %")
    print(f"\n  codigo equivalente en el nodo:")
    print(f"      bool anomalia = (nPicos < {lo:.3f}f) || (nPicos > {hi:.3f}f);")

    print(f"\n  CORROBORACION con {SECUNDARIA}, que identifica QUE armonico y no solo")
    print( "  cuantos picos hay. Es la regla mas conservadora de las dos:")
    w_n, w_f = nom[SECUNDARIA].values, fal[SECUNDARIA].values
    lo2, hi2 = intervalo(w_n)
    fp2 = ((w_n < lo2) | (w_n > hi2)).mean(); det2 = ((w_f < lo2) | (w_f > hi2)).mean()
    print(f"      intervalo [{lo2:.3f}, {hi2:.3f}]  ->  FP {100*fp2:.1f} %  deteccion {100*det2:.1f} %")

    n_out = int(((v_nom < lo) | (v_nom > hi)).sum())
    degenerado = (hi == lo)
    print(f"""
  LO QUE ESTA CIFRA SIGNIFICA Y LO QUE NO. {CARACTERISTICA} vale 1 en {len(v_nom)-n_out} de las
  {len(v_nom)} rafagas nominales y {n_out} quedan fuera del intervalo. El conjunto procede de
  {tn['episodios']} episodios de marcha, de modo que la cifra ya recoge variabilidad entre
  condiciones de operacion y no solo entre rafagas correlacionadas del mismo
  arranque.""" + ("""

  El intervalo sigue siendo un punto porque las observaciones discrepantes caen
  fuera del cuantil que lo fija. Eso no lo invalida, pero significa que el
  margen de tolerancia no esta estimado: el modelo separa 'un pico' de
  'mas de uno' y no dispone de una nocion de cuanto puede acercarse un activo
  sano a la frontera.""" if degenerado else "") + f"""

  La cifra honesta no es esta sino la de la validacion cruzada por episodios,
  en comparar_modelos.py: deja fuera un arranque completo, ajusta sobre los
  demas y mide sobre una condicion no vista. Alli esta regla da un 0,5 % de
  falsos positivos de media y un 8,3 % en el peor episodio, frente al 25-34 %
  en el peor episodio de todos los demas candidatos.

  RIESGO QUE SUBSISTE. Los reintentos del bus I2C FABRICAN esta firma sobre un
  activo sano: con mas de diez reintentos la mediana de {CARACTERISTICA} en el nodo
  nominal pasa de 1 a 3 y la fundamental estimada se derrumba de 49 Hz a 20 Hz.
  El filtro de calidad es por tanto parte del detector y no un preproceso: el
  nodo debe NEGARSE A EMITIR VEREDICTO sobre una rafaga con mas de
  {pl.MAX_RETRIES} reintentos, en lugar de juzgarla.

  Por eso se conserva {SECUNDARIA} como corroboracion: identifica QUE armonico aparece
  y no solo cuantos picos hay, de modo que un segundo armonico legitimo del giro
  no lo dispara.""")

    print("\n" + "=" * 74)
    print("DETECTOR PRINCIPAL: envolvente robusta sobre las {} caracteristicas".format(len(pl.COLUMNAS)))
    print("=" * 74)
    esc = StandardScaler().fit(nom[pl.COLUMNAS].values)
    env = EllipticEnvelope(support_fraction=0.9, contamination=ALFA,
                           random_state=0).fit(esc.transform(nom[pl.COLUMNAS].values))
    s_n = env.score_samples(esc.transform(nom[pl.COLUMNAS].values))
    s_f = env.score_samples(esc.transform(fal[pl.COLUMNAS].values))
    u = np.quantile(s_n, ALFA)
    print(f"  falsos positivos {(s_n<u).sum():4d}/{len(s_n):4d} = {100*(s_n<u).mean():5.1f} %")
    print(f"  detectados       {(s_f<u).sum():4d}/{len(s_f):4d} = {100*(s_f<u).mean():5.1f} %")
    print("  se embarca como una forma cuadratica con matriz precalculada:")
    print(f"    {len(pl.COLUMNAS)}x{len(pl.COLUMNAS)} flotantes = {4*len(pl.COLUMNAS)**2} bytes de matriz,"
          f" mas {len(pl.COLUMNAS)} de vector de medias")
    print("\n  Por validacion cruzada por episodios (ver comparar_modelos.py):")
    print("    falsos positivos 5,1 % de media, 5,6 % ponderado por rafagas,")
    print("    25,0 % en el peor episodio -- que son 3 rafagas de 12, y 11 de los")
    print("    22 episodios dan 0 %.")
    print("  Cubre las 5 direcciones de fallo examinadas, frente a 1 de la regla.")

    print("\n" + "=" * 74)
    print("DEMOSTRACION DEL SESGO: el mismo detector con caracteristicas DIMENSIONALES")
    print("=" * 74)
    dim = ["rms_x", "peak_x", "kurt_x"]
    e2 = StandardScaler().fit(nom[dim].values)
    i2 = IsolationForest(n_estimators=300, random_state=0).fit(e2.transform(nom[dim].values))
    t_n, t_f = i2.score_samples(e2.transform(nom[dim].values)), i2.score_samples(e2.transform(fal[dim].values))
    u2 = np.quantile(t_n, ALFA)
    print(f"  detectados {100*(t_f<u2).mean():5.1f} % usando rms_x, peak_x, kurt_x")
    print("  NINGUNA de las tres contiene la firma del fallo: el filtro paso bajo a 150 Hz")
    print("  la elimina de los estadisticos temporales. Lo que separa es el nivel de")
    print("  vibracion, distinto entre las dos MAQUINAS. Es el modo de error a evitar.")

    print("\n" + "=" * 74)
    print("LO QUE ESTAS CIFRAS NO ESTABLECEN")
    print("=" * 74)
    print(f"""  1. No hay validacion cruzada por episodios. El conjunto nominal tiene
     {tn['episodios']} episodio(s) de marcha y el conjunto con fallo {tf['episodios']}. Las rafagas de un
     mismo episodio describen la misma condicion y estan correlacionadas: las
     {len(nom)} y {len(fal)} observaciones NO son independientes.
  2. Los dos activos son maquinas distintas, de modo que el contraste no separa
     el efecto del fallo del de la variabilidad entre ejemplares. Las
     caracteristicas adimensionales acotan ese sesgo; no lo eliminan.
  3. El umbral [{lo:.3f}, {hi:.3f}] no esta calibrado: se apoya en {len(nom)} observaciones
     de {tn['episodios']} episodio(s). Recalcularlo antes de embarcarlo.
  4. El modo de fallo no esta identificado. Hay una firma caracterizada, no un
     mecanismo.""")


if __name__ == "__main__":
    main()

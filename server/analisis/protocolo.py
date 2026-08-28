#!/usr/bin/env python3
"""
Protocolo de seleccion y evaluacion SIN SESGO DE ESPIONAJE.

Este script existe porque el analisis anterior lo cometia. La caracteristica
n_picos se eligio ordenando las candidatas por su separacion MEDIDA CONTRA EL
CONJUNTO CON FALLO, es decir usando el conjunto de evaluacion para tomar una
decision de diseno. La cifra que resultaba —8,3 % de falsos positivos en el peor
episodio— era por tanto optimista, y la conclusion que se derivaba de ella —que
una regla de una caracteristica superaba a los modelos de aprendizaje
automatico— era ademas falsa: dandoles esa misma caracteristica, los seis
candidatos convergen al mismo valor.

QUE SE PERMITE Y QUE NO
-----------------------
El detector es de una clase: en explotacion solo dispone de datos del activo
sano. De ello se sigue lo que es legitimo:

  PERMITIDO, porque en explotacion tambien se tendria:
    - Cualquier decision tomada sobre el conjunto NOMINAL.
    - Conocimiento previo del dominio: que magnitudes son indicadores de estado
      en analisis de vibracion esta establecido en la literatura y no se deduce
      de estos datos.
    - Perturbaciones SINTETICAS del conjunto nominal para localizar puntos
      ciegos, porque no emplean el fallo real.

  PROHIBIDO:
    - Elegir, ordenar o descartar caracteristicas por su comportamiento sobre
      el conjunto con fallo.
    - Ajustar cualquier umbral mirando la tasa de deteccion.
    - Repetir la evaluacion final tras haberla visto.

PARTICION
---------
El conjunto nominal se divide POR EPISODIOS y de forma CRONOLOGICA:

    desarrollo   los episodios mas antiguos   ->  todas las decisiones
    prueba       los episodios mas recientes  ->  se mira UNA vez, al final

Cronologica y no aleatoria porque reproduce la situacion real: se ajusta con lo
capturado hasta hoy y se despliega sobre lo que venga despues. Una particion
aleatoria reparte episodios contiguos entre ambos lados y filtra informacion del
futuro.

    .venv/bin/python server/analisis/protocolo.py
"""
import sys
import warnings

import numpy as np
import pandas as pd

import pipeline as pl
from comparar_modelos import ALFA, catalogo, evaluar

warnings.filterwarnings("ignore")

FRACCION_DESARROLLO = 0.65     # de los episodios nominales, los mas antiguos


def particion(nom):
    """Divide los episodios nominales de forma cronologica."""
    orden = (nom.groupby("episodio").t.min().sort_values().index.tolist())
    corte = max(1, int(round(len(orden) * FRACCION_DESARROLLO)))
    desarrollo, prueba = orden[:corte], orden[corte:]
    return (nom[nom.episodio.isin(desarrollo)].copy(),
            nom[nom.episodio.isin(prueba)].copy(),
            desarrollo, prueba)


def fp_por_episodio(modelo, datos, columnas):
    """Falsos positivos dejando fuera un episodio, DENTRO del conjunto dado.

    No interviene ningun dato con fallo: mide exclusivamente cuanto se equivoca
    el modelo sobre el activo sano, que es informacion disponible en explotacion.
    """
    fps, pesos = [], []
    vacio = datos.iloc[:0][columnas].values
    for e in sorted(datos.episodio.unique()):
        tr, te = datos[datos.episodio != e], datos[datos.episodio == e]
        if len(tr) < 20 or len(te) < 3:
            continue
        esc_fit = tr[columnas].values
        from sklearn.preprocessing import StandardScaler
        esc = StandardScaler().fit(esc_fit)
        modelo.fit(esc.transform(esc_fit), columnas)
        s_tr = modelo.score(esc.transform(esc_fit), columnas)
        umbral = np.quantile(s_tr, ALFA)
        s_te = modelo.score(esc.transform(te[columnas].values), columnas)
        fps.append(float(np.mean(s_te < umbral)))
        pesos.append(len(te))
    if not fps:
        return np.nan, np.nan, np.nan, 0
    fps, pesos = np.array(fps), np.array(pesos)
    return (float(fps.mean()), float((fps * pesos).sum() / pesos.sum()),
            float(fps.max()), len(fps))


def main():
    print("=" * 78)
    print("PROTOCOLO SIN SESGO DE ESPIONAJE")
    print("=" * 78)
    nom, tn = pl.preparar("entrenamiento", verboso=False)
    pl.resumen("nominal", tn)

    des, pru, eps_d, eps_p = particion(nom)
    print(f"\n  particion cronologica por episodios:")
    print(f"    desarrollo  {len(eps_d):3d} episodios, {len(des):5d} rafagas"
          f"   hasta {des.t.max().strftime('%d %H:%M')}")
    print(f"    prueba      {len(eps_p):3d} episodios, {len(pru):5d} rafagas"
          f"   desde {pru.t.min().strftime('%d %H:%M')}")

    # ---------------------------------------------------------------
    # FASE 1. Caracteristicas: fijadas por conocimiento del dominio.
    # NO se seleccionan por rendimiento. Ordenarlas por su separacion
    # frente al fallo es precisamente el espionaje que se quiere evitar.
    # ---------------------------------------------------------------
    cols = pl.COLUMNAS
    print(f"\n  FASE 1 — caracteristicas: las {len(cols)} fijadas a priori.")
    print("           No se seleccionan por rendimiento: hacerlo mirando el")
    print("           conjunto con fallo es el sesgo que este protocolo evita.")

    # ---------------------------------------------------------------
    # FASE 2. Modelo: se elige por su comportamiento sobre el activo
    # SANO del conjunto de desarrollo, y por cobertura sintetica.
    # Ningun dato con fallo interviene.
    # ---------------------------------------------------------------
    print(f"\n  FASE 2 — eleccion de modelo, solo con el activo SANO de desarrollo")
    print(f"  {'modelo':<20}{'FP media':>10}{'FP ponder.':>12}{'peor ep':>10}{'eps':>6}")
    resultados = {}
    for nombre, modelo in catalogo().items():
        m, p, w, n = fp_por_episodio(modelo, des, cols)
        resultados[nombre] = (m, p, w, n)
        print(f"  {nombre:<20}{100*m:9.1f} %{100*p:11.1f} %{100*w:9.1f} %{n:6d}")

    import cobertura_modos as cm
    Xd = des[cols].values
    print(f"\n  FASE 2b — cobertura de direcciones de fallo (perturbaciones SINTETICAS")
    print(f"            del propio conjunto sano; no interviene el fallo real)")
    print(f"  {'modelo':<20}" + "".join(f"{m[:11]:>13}" for m in cm.MODOS))
    cobertura = {}
    for nombre, modelo in catalogo().items():
        det = [evaluar(modelo, Xd, Xd[:0], cm.perturbar(des, m)[cols].values, cols)[1]
               for m in cm.MODOS]
        cobertura[nombre] = sum(1 for x in det if x > 0.5)
        print(f"  {nombre:<20}" + "".join(f"{100*x:11.0f} %" for x in det))

    # Criterio declarado ANTES de mirar nada del fallo: se exige cubrir el
    # mayor numero de direcciones y, entre los que empaten, menor FP ponderado.
    elegido = min(
        catalogo(),
        key=lambda k: (-cobertura[k], resultados[k][1]))
    print(f"\n  MODELO ELEGIDO: {elegido}")
    print(f"    cobertura {cobertura[elegido]} de {len(cm.MODOS)} direcciones,"
          f" FP ponderado {100*resultados[elegido][1]:.1f} % en desarrollo")
    print(f"    criterio, declarado antes de mirar el fallo: maxima cobertura y,")
    print(f"    a igual cobertura, menor FP ponderado.")

    # ---------------------------------------------------------------
    # FASE 3. Evaluacion final. Se mira UNA vez.
    # ---------------------------------------------------------------
    fal, tf = pl.preparar("fallo", verboso=False)
    modelo = catalogo()[elegido]
    from sklearn.preprocessing import StandardScaler
    esc = StandardScaler().fit(des[cols].values)
    modelo.fit(esc.transform(des[cols].values), cols)
    s_des = modelo.score(esc.transform(des[cols].values), cols)
    umbral = np.quantile(s_des, ALFA)
    s_pru = modelo.score(esc.transform(pru[cols].values), cols)
    s_fal = modelo.score(esc.transform(fal[cols].values), cols)

    print("\n" + "=" * 78)
    print("FASE 3 — EVALUACION FINAL, sobre datos nunca usados para decidir")
    print("=" * 78)
    print(f"  falsos positivos, episodios de prueba   "
          f"{(s_pru<umbral).sum():4d}/{len(s_pru):4d} = {100*(s_pru<umbral).mean():5.1f} %")
    print(f"  deteccion, activo con fallo             "
          f"{(s_fal<umbral).sum():4d}/{len(s_fal):4d} = {100*(s_fal<umbral).mean():5.1f} %")
    print(f"\n  Para contraste, la cifra que se obtenia CON espionaje era del")
    print(f"  {100*resultados[elegido][2]:.1f} % en el peor episodio del conjunto completo.")
    print(f"\n  LIMITACION QUE ESTE PROTOCOLO NO ELIMINA: los dos activos son")
    print(f"  maquinas distintas, de modo que la cifra de deteccion no separa el")
    print(f"  efecto del fallo del de la variabilidad entre ejemplares. El")
    print(f"  protocolo evita el espionaje, no ese sesgo, que exige un fallo")
    print(f"  inducido sobre el propio activo de referencia.")


if __name__ == "__main__":
    main()

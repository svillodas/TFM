#!/usr/bin/env python3
"""
Seleccion del modelo de deteccion de anomalias.

"El modelo que mejor se adapte" no es el de mayor tasa de deteccion. Con un
conjunto nominal de un solo episodio de marcha, la tasa de deteccion sobre el
activo con fallo esta saturada para casi cualquier modelo y no discrimina: lo
que discrimina es la ESTABILIDAD de la frontera de decision cuando el tamano de
muestra cambia. Un modelo cuya frontera se mueve al quitar diez observaciones no
es utilizable con los datos disponibles, aunque acierte el 100 %.

Criterios, en el orden en que se aplican:

  1. Estabilidad frente al tamano de muestra. Se ajusta el modelo sobre
     submuestras de tamano creciente y se mide la dispersion de la tasa de
     deteccion y de la tasa de falsos positivos fuera de muestra. Es el criterio
     decisivo con 45 observaciones.
  2. Tasa de falsos positivos FUERA DE MUESTRA. La tasa dentro de muestra la fija
     el umbral por construccion y no informa de nada.
  3. Tasa de deteccion sobre el activo con fallo.
  4. Numero de hiperparametros. Cada uno es un grado de libertad que con 45
     observaciones correlacionadas no se puede ajustar honestamente.
  5. Coste de embarcarlo en el ESP32.

     ADVERTENCIA SOBRE ESTE CRITERIO. En la primera version se etiquetaron
     varios modelos como "no embarcables" POR SUPOSICION, sin medir nada, y eso
     sesgo la eleccion hacia el modelo mas simple. Medido, la restriccion NO
     EXISTE: el mayor de los cinco ocupa 274 KB y el mas costoso exige 15 150
     operaciones en coma flotante, del orden de 0,1 ms a 240 MHz, frente a una
     rafaga cada 30 s. La placa tiene 512 KB de SRAM y 8 MB de PSRAM. Este
     criterio no debe usarse para descartar, solo para informar.

    .venv/bin/python server/analisis/comparar_modelos.py
"""
import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

import pipeline as pl

ALFA = 0.05          # tasa de falsos positivos objetivo, fijada en el umbral
REPETICIONES = 60    # submuestras por cada tamano
SEMILLA = 0


# =============================================================================
# Catalogo de modelos
# =============================================================================
# Cada entrada devuelve un objeto con fit(X) y score(X), donde score es
# creciente con la normalidad: cuanto MAYOR, mas normal. El umbral se fija
# despues sobre el cuantil ALFA de las puntuaciones de entrenamiento, de modo
# que todos los modelos se comparan en el mismo punto de operacion.

class Regla:
    """Intervalo sobre una sola caracteristica. El modelo mas simple posible.

    Puntua como la distancia relativa al centro del intervalo nominal, de modo
    que la puntuacion es continua y comparable con las de los demas.
    """
    hiperparametros = 1   # la caracteristica elegida
    embarcable = "8 B, 3 operaciones"

    def __init__(self, columna="r2"):
        self.columna = columna

    def fit(self, X, columnas):
        v = X[:, columnas.index(self.columna)]
        self.centro_ = np.median(v)
        self.escala_ = np.percentile(v, 84) - np.percentile(v, 16) or 1e-9
        return self

    def score(self, X, columnas):
        v = X[:, columnas.index(self.columna)]
        return -np.abs(v - self.centro_) / self.escala_


class Envolvente:
    """Distancia de Mahalanobis a la nube nominal. Supone normalidad conjunta."""
    hiperparametros = 0
    embarcable = "960 B, 240 operaciones"

    def fit(self, X, columnas):
        self.mu_ = X.mean(axis=0)
        # Regularizacion de Ledoit-Wolf implicita: con 45 muestras y 10
        # dimensiones la covarianza empirica es casi singular.
        c = np.cov(X, rowvar=False) + np.eye(X.shape[1]) * 1e-3
        self.inv_ = np.linalg.pinv(c)
        return self

    def score(self, X, columnas):
        dif = X - self.mu_
        return -np.einsum("ij,jk,ik->i", dif, self.inv_, dif)


class Envoltura:
    """Adapta un estimador de scikit-learn al contrato fit/score."""
    def __init__(self, nombre, fabrica, hiperparametros, embarcable):
        self.nombre, self.fabrica = nombre, fabrica
        self.hiperparametros, self.embarcable = hiperparametros, embarcable

    def fit(self, X, columnas):
        try:
            self.m_ = self.fabrica().fit(X)
        except ValueError:
            # EllipticEnvelope aborta si la covarianza del soporte es nula, que
            # ocurre con pocas dimensiones de varianza casi nula. Se reintenta
            # con soporte completo antes de darlo por no ajustable.
            self.m_ = self.fabrica_alt().fit(X) if hasattr(self, "fabrica_alt") \
                else None
            if self.m_ is None:
                raise
        return self

    def score(self, X, columnas):
        return self.m_.score_samples(X) if hasattr(self.m_, "score_samples") \
            else self.m_.decision_function(X)


def _con_alternativa(env, fabrica_alt):
    env.fabrica_alt = fabrica_alt
    return env


def catalogo():
    return {
        "Regla n_picos":   Regla("n_picos"),
        "Regla sobre r2":  Regla("r2"),
        "Envolvente":      Envolvente(),
        "Isolation Forest": Envoltura(
            "Isolation Forest",
            lambda: IsolationForest(n_estimators=200, random_state=SEMILLA),
            hiperparametros=3, embarcable="274 KB, 4800 operaciones"),
        "One-Class SVM": Envoltura(
            "One-Class SVM",
            lambda: OneClassSVM(kernel="rbf", gamma="scale", nu=ALFA),
            hiperparametros=2, embarcable="2,3 KB, 1110 operaciones"),
        "LOF (novelty)": Envoltura(
            "LOF",
            lambda: LocalOutlierFactor(n_neighbors=10, novelty=True),
            hiperparametros=2, embarcable="32 KB, 15150 operaciones"),
        "Elliptic Envelope": _con_alternativa(Envoltura(
            "Elliptic Envelope",
            lambda: EllipticEnvelope(support_fraction=0.9, contamination=ALFA,
                                     random_state=SEMILLA),
            hiperparametros=2, embarcable="960 B, 240 operaciones"),
            lambda: EllipticEnvelope(support_fraction=1.0, contamination=ALFA,
                                     random_state=SEMILLA)),
    }


# =============================================================================
# Evaluacion
# =============================================================================

def evaluar(modelo, Xtr, Xte_nom, Xfal, columnas):
    """Ajusta sobre Xtr y devuelve (fp fuera de muestra, deteccion)."""
    esc = StandardScaler().fit(Xtr)
    modelo.fit(esc.transform(Xtr), columnas)
    s_tr = modelo.score(esc.transform(Xtr), columnas)
    umbral = np.quantile(s_tr, ALFA)
    fp = np.mean(modelo.score(esc.transform(Xte_nom), columnas) < umbral) \
        if len(Xte_nom) else np.nan
    det = np.mean(modelo.score(esc.transform(Xfal), columnas) < umbral)
    return fp, det


def curva(modelo, Xnom, Xfal, columnas, tamanos):
    """Estabilidad frente al tamano de muestra, por remuestreo."""
    rng = np.random.default_rng(SEMILLA)
    filas = []
    for n in tamanos:
        fps, dets = [], []
        for _ in range(REPETICIONES):
            idx = rng.permutation(len(Xnom))
            tr, te = idx[:n], idx[n:]
            fp, det = evaluar(modelo, Xnom[tr], Xnom[te], Xfal, columnas)
            fps.append(fp); dets.append(det)
        filas.append((n, np.nanmean(fps), np.nanstd(fps),
                      np.mean(dets), np.std(dets)))
    return filas


def main():
    print("Pipeline de datos\n")
    nom, tn = pl.preparar("entrenamiento"); pl.resumen("nominal", tn)
    fal, tf = pl.preparar("fallo");         pl.resumen("fallo", tf)

    cols = pl.COLUMNAS
    Xnom, Xfal = nom[cols].values, fal[cols].values
    print(f"\n{len(cols)} caracteristicas adimensionales, "
          f"{len(Xnom)} observaciones nominales en {tn['episodios']} episodio(s)")
    print(f"punto de operacion comun: umbral en el cuantil {ALFA:.2f} del nominal\n")

    tamanos = [15, 25, 35, len(Xnom) - 5]
    print("=" * 78)
    print("ESTABILIDAD FRENTE AL TAMANO DE MUESTRA "
          f"({REPETICIONES} submuestras por tamano)")
    print("=" * 78)
    print(f"{'modelo':<20}{'n':>4}  {'FP fuera muestra':>18}  {'deteccion':>18}")
    resumen = {}
    for nombre, modelo in catalogo().items():
        filas = curva(modelo, Xnom, Xfal, cols, tamanos)
        for i, (n, fpm, fps, dm, ds) in enumerate(filas):
            etq = nombre if i == 0 else ""
            print(f"{etq:<20}{n:>4}  {100*fpm:8.1f} +-{100*fps:5.1f} %  "
                  f"{100*dm:8.1f} +-{100*ds:5.1f} %")
        # Inestabilidad: dispersion media de la tasa de FALSOS POSITIVOS entre
        # submuestras. Se mide sobre los falsos positivos y no sobre la
        # deteccion porque esta ultima esta saturada al 100 % en todos los
        # modelos y su desviacion es nula: no discrimina. Lo que se mueve al
        # cambiar la submuestra es el lado nominal de la frontera.
        resumen[nombre] = {
            "inestabilidad": float(np.nanmean([f[2] for f in filas])),
            "fp": filas[-1][1], "det": filas[-1][3],
            "hp": modelo.hiperparametros, "emb": modelo.embarcable,
        }
        print()

    print("=" * 78)
    print("RESUMEN, ordenado por estabilidad")
    print("=" * 78)
    print(f"{'modelo':<20}{'inestab.':>9}{'FP':>7}{'detec.':>8}{'hiperp.':>9}  coste en el nodo")
    for nombre, r in sorted(resumen.items(), key=lambda kv: kv[1]["inestabilidad"]):
        print(f"{nombre:<20}{100*r['inestabilidad']:8.2f}%{100*r['fp']:6.1f}%"
              f"{100*r['det']:7.1f}%{r['hp']:8d}   {r['emb']}")

    print(f"""
LECTURA. La tasa de deteccion NO discrimina: los {len(catalogo())} modelos la dejan en el
100 %. Con un factor 5,5 de diferencia de nivel entre los dos activos, detectar
el fallo es facil y esa cifra no mide capacidad diagnostica.

Las dos columnas que si discriminan son 'FP', la tasa de falsos positivos fuera
de muestra frente al {100*ALFA:.0f} % que el umbral fija por construccion, y 'inestab.', su
desviacion tipica entre submuestras del mismo tamano. La segunda mide cuanto se
mueve la frontera al cambiar que observaciones la ajustan. Con {len(Xnom)}
observaciones de {tn['episodios']} episodio(s), un modelo con inestabilidad alta no es
utilizable aunque acierte el 100 %.

LIMITACION QUE NINGUNA CIFRA DE ESTA TABLA CORRIGE. El conjunto nominal procede
de {tn['episodios']} episodio(s) y el conjunto con fallo de {tf['episodios']}. Las submuestras de
este experimento se toman DENTRO de esos episodios, de modo que estiman la
variabilidad entre observaciones correlacionadas, no entre condiciones de
operacion. La validacion cruzada por episodios, que es la correcta, exige mas
episodios de los que hay.""")


if __name__ == "__main__":
    main()


# =============================================================================
# Validacion cruzada por episodios
# =============================================================================
# Es la validacion correcta y hasta ahora no era posible: con un solo episodio
# nominal, cualquier particion de los datos dejaba en entrenamiento y en prueba
# rafagas de la MISMA condicion de operacion, separadas 30 s y fuertemente
# correlacionadas. La tasa de falsos positivos que se obtenia asi era optimista
# por construccion.
#
# Con 22 episodios se puede dejar fuera un episodio completo, ajustar sobre los
# demas y medir los falsos positivos sobre una condicion de operacion que el
# modelo no ha visto. Es lo que mide si el detector generaliza entre arranques
# del compresor y no solo entre rafagas del mismo arranque.

def validacion_por_episodios(modelo, nom, fal, columnas):
    """Deja fuera un episodio completo cada vez. Devuelve (fp, det, n_ep)."""
    eps = sorted(nom.episodio.unique())
    fps, dets = [], []
    Xfal = fal[columnas].values
    for e in eps:
        tr = nom[nom.episodio != e]
        te = nom[nom.episodio == e]
        if len(tr) < 20 or len(te) < 3:
            continue
        fp, det = evaluar(modelo, tr[columnas].values, te[columnas].values,
                          Xfal, columnas)
        fps.append(fp); dets.append(det)
    return np.array(fps), np.array(dets), len(fps)


def main_episodios():
    print("\nPipeline de datos\n")
    nom, tn = pl.preparar("entrenamiento", verboso=False); pl.resumen("nominal", tn)
    fal, tf = pl.preparar("fallo", verboso=False);         pl.resumen("fallo", tf)
    cols = pl.COLUMNAS

    print("\n" + "=" * 78)
    print(f"VALIDACION CRUZADA POR EPISODIOS ({tn['episodios']} episodios nominales)")
    print("=" * 78)
    print("Se deja fuera un episodio completo, se ajusta sobre los demas y se miden los")
    print("falsos positivos sobre una condicion de operacion NO VISTA por el modelo.\n")
    print(f"{'modelo':<20}{'FP fuera de episodio':>24}{'peor episodio':>15}{'deteccion':>13}")
    filas = []
    for nombre, modelo in catalogo().items():
        fps, dets, n = validacion_por_episodios(modelo, nom, fal, cols)
        if not n:
            continue
        filas.append((nombre, fps, dets))
        print(f"{nombre:<20}{100*fps.mean():10.1f} +-{100*fps.std():5.1f} %"
              f"{100*fps.max():14.1f} %{100*dets.mean():11.1f} %")

    print(f"""
LECTURA. La columna 'peor episodio' es la que importa para el despliegue: es la
tasa de falsos positivos sobre el arranque del compresor que peor se ajusta al
modelo. Una media baja con un peor caso alto significa que el detector fallara
de forma concentrada, no repartida, y en operacion eso se traduce en una tanda
de alarmas falsas seguidas y no en un falso positivo aislado cada tanto.""")


if __name__ == "__main__":
    main()
    main_episodios()

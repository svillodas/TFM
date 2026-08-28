#!/usr/bin/env python3
"""
Pipeline de datos: carga, limpieza, segmentacion y extraccion de caracteristicas
derivadas. Es la unica via por la que los scripts de analisis leen los CSV, para
que las decisiones de limpieza sean las mismas en todos ellos.

Cada decision de este modulo esta justificada en README.md. Las que tienen
consecuencias silenciosas si se revierten llevan el motivo escrito al lado.
"""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
DATA = RAIZ / "server" / "data"

# --- Contrato con el firmware -------------------------------------------------
# Unica version admisible. fw-31col y fw-33col publican DEFINICIONES DISTINTAS
# de rms/peak/kurt (sin filtrar) y un solo pico espectral: no son comparables.
FIRMWARE = "fw-46col"

# Sufijo del fichero y numero de columnas de cada canal. Se declaran juntos y de
# forma POSITIVA —qué sufijo tiene cada canal— y no por descarte. El criterio
# anterior era "todo lo que no acabe en -vibration.csv es canal lento", y al
# aparecer un tercer canal (-status.csv, el veredicto del detector embarcado) el
# cargador intento leerlo como canal lento y aborto por numero de columnas. Un
# criterio por descarte se rompe con cada canal nuevo; uno explicito no.
CANALES = {
    "rafaga": ("-vibration.csv", 46),
    "lento":  (".csv", 10),
    "estado": ("-status.csv", 8),
}
SUFIJOS_CONOCIDOS = tuple(suf for suf, _ in CANALES.values() if suf != ".csv")

# --- Valores centinela del firmware (ver docs/DATA_SCHEMA.md) -----------------
TEMP_AUSENTE = -127.0        # DS18B20 no responde
MOTOR_TEMP_MIN = 0.0         # el MPU devuelve 0 si la lectura fallo

# --- Filtro de calidad --------------------------------------------------------
# Solo contadores POR RAFAGA. bad_frames y los total_* son acumulados desde el
# arranque del nodo: exigirles cero descarta el 100 % de las observaciones.
#
# ESTE FILTRO NO ES OPCIONAL, y el motivo no es la limpieza sino que los
# reintentos del bus I2C FABRICAN LA FIRMA DEL FALLO sobre un activo sano. En el
# nodo A, que esta en estado nominal, la mediana del numero de picos espectrales
# significativos pasa de 1 con pocos reintentos a 3 con mas de diez, y la
# frecuencia fundamental estimada se derrumba de 49,15 Hz a 20 Hz. Una muestra
# corrupta inyecta ruido de banda ancha y varios coeficientes del espectro
# superan el umbral de significacion.
#
# Fraccion de rafagas del activo NOMINAL con picos espurios, medida sobre 19 h:
#
#     retries      n   con n_picos > 1
#     0          261    0,4 %
#     1-3        206    0,5 %
#     4-5         53    8   %
#     6-10        48   31   %
#     11-20       46   93   %
#     >20         69   94   %
#
# El corte en 3 conserva 467 rafagas con un 0,4 % de espurias, la misma tasa que
# exigir cero reintentos pero con un 79 % mas de datos. El corte anterior, 5,
# admitia un 1,2 %.
#
# Consecuencia para el despliegue en el nodo: el ESP32 debe NEGARSE A EMITIR
# VEREDICTO sobre una rafaga con mas de 3 reintentos, en lugar de juzgarla.
MAX_RETRIES = 3
MAX_CONT_REJECTS = 2
KURT_RANGO = (1.0, 20.0)     # kurtosis fisicamente posible; 1,5 es una senoide

# --- Segmentacion marcha / parada --------------------------------------------
# El valor eficaz filtrado es bimodal, pero el nivel de cada modo es PROPIO DE
# CADA MAQUINA: el nodo A da 0,024 parado y 1,61 en marcha, mientras el nodo B
# da 0,022 y 0,158. Un umbral absoluto no sirve para las dos.
#
# El primero que se probo, 0,05, se fijo con 1,88 h de datos del nodo A y era
# INCORRECTO: caia dentro del grupo de parado, cuyo extremo superior llega a
# 0,06. Con 19 h se ve que el valle real del nodo A esta entre 0,06 y 0,30, y
# aquel umbral producia episodios espurios de una sola rafaga.
#
# El umbral se deriva por tanto de los propios datos, separando los dos modos
# del logaritmo del valor eficaz. No tiene hiperparametros.
RMS_MARCHA = None      # se calcula; ver umbral_marcha()
# Separacion minima entre los dos modos para aceptar que la distribucion es
# bimodal. Por debajo se entiende que no hay poblacion de parada en el conjunto
# y se considera todo en marcha, en lugar de partir en dos el grupo de marcha.
RATIO_MODOS_MIN = 3.0
# Amplitud minima de un pico espectral para considerarlo, relativa a la del
# mayor de los tres. Por debajo es ruido y no una componente de la maquina.
AMP_MIN_RELATIVA = 0.20
# Un episodio es un tramo contiguo de rafagas en marcha. Con la cadencia de 30 s,
# un hueco mayor que este corta el episodio aunque el compresor no se detuviese:
# un hueco asi significa que el nodo dejo de publicar.
HUECO_MAX_S = 180


# =============================================================================
# Carga
# =============================================================================

def _leer_csv(ruta, n_esperado):
    """Lee un CSV del registrador retirando los bytes nulos.

    Los NUL son huecos del sistema de ficheros por parada sucia del
    concentrador: bloques reservados cuyos datos nunca se escribieron. Se
    retiran al leer y no a mitad del entrenamiento.
    """
    crudo = ruta.read_bytes()
    nul = crudo.count(b"\x00")
    texto = crudo.replace(b"\x00", b"").decode("utf-8", errors="replace")
    cabecera = texto.split("\n", 1)[0].split(",")
    if len(cabecera) != n_esperado:
        sys.exit(f"ABORTA: {ruta} tiene {len(cabecera)} columnas y no {n_esperado}.\n"
                 f"        Su cabecera no corresponde a {FIRMWARE}. Leerla con las\n"
                 f"        caracteristicas de este pipeline daria valores sin sentido:\n"
                 f"        ya ocurrio una vez y devolvio rms_x = 7 sin protestar.")
    d = pd.read_csv(io.StringIO(texto))
    d.attrs["nul"] = nul
    return d


def series(uso, canal="rafaga"):
    """Rutas del manifiesto con el uso y canal indicados, filtradas por firmware."""
    man = json.loads((DATA / "manifiesto.json").read_text(encoding="utf-8"))
    todas = [s["ruta"] for s in man["series"]
             if s["uso"] == uso and canal in s["canales"]]
    # El candado de firmware se aplica SOLO al canal de rafaga. Es donde las
    # versiones anteriores publican definiciones distintas de la misma
    # caracteristica (estadisticos sin filtrar, un unico pico espectral) y
    # mezclarlas no significa nada. El canal lento publica las mismas 10
    # columnas en todas las versiones, de modo que excluirlo descartaria en
    # silencio 20,6 h de datos termicos validos que el manifiesto clasifica
    # expresamente como aptos.
    if canal != "rafaga":
        return todas
    admitidas = [r for r in todas if FIRMWARE in r]
    for r in sorted(set(todas) - set(admitidas)):
        print(f"    omitida {r} (uso='{uso}', canal de rafaga): no es {FIRMWARE}")
    return admitidas


def cargar(uso, canal="rafaga", verboso=True):
    """Carga y concatena las series de un uso. Devuelve el DataFrame crudo."""
    if canal not in CANALES:
        sys.exit(f"ABORTA: canal '{canal}' desconocido. Conocidos: {list(CANALES)}")
    sufijo, n_col = CANALES[canal]
    marcos = []
    for r in series(uso, canal):
        for csv in sorted((DATA / r).glob("*.csv")):
            if sufijo == ".csv":
                # El canal lento no tiene sufijo propio, de modo que es el unico
                # que hay que identificar por exclusion de los demas.
                if csv.name.endswith(SUFIJOS_CONOCIDOS):
                    continue
            elif not csv.name.endswith(sufijo):
                continue
            d = _leer_csv(csv, n_col)
            d["_serie"] = r
            if verboso:
                nul = d.attrs.get("nul", 0)
                print(f"    {csv.relative_to(DATA)}: {len(d)} filas"
                      + (f", {nul} bytes NUL retirados" if nul else ""))
            marcos.append(d)
    if not marcos:
        sys.exit(f"ABORTA: ninguna serie con uso='{uso}' y canal='{canal}' en el manifiesto.")
    d = pd.concat(marcos, ignore_index=True)
    d["t"] = pd.to_datetime(d.ts, format="mixed")
    return d.sort_values("t").reset_index(drop=True)


# =============================================================================
# Limpieza
# =============================================================================

def limpiar(d, informe=None):
    """Retira centinelas y duplicados. NO filtra por calidad: eso va aparte,
    porque el umbral de calidad es una decision del analisis y su fraccion
    descartada forma parte del resultado que hay que declarar."""
    n0 = len(d)
    pasos = []

    # Duplicados por marca de tiempo: aparecen al consolidar fragmentos.
    d = d.drop_duplicates(subset="ts", keep="last")
    pasos.append(("duplicados de ts", n0 - len(d)))

    # Centinelas. Un solo -127 arrastra la media termica de la jornada entera.
    n = len(d)
    if "tempExt" in d:
        d = d[d.tempExt != TEMP_AUSENTE]
        pasos.append(("tempExt = -127 (DS18B20 sin respuesta)", n - len(d)))
    n = len(d)
    if "motorTemp" in d:
        d = d[d.motorTemp > MOTOR_TEMP_MIN]
        pasos.append(("motorTemp = 0 (lectura del MPU fallida)", n - len(d)))

    # Un retroceso en un contador acumulado indica reinicio del nodo, no error
    # de lectura. No se descarta la fila: se marca, porque el reinicio rompe la
    # continuidad temporal y eso importa al segmentar episodios.
    if "total_retries" in d:
        d = d.copy()
        d["reinicio"] = d.total_retries.diff() < 0
        pasos.append(("reinicios del nodo detectados", int(d.reinicio.sum())))

    if informe is not None:
        informe.extend(pasos)
    return d.reset_index(drop=True)


def calidad(d):
    """Mascara booleana de rafagas cuya medida es fiable."""
    return ((d.retries <= MAX_RETRIES)
            & (d.cont_rejects <= MAX_CONT_REJECTS)
            & d.kurt_x.between(*KURT_RANGO))


def umbral_marcha(v):
    """Umbral marcha/parada derivado de los datos, en el valle de la bimodal.

    Separa el logaritmo del valor eficaz en dos grupos y devuelve la media
    geometrica de sus centros. Sobre el logaritmo y no sobre el valor directo
    porque los dos modos difieren en casi dos ordenes de magnitud, y en escala
    lineal el grupo de marcha arrastraria el corte.

    Devuelve (umbral, bimodal). Si los dos modos no estan separados al menos
    RATIO_MODOS_MIN, no hay poblacion de parada que separar y se devuelve
    bimodal=False: partir en dos un grupo homogeneo de marcha inventaria una
    frontera donde no la hay.
    """
    v = np.asarray(v, dtype=float)
    v = v[v > 0]
    if len(v) < 10:
        return 0.0, False
    lv = np.log(v)
    c = np.array([lv.min(), lv.max()])
    for _ in range(100):                      # dos medias, hasta converger
        asig = np.abs(lv[:, None] - c).argmin(1)
        nuevo = np.array([lv[asig == k].mean() if (asig == k).any() else c[k]
                          for k in (0, 1)])
        if np.allclose(nuevo, c):
            break
        c = nuevo
    bajo, alto = float(np.exp(c.min())), float(np.exp(c.max()))
    if bajo <= 0 or alto / bajo < RATIO_MODOS_MIN:
        return 0.0, False
    return float(np.sqrt(bajo * alto)), True


def en_marcha(d, umbral=None):
    """Mascara booleana de rafagas capturadas con el compresor en marcha."""
    if umbral is None:
        umbral, _ = umbral_marcha(d.rms_x)
    return d.rms_x > umbral


def episodios(d, umbral=None):
    """Etiqueta cada rafaga en marcha con su episodio. -1 si esta parada.

    Es la unidad de observacion independiente. Las rafagas de un mismo episodio
    describen la misma condicion de operacion y estan fuertemente
    correlacionadas: contarlas como observaciones independientes sobreestima el
    tamano de muestra en un orden de magnitud.
    """
    d = d.copy()
    marcha = en_marcha(d, umbral)
    hueco = d.t.diff().dt.total_seconds() > HUECO_MAX_S
    # Deliberadamente NO se corta por reinicio del nodo. Un reinicio interrumpe
    # la OBSERVACION, no la marcha del compresor: contarlo como episodio nuevo
    # presenta como independiente lo que es el mismo estado de la maquina. Si el
    # reinicio dejo un hueco real en los datos, el criterio de hueco ya lo corta.
    corte = (marcha != marcha.shift()) | hueco
    grupo = corte.cumsum()
    d["episodio"] = np.where(marcha, grupo, -1)
    # Renumera los episodios de marcha de 0 en adelante.
    vistos = {g: i for i, g in enumerate(sorted(d.loc[marcha, "episodio"].unique()))}
    d["episodio"] = d.episodio.map(lambda g: vistos.get(g, -1))
    return d


# =============================================================================
# Caracteristicas
# =============================================================================

# Adimensionales por construccion. El motivo no es estetico: el nivel absoluto
# de vibracion difiere en un factor 5,5 entre los dos activos, de modo que
# cualquier caracteristica con unidades separa las dos MAQUINAS antes de separar
# el estado de una de ellas. Un detector sobre rms/peak/kurt alcanza el 99,8 %
# de deteccion sin haber visto la firma del fallo: es una metrica excelente
# obtenida sobre el atributo equivocado.
CARACTERISTICAS = {
    "kurt_x":  "Kurtosis del eje X. Adimensional por definicion. 1,5 = senoide pura, 3 = gaussiana.",
    "crest":   "Factor de cresta, peak/rms. Forma de onda independiente de la amplitud.",
    "r2":      "Relacion del pico de frecuencia intermedia con el de frecuencia mas baja.",
    "r3":      "Relacion del pico de frecuencia mas alta con el de frecuencia mas baja.",
    "q2":      "Amplitud del pico intermedio relativa a la del pico de frecuencia mas baja.",
    "q3":      "Amplitud del pico mas alto relativa a la del pico de frecuencia mas baja.",
    "n_picos": "Numero de picos espectrales con amplitud significativa, de 1 a 3. Un activo sano esta dominado por su fundamental; los armonicos del fallo anaden picos.",
    "rms_x_rel": "Valor eficaz relativo a la mediana del PROPIO activo en marcha. Recupera la sensibilidad a la amplitud sin perder la independencia de maquina.",
    "adom_x_rel": "Amplitud dominante relativa a la mediana del propio activo.",
    "dif_rel": "Diferencial termico motor-ambiente, relativo a la mediana del propio activo. Detecta lo que la vibracion no ve: una obstruccion de ventilacion no altera la firma vibratoria pero eleva la temperatura.",
    "grad_motor": "Pendiente de la temperatura del motor en el minuto anterior, en C/min. Distingue el arranque en frio del regimen estacionario.",
    "aud_b0":  "Fraccion de energia acustica en 0-250 Hz. Ya normalizada por el firmware.",
    "aud_b1":  "Fraccion de energia acustica en 250-1000 Hz.",
    "aud_b2":  "Fraccion de energia acustica en 1-2 kHz.",
    # aud_b3 NO se incluye, y el motivo es de construccion y no de rendimiento:
    # el firmware normaliza las cuatro bandas para que sumen 1, de modo que
    # cualquiera de ellas queda determinada por las otras tres. Es una
    # dependencia lineal EXACTA —medida: suman 1,000003 +- 5,9e-5— que vuelve
    # singular la matriz de covarianza. Con las cuatro, su numero de condicion
    # es de 3,9e7 y la forma cuadratica de la envolvente sufre una cancelacion
    # de un factor 45 000: en simple precision el resultado se desvia en 37
    # unidades sobre puntuaciones del orden de 19 000. Sin aud_b3, la condicion
    # baja a 6,5e4.
    #
    # No se pierde informacion: aud_b3 = 1 - aud_b0 - aud_b1 - aud_b2.
}
COLUMNAS = list(CARACTERISTICAS)

# Con unidades. Se calculan para poder DEMOSTRAR el sesgo, no para entrenar.
DIMENSIONALES = ["rms_x", "peak_x", "adom_x"]


def caracteristicas(d):
    """Deriva las caracteristicas adimensionales. Requiere el canal de rafaga.

    Los tres picos se REORDENAN POR FRECUENCIA antes de calcular los cocientes.
    El firmware los publica ordenados por amplitud, y eso hace que los cocientes
    no sean estables: en 60 de 676 rafagas del activo con fallo el armonico del
    fallo supera a la fundamental del giro por un 2 % (0,2056 frente a 0,2016) y
    pasa a ocupar la posicion de pico dominante. Con la definicion por amplitud,
    f2/fdom valia 9,0 en unas rafagas y 0,111 en otras describiendo el MISMO
    fenomeno: el coeficiente de variacion pasaba del 1,9 % al 30,9 % y la
    frecuencia dominante aparentaba un CV del 133 %.

    Ordenar por frecuencia es lo que hace la caracteristica invariante a ese
    reordenamiento. El pico de frecuencia mas baja es la fundamental del giro,
    y los otros dos se expresan respecto a ella.
    """
    d = d.copy()
    d["crest"] = d.peak_x / d.rms_x

    f = d[["fdom_x", "f2_x", "f3_x"]].to_numpy(dtype=float)
    a = d[["adom_x", "a2_x", "a3_x"]].to_numpy(dtype=float)
    # Se descartan los picos cuya amplitud es despreciable frente a la mayor:
    # son ruido espectral, y con frecuencia caen por DEBAJO de la fundamental,
    # con lo que el criterio de frecuencia mas baja los tomaria por fundamental.
    # Sin este filtro el nominal daba a q2 un CV del 219 %, porque el
    # denominador era la amplitud de un pico de ruido.
    # La comparacion se hace en PRECISION SIMPLE a proposito, no en doble.
    # El firmware evalua en float y este modulo es su implementacion de
    # referencia: si ambos no comparan igual, los casos que caen justo en la
    # frontera se resuelven de forma distinta. Ocurre: en 1 de 1161 rafagas la
    # amplitud del tercer pico vale 0,044700 y el umbral 0,2 x 0,2235 =
    # 0,0447000000000000004, de modo que en doble queda fuera y en simple
    # dentro. Comparando en simple, el veredicto del nodo y el del analisis
    # coinciden bit a bit.
    a32 = a.astype(np.float32)
    umbral32 = (np.float32(AMP_MIN_RELATIVA) *
                a32.max(axis=1, keepdims=True)).astype(np.float32)
    significativo = a32 >= umbral32
    f_eval = np.where(significativo, f, np.inf)        # los no significativos al final
    # Ordenacion ESTABLE: cuando dos picos son ambos insignificantes reciben la
    # misma clave y su orden relativo debe ser el original, no arbitrario. El
    # quicksort que numpy usa por omision no lo garantiza, y el firmware ordena
    # por insercion, que si es estable.
    orden = np.argsort(f_eval, axis=1, kind="stable")   # ascendente en frecuencia
    f = np.take_along_axis(f, orden, axis=1)
    a = np.take_along_axis(a, orden, axis=1)
    d["f0"] = f[:, 0]                                  # fundamental del giro
    d["a0"] = a[:, 0]
    d["n_picos"] = significativo.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        d["r2"] = f[:, 1] / f[:, 0]
        d["r3"] = f[:, 2] / f[:, 0]
        d["q2"] = a[:, 1] / a[:, 0]
        d["q3"] = a[:, 2] / a[:, 0]
    # Una fundamental nula o un pico ausente producen inf/nan: se descartan,
    # porque un cociente sin denominador no es una observacion.
    d["n_picos"] = d.n_picos.astype(float)
    d = d.replace([np.inf, -np.inf], np.nan)
    return d


# Ventana alrededor de la marca de tiempo de la rafaga en la que se promedian
# las tramas del canal lento. La rafaga dura ~1 s y el canal lento publica a
# 1 Hz, de modo que 15 s recogen unas 30 tramas: suficiente para promediar el
# ruido de cuantificacion del sensor sin salirse del estado termico del instante.
VENTANA_LENTO_S = 15
# Intervalo sobre el que se estima la pendiente termica.
VENTANA_GRADIENTE_S = 60


def unir_termico(rafagas, lento):
    """Anade al canal de rafaga el estado termico del instante de captura.

    Los dos canales viven en ficheros distintos y a cadencias distintas, de modo
    que hay que unirlos por marca de tiempo. Sin esta union el detector ignora
    por completo la temperatura, que es la unica modalidad capaz de ver un fallo
    que no altere la vibracion.

    El diferencial se normaliza por la mediana del PROPIO activo, por el mismo
    motivo que las amplitudes: la temperatura absoluta depende del ambiente de
    la habitacion y no del estado de la maquina.
    """
    lento = lento.sort_values("t")
    # Segundos desde la epoca, calculados por diferencia y NO con astype("int64").
    # La resolucion interna de pandas cambio a microsegundos en la version 3, de
    # modo que astype("int64")//10**9 devolvia miles de segundos: las marcas de
    # tiempo se colapsaban y 24753 de 24780 quedaban duplicadas, con lo que la
    # union termica no unia nada y el gradiente salia en 19 C/min sobre un activo
    # cuya temperatura varia 7 C en total. La diferencia frente a un instante
    # explicito es independiente de la unidad interna.
    EPOCA = pd.Timestamp("1970-01-01", tz="UTC")
    ts = (lento.t - EPOCA).dt.total_seconds().to_numpy()
    dif = (lento.motorTemp - lento.tempExt).to_numpy()
    mot = lento.motorTemp.to_numpy()

    d = rafagas.copy()
    objetivo = (d.t - EPOCA).dt.total_seconds().to_numpy()
    dif_v, grad_v = np.full(len(d), np.nan), np.full(len(d), np.nan)
    for i, t0 in enumerate(objetivo):
        cerca = (ts >= t0 - VENTANA_LENTO_S) & (ts <= t0 + VENTANA_LENTO_S)
        if cerca.any():
            dif_v[i] = np.nanmean(dif[cerca])
        antes = (ts >= t0 - VENTANA_GRADIENTE_S) & (ts <= t0)
        if antes.sum() >= 5:
            x = (ts[antes] - t0).astype(float)
            y = mot[antes]
            # Pendiente por minimos cuadrados a mano, en lugar de polyfit: hay
            # que descartar los NaN antes de resolver y polyfit no lo hace, con
            # lo que la descomposicion no converge y aborta el pipeline entero.
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() >= 5:
                x, y = x[ok], y[ok]
                vx = x.var()
                if vx > 0:
                    grad_v[i] = (np.cov(x, y, bias=True)[0, 1] / vx) * 60.0
    d["dif_termico"] = dif_v
    d["grad_motor"] = grad_v
    m = np.nanmedian(dif_v)
    d["dif_rel"] = dif_v / m if m and not np.isnan(m) else np.nan
    return d


# t_marcha se calcula pero NO se usa como caracteristica del detector, y conviene
# saber por que: separa los dos activos (12,5 min frente a 169,9 de mediana) pero
# lo hace por la DURACION DE SUS EPISODIOS, que es una consecuencia de que el
# activo con fallo no llegue a detenerse. Es identidad de maquina disfrazada de
# diagnostico, el mismo error que las caracteristicas con unidades. Se conserva
# para el analisis descriptivo de los ciclos.
def tiempo_en_marcha(d):
    """Minutos desde el inicio del episodio de marcha al que pertenece la rafaga."""
    d = d.copy()
    d["t_marcha"] = np.nan
    for e, g in d[d.episodio >= 0].groupby("episodio"):
        d.loc[g.index, "t_marcha"] = (g.t - g.t.min()).dt.total_seconds() / 60.0
    return d


def relativas(d):
    """Normaliza las magnitudes con unidades por la mediana del PROPIO activo.

    Es la unica via para conservar sensibilidad a la AMPLITUD sin reintroducir
    el sesgo entre maquinas. Las caracteristicas puramente adimensionales son
    ciegas por construccion a un fallo que solo cambia el nivel —un
    desequilibrio de masa, por ejemplo, sube la amplitud a la frecuencia de giro
    sin anadir componentes nuevas— y esa ceguera es el precio de la
    independencia de maquina. Dividir por la mediana propia lo evita: la
    caracteristica es adimensional en la forma y especifica en el valor.

    CONSECUENCIA PARA EL DESPLIEGUE: el nodo necesita conocer la mediana de su
    propio activo, de modo que debe aprenderla durante una fase de referencia
    antes de poder emitir veredicto. No es una caracteristica calculable en la
    primera rafaga.

    Debe llamarse DESPUES de filtrar por marcha: la mediana ha de ser la del
    activo en funcionamiento, no la de una mezcla con el compresor detenido.
    """
    d = d.copy()
    for c in ("rms_x", "adom_x"):
        m = d[c].median()
        d[c + "_rel"] = d[c] / m if m else np.nan
    return d


def preparar(uso, verboso=True):
    """Carga -> limpia -> caracteristicas -> filtra calidad y marcha.

    Devuelve (DataFrame listo, dict con la trazabilidad del descarte).
    """
    if verboso:
        print(f"  uso='{uso}':")
    crudo = cargar(uso, verboso=verboso)
    traza = {"crudas": len(crudo), "pasos": []}
    d = limpiar(crudo, informe=traza["pasos"])
    d = caracteristicas(d)
    umbral, bimodal = umbral_marcha(d.rms_x)
    traza["umbral_marcha"], traza["bimodal"] = umbral, bimodal
    d = episodios(d, umbral)

    m_cal, m_mar = calidad(d), en_marcha(d, umbral)
    traza["calidad_ok"] = int(m_cal.sum())
    traza["en_marcha"] = int(m_mar.sum())
    d = d[m_cal & m_mar].reset_index(drop=True)
    d = relativas(d)                      # despues de filtrar, no antes
    d = tiempo_en_marcha(d)
    lento = limpiar(cargar(uso, canal="lento", verboso=False))
    d = unir_termico(d, lento)
    antes = len(d)
    d = d.dropna(subset=COLUMNAS).reset_index(drop=True)
    traza["sin_termico"] = antes - len(d)
    traza["utiles"] = len(d)
    if traza.get("sin_termico"):
        print(f"      -{traza['sin_termico']:5d}  sin trama del canal lento en la ventana")
    traza["episodios"] = int(d.episodio.nunique())
    traza["detalle_episodios"] = sorted(d.groupby("episodio"), key=lambda kv: kv[0])
    horas = (crudo.t.max() - crudo.t.min()).total_seconds() / 3600
    traza["horas"] = horas
    traza["utiles_hora"] = len(d) / horas if horas else 0.0
    return d, traza


def resumen(nombre, traza):
    p = traza
    print(f"  {nombre}: {p['crudas']} crudas en {p['horas']:.2f} h")
    if p["bimodal"]:
        print(f"      umbral marcha/parada derivado de los datos: "
              f"{p['umbral_marcha']:.4f} m/s2")
    else:
        print(f"      AVISO: la distribucion del valor eficaz no es bimodal. No hay "
              f"poblacion de parada\n              en el conjunto; se considera todo en marcha.")
    for etiqueta, n in p["pasos"]:
        if n:
            print(f"      -{n:5d}  {etiqueta}")
    print(f"      calidad ok {p['calidad_ok']:5d} ({100*p['calidad_ok']/p['crudas']:3.0f} %)"
          f" | en marcha {p['en_marcha']:5d} ({100*p['en_marcha']/p['crudas']:3.0f} %)")
    print(f"      UTILES     {p['utiles']:5d} ({100*p['utiles']/p['crudas']:3.0f} %)"
          f" = {p['utiles_hora']:.0f}/h  en {p['episodios']} episodios de marcha")
    for e, g in p["detalle_episodios"]:
        print(f"          episodio {e}: {len(g):4d} rafagas, "
              f"{(g.t.max()-g.t.min()).total_seconds()/60:6.1f} min, "
              f"{g.t.min().strftime('%H:%M')}-{g.t.max().strftime('%H:%M')}")


if __name__ == "__main__":
    print("Pipeline de datos\n")
    for uso in ("entrenamiento", "fallo"):
        d, traza = preparar(uso)
        resumen(uso, traza)
        print()

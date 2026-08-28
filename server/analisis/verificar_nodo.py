#!/usr/bin/env python3
"""
Evalua una captura con el detector embarcado corriendo: ¿ha funcionado bien?

    .venv/bin/python server/analisis/verificar_nodo.py [serie]

Sin argumento usa nodo-a-nevera-buena/fw-46col.

Responde a tres preguntas, en orden de importancia:

  1. ¿COINCIDE EL NODO CON EL ANALISIS? Es la verificacion fuerte, y es posible
     porque el nodo publica las caracteristicas y el veredicto en el mismo
     instante: se recalcula la puntuacion en el PC a partir de la rafaga que el
     propio nodo midio y se compara con la que el nodo reporto. Misma rafaga,
     dos implementaciones. Si coinciden, la afirmacion de que el diagnostico se
     ejecuta en el nodo esta medida y no supuesta.

  2. ¿CUANTOS AVISOS FALSOS? Se cuenta notify=1, no health='anomaly'. La
     diferencia entre ambas magnitudes es de dos ordenes de magnitud: sobre el
     conjunto de referencia el 5,1 % de las rafagas se marcan como anomalas y se
     emiten CERO avisos, porque son aisladas y la histeresis exige tres
     consecutivas. La que estima la carga real de alarmas es notify.

  3. ¿CUANTO TARDA LA INFERENCIA? us_inference es la medida que respalda que el
     diagnostico cabe en el borde. Sin ella es una estimacion.
"""
import io
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import leer_cabecera as lc
import pipeline as pl

# Tolerancia al cruzar los dos canales por marca de tiempo. El nodo publica el
# veredicto inmediatamente despues de la rafaga, pero el registrador sella cada
# mensaje al recibirlo: la diferencia es de decimas de segundo, y un margen de
# unos pocos segundos absorbe cualquier retraso del enlace sin emparejar
# rafagas distintas, que estan separadas 30 s.
TOLERANCIA_S = 5.0


def leer(ruta):
    crudo = ruta.read_bytes().replace(b"\x00", b"")
    d = pd.read_csv(io.StringIO(crudo.decode("utf-8", errors="replace")))
    d["t"] = pd.to_datetime(d.ts, format="mixed")
    return d.sort_values("t").reset_index(drop=True)


def main():
    serie = sys.argv[1] if len(sys.argv) > 1 else "nodo-a-nevera-buena/fw-46col"
    # La raiz se puede redirigir con DATA_ROOT. Existe para poder ejercitar este
    # script sobre datos de prueba sin escribir en server/data, que contiene
    # medidas de laboratorio no reproducibles.
    raiz = Path(os.environ.get("DATA_ROOT",
                Path(__file__).resolve().parents[2] / "server" / "data"))
    base = raiz / serie

    estados = sorted(base.glob("*-status.csv"))
    if not estados:
        sys.exit(f"No hay ningun *-status.csv en {serie}.\n"
                 f"  Si acabas de flashear, trae los datos primero:\n"
                 f"    ./server/traer-datos.sh 10.42.0.1 iiot-c {serie}\n"
                 f"  Si ya los trajiste y no hay fichero, el registrador no\n"
                 f"  estaba suscrito a fridge/status: comprueba con\n"
                 f"    ./server/provision-pi.sh comprobar")

    est = pd.concat([leer(f) for f in estados], ignore_index=True)
    est = est.drop_duplicates(subset="ts").sort_values("t").reset_index(drop=True)
    horas = (est.t.max() - est.t.min()).total_seconds() / 3600

    print("=" * 74)
    print(f"CAPTURA CON EL DETECTOR EMBARCADO — {serie}")
    print("=" * 74)
    print(f"  {len(est)} veredictos en {horas:.2f} h")
    print(f"  de {est.t.min().strftime('%d %b %H:%M')} "
          f"a {est.t.max().strftime('%d %b %H:%M')}")

    # --- 2. Avisos ------------------------------------------------------
    print("\n" + "-" * 74)
    print("AVISOS EMITIDOS")
    print("-" * 74)
    for etiqueta in ("nominal", "anomaly", "not_evaluable"):
        n = int((est.health == etiqueta).sum())
        print(f"  health = {etiqueta:15s} {n:5d}  ({100*n/len(est):5.1f} %)")
    evaluables = int((est.health != "not_evaluable").sum())
    avisos = int((est.notify == 1).sum()) if "notify" in est else 0
    print(f"\n  rafagas evaluables (compresor en marcha, bus sano): {evaluables}")
    if evaluables:
        anom = int((est.health == "anomaly").sum())
        print(f"  marcadas como anomalas: {anom} = {100*anom/evaluables:.1f} % de las evaluables")
    print(f"  AVISOS EMITIDOS (notify=1): {avisos}")
    if avisos == 0:
        print("    -> ningun aviso. Si la nevera estaba sana, es el resultado esperado:")
        print("       la histeresis absorbe las rafagas anomalas aisladas.")
    else:
        print("    -> instantes de los avisos:")
        for t in est.loc[est.notify == 1, "t"]:
            print(f"       {t.strftime('%d %b %H:%M:%S')}")
    if "streak" in est:
        print(f"  racha maxima de anomalas consecutivas: {int(est.streak.max())}")

    # --- 3. Coste de la inferencia -------------------------------------
    if "us_inference" in est:
        u = pd.to_numeric(est.us_inference, errors="coerce").dropna()
        u = u[u > 0]
        if len(u):
            print("\n" + "-" * 74)
            print("COSTE DE LA INFERENCIA EN EL NODO")
            print("-" * 74)
            print(f"  mediana {u.median():8.0f} us     p99 {u.quantile(.99):8.0f} us"
                  f"     max {u.max():8.0f} us")
            print(f"  frente a una rafaga cada 30 s: {100*u.median()/30e6:.5f} % del ciclo")

    # --- 1. La verificacion fuerte -------------------------------------
    rafagas = sorted(base.glob("*-vibration.csv"))
    if not rafagas:
        print("\n  (sin fichero de rafaga: no se puede contrastar con el analisis)")
        return
    raf = pd.concat([leer(f) for f in rafagas], ignore_index=True)
    raf = raf.drop_duplicates(subset="ts").sort_values("t").reset_index(drop=True)

    print("\n" + "-" * 74)
    print("¿COINCIDE EL NODO CON EL ANALISIS EN EL PC?")
    print("-" * 74)

    # EL MODELO SE LEE DE LA CABECERA GENERADA, no se reajusta con los datos de
    # hoy. Es la correccion de un defecto de la primera version de este script:
    # reajustarlo introducia una diferencia que no era un defecto de
    # implementacion sino OTRO MODELO. Cada vez que llegan rafagas nuevas cambian
    # las medianas, el conjunto de ajuste y el umbral, y la comparacion deja de
    # medir lo que pretende. Con 20 rafagas producia 2 discrepancias falsas.
    try:
        mod = lc.leer()
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"  no se puede leer el modelo del firmware: {e}")
        return
    print(f"  modelo leido de modelo_referencia.h, generada el {mod['generada']}")
    if mod["rafagas"]:
        print(f"    ajustado sobre {mod['rafagas'][1]} rafagas utilizables")
    cols = pl.COLUMNAS
    if len(mod["media"]) != len(cols):
        print(f"  AVISO: la cabecera tiene {len(mod['media'])} caracteristicas y el")
        print(f"  pipeline {len(cols)}. El firmware es de otra version del analisis:")
        print(f"  vuelve a ejecutar exportar_modelo.py y recompila.")
        return

    # Las rafagas de esta captura, por el pipeline, y normalizadas con las
    # medianas Y el umbral de marcha QUE LLEVA EL NODO.
    d = pl.caracteristicas(pl.limpiar(raf))
    d = pl.episodios(d, mod["umbral_marcha"])
    apta = (pl.calidad(d) & (d.rms_x > mod["umbral_marcha"]))
    d = d[apta].reset_index(drop=True)
    if not len(d):
        print("  ninguna rafaga de esta captura pasa el filtro: nada que contrastar")
        return
    d["rms_x_rel"] = d.rms_x / mod["mediana_rms"]
    d["adom_x_rel"] = d.adom_x / mod["mediana_adom"]
    d = pl.tiempo_en_marcha(d)
    lento = pl.limpiar(pl.cargar("entrenamiento", canal="lento", verboso=False))
    d = pl.unir_termico(d, lento)
    d["dif_rel"] = d.dif_termico / mod["mediana_dif"]
    d = d.dropna(subset=cols).reset_index(drop=True)

    Z = lc.normalizar(mod, d[cols].values)
    d = d.assign(lof_pc=lc.puntuar_lof(mod, Z))
    umbral = mod["lof_umbral"]

    # Cruce por marca de tiempo con tolerancia.
    est_ev = est[est.health != "not_evaluable"].copy()
    if "lof" not in est_ev or not len(est_ev):
        print("  la captura no trae veredictos evaluables con puntuacion")
        return
    emp = pd.merge_asof(d.sort_values("t"),
                        est_ev.sort_values("t")[["t", "lof", "health"]],
                        on="t", direction="nearest",
                        tolerance=pd.Timedelta(seconds=TOLERANCIA_S))
    emp = emp.dropna(subset=["lof"])
    print(f"  rafagas emparejadas con su veredicto: {len(emp)} de {len(d)}")
    if not len(emp):
        print("  ninguna pareja dentro de la tolerancia: revisa las marcas de tiempo")
        return
    err = (emp.lof_pc - emp.lof).abs()
    print(f"  diferencia en la puntuacion: mediana {err.median():.5f}  max {err.max():.5f}")
    coincide = ((emp.lof_pc < umbral) == (emp.health == "anomaly"))
    print(f"  veredictos coincidentes: {int(coincide.sum())} de {len(emp)}")

    if coincide.all():
        print("\n  -> EL NODO Y EL ANALISIS DAN EL MISMO VEREDICTO EN TODAS LAS RAFAGAS.")
        print("     La afirmacion de que el diagnostico se ejecuta en el nodo queda")
        print("     MEDIDA, no supuesta.")
    else:
        n = int((~coincide).sum())
        print(f"\n  -> {n} discrepancias. Se acota la causa:")
        # El gradiente termico es la unica caracteristica que el nodo y el PC no
        # calculan sobre los mismos datos: el nodo usa su ventana interna y el PC
        # reconstruye la pendiente desde el CSV del canal lento. Si al anularlo
        # las discrepancias desaparecen, la causa es esa y no un defecto.
        j = cols.index("grad_motor")
        Z2 = Z.copy()
        Z2[:, j] = 0.0
        alt = lc.puntuar_lof(mod, Z2)
        d2 = d.assign(lof_alt=alt)
        emp2 = pd.merge_asof(d2.sort_values("t"),
                             est_ev.sort_values("t")[["t", "lof", "health"]],
                             on="t", direction="nearest",
                             tolerance=pd.Timedelta(seconds=TOLERANCIA_S)).dropna(subset=["lof"])
        c2 = ((emp2.lof_alt < umbral) == (emp2.health == "anomaly"))
        print(f"     anulando grad_motor: {int(c2.sum())} de {len(emp2)} coincidirian")
        if int(c2.sum()) > int(coincide.sum()):
            print("     -> la causa es el GRADIENTE TERMICO. El nodo lo calcula con su")
            print("        ventana interna y el PC lo reconstruye desde el CSV del canal")
            print("        lento: no son las mismas muestras. No es un defecto del porte.")
        else:
            print("     -> no es el gradiente termico. Causas a descartar, en orden:")
            print("        1. La placa no lleva el modelo de esta cabecera: recompila.")
            print("        2. Un defecto real en la derivacion de caracteristicas:")
            print("           ejecuta device/test/test_detector.cpp.")

    print(f"\n  Umbral del nodo: {umbral:.6f}. Margen de las rafagas al umbral:")
    m_min = (emp.lof_pc - umbral).abs().min()
    print(f"  la mas proxima dista {m_min:.5f}, frente a un error de {err.max():.5f}.")
    if m_min > 5 * err.max():
        print("  El error es muy inferior al margen: ningun veredicto peligra.")
    else:
        print("  ATENCION: el error es del orden del margen. Con mas rafagas cerca")
        print("  del umbral podrian aparecer discrepancias por precision.")


if __name__ == "__main__":
    main()

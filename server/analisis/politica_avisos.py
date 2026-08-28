#!/usr/bin/env python3
"""
Evalua politicas de notificacion sobre los veredictos ya capturados.

    .venv/bin/python server/analisis/politica_avisos.py

POR QUE ESTE SCRIPT EXISTE. La histeresis es una politica de NOTIFICACION, no
una medida: no altera health, lof, env ni n_peaks, solo notify y streak. Y es
una funcion pura de la secuencia de veredictos, de modo que cualquier politica
alternativa se puede evaluar sobre los datos ya capturados.

De ello se sigue algo que conviene tener presente: **no hace falta reflashear el
nodo ni repetir ninguna campana** para decidir la politica. Y no conviene
hacerlo a mitad de una serie, porque la columna notify pasaria a significar algo
distinto antes y despues del cambio, introduciendo una discontinuidad en un
registro que hasta ahora es homogeneo.

QUE SE DESCARTO Y POR QUE. La primera propuesta fue exigir varias rafagas
NOMINALES consecutivas para rearmar, en lugar de una. Medido sobre los datos, no
reduce los avisos —14, 16 y 19 segun el valor, frente a 18 del actual— y el
motivo es que al no romper la racha con una nominal aislada, la racha de
anomalias se acumula mas rapido y el aviso se dispara antes. La propuesta era
incorrecta.

Lo que si funciona es un TIEMPO MINIMO ENTRE AVISOS, que es deduplicacion y no
insensibilizacion: la primera deteccion de un episodio nunca se pierde.
"""
import io
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
SERIE = "nodo-a-nevera-buena/fw-46col"
REQ_ANOMALAS = 3          # el valor que lleva el firmware


def cargar(serie=SERIE):
    d = RAIZ / "server" / "data" / serie
    ficheros = sorted(d.glob("*-status.csv"))
    if not ficheros:
        sys.exit(f"no hay *-status.csv en {serie}")
    e = pd.concat([pd.read_csv(io.StringIO(
            f.read_bytes().replace(b"\x00", b"").decode("utf-8", "replace")))
        for f in ficheros], ignore_index=True)
    e["t"] = pd.to_datetime(e.ts, format="mixed")
    return e.drop_duplicates("ts").sort_values("t").reset_index(drop=True)


def simular(e, req=REQ_ANOMALAS, silencio_min=0):
    """Reproduce Histeresis::actualizar con un silencio opcional entre avisos.

    Las rafagas no evaluables no cuentan ni rompen la racha, igual que en el
    firmware: no informan del estado de la maquina.
    """
    avisos, racha, notificado, ultimo = [], 0, False, None
    for i, r in e.iterrows():
        if r.health == "not_evaluable":
            continue
        if r.health == "anomaly":
            racha += 1
            if racha >= req and not notificado:
                if ultimo is None or (r.t - ultimo).total_seconds() / 60 >= silencio_min:
                    avisos.append(i)
                    ultimo = r.t
                    notificado = True
        else:
            racha, notificado = 0, False
    return avisos


def main():
    e = cargar()
    horas = (e.t.max() - e.t.min()).total_seconds() / 3600
    print(f"{len(e)} veredictos en {horas:.2f} h, hasta "
          f"{e.t.max().strftime('%d %b %H:%M')}\n")

    # Ventana del episodio de puerta abierta, para comprobar que ninguna
    # politica pierde la deteccion.
    EP = ("2026-08-28 12:00", "2026-08-28 13:45")
    print(f"{'silencio':>10}{'avisos':>9}{'del episodio':>14}   primera deteccion del episodio")
    for sil in (0, 10, 30, 60, 120):
        av = simular(e, silencio_min=sil)
        ep = [i for i in av if EP[0] <= str(e.t[i]) <= EP[1]]
        pri = e.t[ep[0]].strftime("%H:%M:%S") if ep else "—"
        print(f"{sil:>7} min{len(av):>9}{len(ep):>14}   {pri}"
              + ("   <- politica actual" if sil == 0 else ""))

    print("""
LECTURA. El tiempo minimo entre avisos reduce la duplicacion sin perder la
primera deteccion de ningun episodio: con 120 min los avisos bajan de 18 a 7 y
el episodio de puerta abierta produce uno solo en lugar de cuatro.

La contrapartida hay que declararla: un fallo que apareciera dentro de la
ventana de silencio quedaria sin notificar hasta que esta expirase. Con un ciclo
de trabajo de unos 85 min, un silencio de 120 min abarca mas de un ciclo
completo, de modo que el valor no es trasladable a otro activo sin repetir esta
medida sobre el suyo.

Es por tanto una decision de politica de operacion y no una eleccion tecnica: la
determina el coste relativo de una alarma repetida frente al de un retraso en la
notificacion.""")


if __name__ == "__main__":
    main()

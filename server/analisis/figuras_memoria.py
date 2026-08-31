#!/usr/bin/env python3
"""
Genera las figuras del capitulo de resultados a partir de los datos reales.

    .venv/bin/python server/analisis/figuras_memoria.py

Escribe en memoria_TFM/figuras/. Los ficheros son GENERADOS: no se editan a
mano, y regenerarlos tras una campana nueva es volver a ejecutar este script.

Todas las figuras salen de los CSV a traves de pipeline.py, de modo que
comparten las mismas decisiones de limpieza y segmentacion que el analisis. Una
figura construida con otro criterio mostraria algo distinto de lo que el texto
afirma, y esa discrepancia seria invisible.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import leer_cabecera as lc
import pipeline as pl

SALIDA = Path(__file__).resolve().parents[2] / "memoria_TFM" / "figuras"

# Estilo sobrio y legible en impresion: sin rejilla agresiva, tipografia con
# serifa para acompanar al cuerpo del documento.
plt.rcParams.update({
    "font.family": "serif", "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 200, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})
AZUL, ROJO, GRIS, VERDE = "#1f4e79", "#a52019", "#666666", "#2e7d32"


def preparar(uso):
    d, t = pl.preparar(uso, verboso=False)
    return d, t


def fig_armonicos(nom, fal):
    """Los cocientes de los picos con la fundamental del giro.

    Es el hallazgo principal y en forma de tabla no se aprecia: lo que importa
    es que el activo con fallo acumula masa de probabilidad EN LOS ENTEROS
    8, 9 y 10, mientras el de referencia lo hace en 2 y 3.
    """
    fig, ax = plt.subplots(figsize=(6.3, 2.6))
    bins = np.arange(0.5, 12.5, 0.1)
    for d, col, lab, alto in ((nom, AZUL, "Activo de referencia", True),
                              (fal, ROJO, "Activo con fallo", False)):
        v = pd.concat([d.r2, d.r3])
        v = v[(v > 0.5) & (v < 12)]
        ax.hist(v, bins=bins, color=col, alpha=0.75 if alto else 0.75,
                label=f"{lab} (n={len(v)})", density=True)
    for k in range(2, 11):
        ax.axvline(k, color=GRIS, lw=0.5, ls=":", zorder=0)
    ax.set_xlim(1, 11.5)
    ax.set_xticks(range(2, 12))
    ax.set_xlabel("Cociente con la frecuencia de giro")
    ax.set_ylabel("Densidad")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(SALIDA / "armonicos.pdf")
    plt.close(fig)
    return "armonicos.pdf"


def fig_bimodal(nom, mod):
    """La distribucion del valor eficaz y el umbral marcha/parada.

    Justifica visualmente por que el umbral se deriva de los datos: el valle
    entre los dos modos es amplio y su posicion depende de la maquina.
    """
    crudo = pl.limpiar(pl.cargar("entrenamiento", verboso=False))
    v = crudo.rms_x[crudo.rms_x > 0]
    fig, ax = plt.subplots(figsize=(6.3, 2.3))
    ax.hist(np.log10(v), bins=70, color=AZUL, alpha=0.85)
    u = mod["umbral_marcha"]
    ax.axvline(np.log10(u), color=ROJO, lw=1.6,
               label=f"Umbral derivado de los datos: {u:.3f} m/s$^2$")
    ax.axvline(np.log10(0.05), color=GRIS, lw=1.2, ls="--",
               label="Valor fijo inicial: 0,050 m/s$^2$")
    ax.set_xlabel(r"$\log_{10}$ del valor eficaz filtrado [m/s$^2$]")
    ax.set_ylabel("Ráfagas")
    ax.legend(frameon=False, fontsize=8, loc="upper center")
    fig.savefig(SALIDA / "bimodal.pdf")
    plt.close(fig)
    return "bimodal.pdf"


def fig_puerta(mod):
    """El episodio de puerta abierta, con las tres magnitudes alineadas.

    Es la figura que cuenta la campana entera: el transitorio acustico, la
    subida termica sostenida y el regreso al estado nominal. En tablas separadas
    esa secuencia no se percibe.
    """
    # El episodio es del 28 de agosto, posterior al corte de campana que
    # protege al conjunto de referencia del sesgo de espionaje. Se levanta el
    # corte de forma explicita: estas rafagas nunca entraron en el ajuste del
    # modelo, que es justamente lo que da valor a la figura. Sin esto la
    # funcion no encuentra ninguna fila y la figura deja de regenerarse.
    d = pl.caracteristicas(pl.limpiar(
        pl.cargar("entrenamiento", verboso=False, aplicar_corte=False)))
    d = pl.episodios(d, mod["umbral_marcha"])
    d = d[pl.calidad(d) & (d.rms_x > mod["umbral_marcha"])].copy()
    d["rms_x_rel"] = d.rms_x / mod["mediana_rms"]
    d["adom_x_rel"] = d.adom_x / mod["mediana_adom"]
    d = pl.tiempo_en_marcha(d)
    d = pl.unir_termico(d, pl.limpiar(pl.cargar("entrenamiento", canal="lento",
                                                verboso=False, aplicar_corte=False)))
    d["dif_rel"] = d.dif_termico / mod["mediana_dif"]
    d = d.dropna(subset=pl.COLUMNAS)
    d["lof"] = lc.puntuar_lof(mod, lc.normalizar(mod, d[pl.COLUMNAS].values))
    v = d[(d.t >= "2026-08-28 11:30") & (d.t <= "2026-08-28 15:00")]
    if not len(v):
        return None

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.3, 3.1), sharex=True,
                                 gridspec_kw={"height_ratios": [1.25, 1]})
    an = v.lof < mod["lof_umbral"]
    a1.plot(v.t, v.lof, color=GRIS, lw=0.7, zorder=1)
    a1.scatter(v.t[~an], v.lof[~an], s=9, color=AZUL, label="Nominal", zorder=2)
    a1.scatter(v.t[an], v.lof[an], s=9, color=ROJO, label="Anomalía", zorder=2)
    a1.axhline(mod["lof_umbral"], color=ROJO, ls="--", lw=1,
               label=f"Umbral: {mod['lof_umbral']:.3f}")
    a1.set_ylabel("Puntuación")
    a1.set_ylim(max(-4, v.lof.min() - 0.3), v.lof.max() + 0.3)
    a1.legend(frameon=False, fontsize=7.5, ncol=3, loc="lower left")

    a2.plot(v.t, v.dif_termico, color=VERDE, lw=1.3)
    a2.set_ylabel("Diferencial\ntérmico [°C]")

    # La zona horaria se fija de forma explicita. Las marcas de tiempo de los
    # datos son conscientes de zona (UTC+02:00) y una marca ingenua se dibuja
    # como si fuera UTC: la banda de la apertura aparecia dos horas despues de
    # su momento real, contradiciendo al texto que la describe.
    tz = v.t.dt.tz
    ap0 = pd.Timestamp("2026-08-28 12:09", tz=tz)
    ap1 = pd.Timestamp("2026-08-28 12:11", tz=tz)
    for ax in (a1, a2):
        ax.axvspan(ap0, ap1, color="#f9a825", alpha=0.35, zorder=0)
    a1.annotate("Puerta abierta", xy=(ap1, a1.get_ylim()[1]),
                xytext=(6, -9), textcoords="offset points", fontsize=7.5)
    # Solo la hora: el formateador automatico antepone el dia a cada marca y
    # lo repite en las nueve etiquetas sin aportar nada, porque el episodio
    # transcurre dentro de un mismo dia.
    a2.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=tz))
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=tz))
    a2.set_xlabel("Hora local del 28 de agosto")
    fig.savefig(SALIDA / "episodio-puerta.pdf")
    plt.close(fig)
    return "episodio-puerta.pdf"


def fig_ciclos(mod):
    """Los ciclos de marcha y parada de la campana de referencia.

    Da la escala temporal del activo, que es la que dimensiona cualquier
    campana: una hora de captura rinde del orden de veinte rafagas utiles.
    """
    d = pl.caracteristicas(pl.limpiar(pl.cargar("entrenamiento", verboso=False)))
    d = pl.episodios(d, mod["umbral_marcha"])
    # Toda la campana disponible, no un solo dia natural: el texto contrasta el
    # tramo de tarde y noche (irregular) con el de madrugada (ciclico), y
    # recortar al 27 de agosto dejaba el primero fuera de la figura.
    v = d
    if not len(v):
        return None
    fig, ax = plt.subplots(figsize=(6.3, 1.5))
    marcha = v.rms_x > mod["umbral_marcha"]
    ax.fill_between(v.t, 0, marcha.astype(int), step="mid",
                    color=AZUL, alpha=0.8, lw=0)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Parado", "Marcha"])
    ax.set_ylim(-0.15, 1.35)
    ax.set_xlabel("Hora local (26 y 27 de agosto)")
    ax.grid(axis="y", alpha=0)
    # Solo la hora en las marcas: el formateador automatico de matplotlib
    # rotula fecha y hora, y en una figura de esta anchura las etiquetas se
    # solapan hasta resultar ilegibles. La fecha ya consta en el rotulo del eje.
    #
    # La zona horaria se pasa de forma explicita: las marcas de tiempo son
    # conscientes de zona (UTC+02:00) y matplotlib rotularia en UTC, desplazando
    # las etiquetas dos horas respecto de la hora local de la captura.
    tz = v.t.dt.tz
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=3, tz=tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=tz))
    # El eje se ajusta al intervalo medido y no a un dia natural: extenderlo
    # mas alla dejaria zonas vacias que sugieren una parada prolongada donde en
    # realidad no hay medida.
    ax.set_xlim(v.t.min(), v.t.max())
    fig.savefig(SALIDA / "ciclos.pdf")
    plt.close(fig)
    return "ciclos.pdf"


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    mod = lc.leer()
    nom, _ = preparar("entrenamiento")
    fal, _ = preparar("fallo")
    hechas = [f for f in (fig_armonicos(nom, fal), fig_bimodal(nom, mod),
                          fig_puerta(mod), fig_ciclos(mod)) if f]
    for f in hechas:
        p = SALIDA / f
        print(f"  {f:24s} {p.stat().st_size/1024:6.0f} KB")
    print(f"\n{len(hechas)} figuras en memoria_TFM/figuras/")


if __name__ == "__main__":
    main()

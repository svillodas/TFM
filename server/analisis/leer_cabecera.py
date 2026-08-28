#!/usr/bin/env python3
"""
Lee los parametros del modelo desde device/modelo_referencia.h.

Existe porque la verificacion contra el nodo tiene que usar EL MODELO QUE LLEVA
LA PLACA, no uno reajustado con los datos de hoy. Reajustarlo introduce una
diferencia que no es un defecto de implementacion sino otro modelo: cada vez que
llegan rafagas nuevas cambian las medianas, el conjunto de ajuste y el umbral, y
la comparacion deja de medir lo que pretende.

Es el mismo principio que el sello de procedencia de la cabecera: un firmware
programado en una placa debe poder rastrearse a los datos que lo produjeron, y
la verificacion debe hacerse contra esos y no contra los de ahora.
"""
import re
from pathlib import Path

import numpy as np

CABECERA = Path(__file__).resolve().parents[2] / "device" / "modelo_referencia.h"


def _define(texto, nombre):
    m = re.search(rf"^#define\s+{nombre}\s+(\S+)\s*$", texto, re.M)
    if not m:
        raise KeyError(f"{nombre} no esta en {CABECERA.name}")
    return float(m.group(1).rstrip("f"))


def _vector(texto, nombre):
    m = re.search(rf"{nombre}\[\d+\]\s*=\s*\{{(.*?)\n\}};", texto, re.S)
    if not m:
        raise KeyError(f"{nombre} no esta en {CABECERA.name}")
    return np.array([float(x) for x in
                     re.findall(r"-?\d+\.\d+e[+-]\d+", m.group(1))])


def _matriz(texto, nombre):
    m = re.search(rf"{nombre}\[(\d+)\]\[(\d+)\]\s*=\s*\{{(.*?)\n\}};", texto, re.S)
    if not m:
        raise KeyError(f"{nombre} no esta en {CABECERA.name}")
    n, d = int(m.group(1)), int(m.group(2))
    filas = re.findall(r"\{([^{}]*)\}", m.group(3))
    if len(filas) != n:
        raise ValueError(f"{nombre}: {len(filas)} filas leidas, se esperaban {n}")
    # Los literales llevan sufijo 'f' y saltos de linea intercalados: se
    # extraen por patron y no partiendo por comas.
    patron = re.compile(r"-?\d+\.\d+e[+-]\d+")
    datos = np.array([[float(x) for x in patron.findall(f)] for f in filas])
    if datos.shape != (n, d):
        raise ValueError(f"{nombre}: forma {datos.shape}, se esperaba {(n, d)}")
    return datos


def leer():
    """Devuelve los parametros del modelo tal como los tiene el firmware."""
    if not CABECERA.exists():
        raise FileNotFoundError(
            f"No existe {CABECERA}. Generala con:\n"
            f"  .venv/bin/python server/analisis/exportar_modelo.py")
    t = CABECERA.read_text(encoding="utf-8")
    sello = re.search(r"Generado por .* el (\S+)", t)
    campana = re.search(r"rafagas\s+(\d+) capturadas, (\d+) utilizables", t)
    m = {
        "generada": sello.group(1) if sello else "(sin sello)",
        "rafagas": campana.groups() if campana else None,
        "media": _vector(t, "MODELO_MEDIA"),
        "escala": _vector(t, "MODELO_ESCALA"),
        "mediana_rms": _define(t, "MODELO_MEDIANA_RMS"),
        "mediana_adom": _define(t, "MODELO_MEDIANA_ADOM"),
        "mediana_dif": _define(t, "MODELO_MEDIANA_DIF"),
        "umbral_marcha": _define(t, "MODELO_UMBRAL_MARCHA"),
        "max_retries": int(_define(t, "MODELO_MAX_RETRIES")),
        "max_cont": int(_define(t, "MODELO_MAX_CONT_REJECTS")),
        "kurt_min": _define(t, "MODELO_KURT_MIN"),
        "kurt_max": _define(t, "MODELO_KURT_MAX"),
        "amp_min_rel": _define(t, "MODELO_AMP_MIN_RELATIVA"),
        "env_centro": _vector(t, "MODELO_ENV_CENTRO"),
        "env_precision": _matriz(t, "MODELO_ENV_PRECISION"),
        "env_umbral": _define(t, "MODELO_ENV_UMBRAL"),
    }
    if "MODELO_LOF_N" in t:
        m.update({
            "lof_k": int(_define(t, "MODELO_LOF_K")),
            "lof_umbral": _define(t, "MODELO_LOF_UMBRAL"),
            "lof_ajuste": _matriz(t, "MODELO_LOF_AJUSTE"),
            "lof_kdist": _vector(t, "MODELO_LOF_KDIST"),
            "lof_lrd": _vector(t, "MODELO_LOF_LRD"),
        })
    return m


def puntuar_lof(m, Z):
    """Reproduce la puntuacion de LOF con los parametros del firmware.

    Es la misma aritmetica que device/detector.h, verificada contra
    scikit-learn con un error de 2e-7.
    """
    Xf, k = m["lof_ajuste"], m["lof_k"]
    out = np.empty(len(Z))
    for i, z in enumerate(Z):
        d = np.linalg.norm(Xf - z, axis=1)
        idx = np.argpartition(d, k)[:k]
        alcance = np.maximum(m["lof_kdist"][idx], d[idx])
        lrd_z = 1.0 / (alcance.mean() + 1e-10)
        out[i] = -(m["lof_lrd"][idx] / lrd_z).mean()
    return out


def normalizar(m, X):
    esc = np.where(m["escala"] != 0, m["escala"], 1.0)
    return (X - m["media"]) / esc


if __name__ == "__main__":
    m = leer()
    print(f"{CABECERA.name}, generada el {m['generada']}")
    if m["rafagas"]:
        print(f"  campana: {m['rafagas'][0]} rafagas capturadas, "
              f"{m['rafagas'][1]} utilizables")
    print(f"  {len(m['media'])} caracteristicas")
    print(f"  medianas: rms {m['mediana_rms']:.4f}  adom {m['mediana_adom']:.4f}"
          f"  dif {m['mediana_dif']:.4f}")
    print(f"  umbral marcha: {m['umbral_marcha']:.6f} m/s2")
    print(f"  filtro: retries<={m['max_retries']}  cont<={m['max_cont']}"
          f"  kurt en [{m['kurt_min']:.0f},{m['kurt_max']:.0f}]")
    print(f"  envolvente: umbral {m['env_umbral']:.4f}, "
          f"matriz {m['env_precision'].shape}")
    if "lof_ajuste" in m:
        print(f"  LOF: umbral {m['lof_umbral']:.6f}, k={m['lof_k']}, "
              f"ajuste {m['lof_ajuste'].shape}")

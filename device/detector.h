// =====================================================================
// Detector de anomalías embarcado.
//
// SIN DEPENDENCIAS DE ARDUINO a proposito, igual que signal_processing.h: se
// compila y verifica en el PC antes de subirlo a la placa.
//
//   g++ -std=c++11 -O2 -o /tmp/test_det device/test/test_detector.cpp
//
// Los parametros viven en modelo_referencia.h, que genera
// server/analisis/exportar_modelo.py: aqui la aritmetica, alli los numeros.
// Reentrenar no debe obligar a tocar codigo.
// =====================================================================
#ifndef DETECTOR_H
#define DETECTOR_H

#include <math.h>
#include <stdint.h>

#include "modelo_referencia.h"

// Veredicto del nodo. Se publica en un topic propio y NO como campos nuevos
// del payload de ráfaga: añadir campos cambia la cabecera del CSV y parte la
// serie histórica en dos conjuntos no comparables.
enum Veredicto {
  VEREDICTO_NOMINAL = 0,
  VEREDICTO_ANOMALIA = 1,
  // El nodo se NIEGA a juzgar. No es un estado intermedio de salud: es la
  // declaración de que la medida no es apta para decidir. Los reintentos del
  // bus fabrican la firma del fallo sobre un activo sano, de modo que juzgar
  // una ráfaga degradada produce un falso positivo sistemático.
  VEREDICTO_NO_EVALUABLE = 2,
};

// ---------------------------------------------------------------------
// Cuenta los picos espectrales con amplitud significativa.
//
// El umbral es RELATIVO a la mayor de las tres amplitudes, no absoluto: el
// nivel de vibración difiere en un factor 12,5 entre los dos activos
// medidos, de modo que cualquier umbral con unidades separaría máquinas en
// lugar de estados.
// ---------------------------------------------------------------------
inline uint8_t countSignificantPeaks(float a0, float a1, float a2) {
  const float amps[3] = {a0, a1, a2};
  float mayor = amps[0];
  for (uint8_t i = 1; i < 3; i++) {
    if (amps[i] > mayor) mayor = amps[i];
  }
  if (!(mayor > 0.0f)) return 0;          // ráfaga sin contenido espectral
  uint8_t n = 0;
  for (uint8_t i = 0; i < 3; i++) {
    if (amps[i] >= MODELO_AMP_MIN_RELATIVA * mayor) n++;
  }
  return n;
}

// ---------------------------------------------------------------------
// Medida cruda de una ráfaga: lo que el nodo tiene antes de derivar nada.
// Se agrupa en una estructura para que la derivación sea verificable en el PC
// con los mismos valores que produjo la placa.
// ---------------------------------------------------------------------
struct MedidaRafaga {
  // Eje X del acelerómetro. Es el único utilizable: su kurtosis está en rango
  // físico en el 100 % de las ráfagas de los dos activos medidos, mientras la
  // del eje Z lo está en el 59 % y el 44 %.
  float rms, peak, kurt;
  float fdom, adom;        // pico dominante (POR AMPLITUD, como lo da el firmware)
  float f2, a2;            // segundo pico por amplitud
  float f3, a3;            // tercer pico por amplitud
  float audB0, audB1, audB2;   // fracciones de energía acústica
  float difTermico;        // motorTemp - tempExt, en grados
  float gradMotor;         // pendiente de motorTemp, en grados por minuto
  uint16_t retries, contRejects;
};

// ---------------------------------------------------------------------
// Deriva el vector de características a partir de la medida cruda.
//
// DEBE REPRODUCIR EXACTAMENTE server/analisis/pipeline.py. Una discrepancia no
// da error: da un veredicto sin sentido. Se verifica contra los valores de
// Python sobre las mismas rafagas reales (device/test/test_detector.cpp).
// El orden de las 14 posiciones lo declara modelo_referencia.h.
// ---------------------------------------------------------------------
inline void derivarCaracteristicas(const MedidaRafaga& m, float* x) {
  // Los tres picos se REORDENAN POR FRECUENCIA, no por amplitud, descartando
  // antes los de amplitud despreciable. Ambas condiciones son necesarias:
  //   - por amplitud (como los da el firmware) el armonico puede superar a la
  //     fundamental y quitarle la posicion de dominante: el mismo fenomeno
  //     daba 9,0 en unas rafagas y 0,111 en otras;
  //   - solo por frecuencia, un pico de ruido bajo pasa por fundamental y el
  //     cociente de amplitudes se dispara.
  float fr[3] = {m.fdom, m.f2, m.f3};
  float am[3] = {m.adom, m.a2, m.a3};

  float mayor = am[0];
  for (uint8_t i = 1; i < 3; i++) {
    if (am[i] > mayor) mayor = am[i];
  }
  const float umbralAmp = MODELO_AMP_MIN_RELATIVA * mayor;

  // Los no significativos se mandan al final asignándoles frecuencia infinita,
  // de modo que la ordenación por frecuencia los deje detrás sin descartarlos:
  // sus valores siguen haciendo falta para rellenar las posiciones 2 y 3.
  float clave[3];
  uint8_t nPicos = 0;
  for (uint8_t i = 0; i < 3; i++) {
    const bool signif = (mayor > 0.0f) && (am[i] >= umbralAmp);
    clave[i] = signif ? fr[i] : INFINITY;
    if (signif) nPicos++;
  }
  // Ordenación por inserción de tres elementos: más corto y más claro que
  // cualquier alternativa, y el coste es irrelevante.
  uint8_t ord[3] = {0, 1, 2};
  for (uint8_t i = 1; i < 3; i++) {
    for (uint8_t j = i; j > 0 && clave[ord[j - 1]] > clave[ord[j]]; j--) {
      const uint8_t t = ord[j]; ord[j] = ord[j - 1]; ord[j - 1] = t;
    }
  }
  const float f0 = fr[ord[0]], a0 = am[ord[0]];

  x[0]  = m.kurt;
  x[1]  = (m.rms != 0.0f) ? m.peak / m.rms : 0.0f;            // crest
  x[2]  = (f0 != 0.0f) ? fr[ord[1]] / f0 : 0.0f;              // r2
  x[3]  = (f0 != 0.0f) ? fr[ord[2]] / f0 : 0.0f;              // r3
  x[4]  = (a0 != 0.0f) ? am[ord[1]] / a0 : 0.0f;              // q2
  x[5]  = (a0 != 0.0f) ? am[ord[2]] / a0 : 0.0f;              // q3
  x[6]  = (float)nPicos;
  x[7]  = m.rms  / MODELO_MEDIANA_RMS;                        // rms_x_rel
  x[8]  = m.adom / MODELO_MEDIANA_ADOM;                       // adom_x_rel
  x[9]  = m.difTermico / MODELO_MEDIANA_DIF;                  // dif_rel
  x[10] = m.gradMotor;
  x[11] = m.audB0;
  x[12] = m.audB1;
  x[13] = m.audB2;
  // aud_b3 NO se incluye: las cuatro bandas suman 1 por construcción, de modo
  // que la cuarta es 1 - b0 - b1 - b2. Incluirla vuelve singular la matriz de
  // covarianza de la envolvente (condición 3,9e7 frente a 6,5e4) y la forma
  // cuadrática pierde toda precisión en simple.
}

// ---------------------------------------------------------------------
// ¿Es esta ráfaga apta para emitir veredicto?
//
// No es un filtro de limpieza: es parte del detector. Los reintentos del bus
// FABRICAN la firma del fallo sobre un activo sano — con más de diez, el
// número de picos significativos de un activo NOMINAL pasa de 1 a 3 y la
// fundamental estimada se derrumba de 49 Hz a 20 Hz. Juzgar una ráfaga
// degradada produce un falso positivo sistemático.
// ---------------------------------------------------------------------
inline bool rafagaEvaluable(const MedidaRafaga& m) {
  if (m.retries > MODELO_MAX_RETRIES) return false;
  if (m.contRejects > MODELO_MAX_CONT_REJECTS) return false;
  if (m.kurt < MODELO_KURT_MIN || m.kurt > MODELO_KURT_MAX) return false;
  // Con el compresor detenido no hay vibración que analizar. El umbral se
  // derivó del valle de la distribución bimodal del valor eficaz del propio
  // activo; no es un valor absoluto trasladable a otra máquina.
  if (m.rms <= MODELO_UMBRAL_MARCHA) return false;
  return true;
}

// ---------------------------------------------------------------------
// Normaliza el vector de características al espacio en que se ajustó el
// modelo. Debe llamarse antes de cualquier puntuación.
// ---------------------------------------------------------------------
inline void normalizar(const float* x, float* z) {
  for (uint8_t i = 0; i < MODELO_N_CARACTERISTICAS; i++) {
    const float e = MODELO_ESCALA[i];
    z[i] = (e != 0.0f) ? (x[i] - MODELO_MEDIA[i]) / e : 0.0f;
  }
}

// ---------------------------------------------------------------------
// Envolvente robusta. Devuelve -(z-mu)' P (z-mu): cuanto MENOR, más
// anómalo, igual convención que el resto de puntuaciones.
//
// La forma cuadrática se evalúa aprovechando la simetría de la matriz de
// precisión, lo que ahorra la mitad de los productos.
// ---------------------------------------------------------------------
inline float puntuarEnvolvente(const float* z) {
  float dif[MODELO_N_CARACTERISTICAS];
  for (uint8_t i = 0; i < MODELO_N_CARACTERISTICAS; i++) {
    dif[i] = z[i] - MODELO_ENV_CENTRO[i];
  }
  // El acumulador es DOBLE a propósito. La matriz de covarianza tiene un
  // número de condición de 6,5e4, de modo que la forma cuadrática sufre
  // cancelación: se suman términos mucho mayores que el resultado. En simple
  // precisión quedan ~2 dígitos significativos y el veredicto puede cambiar.
  // Son 240 operaciones cada 30 s: el coste de emular doble es irrelevante.
  double acc = 0.0;
  for (uint8_t i = 0; i < MODELO_N_CARACTERISTICAS; i++) {
    acc += (double)MODELO_ENV_PRECISION[i][i] * dif[i] * dif[i];
    for (uint8_t j = i + 1; j < MODELO_N_CARACTERISTICAS; j++) {
      acc += 2.0 * (double)MODELO_ENV_PRECISION[i][j] * dif[i] * dif[j];
    }
  }
  return (float)(-acc);
}

#ifndef MODELO_SIN_LOF
// ---------------------------------------------------------------------
// LOF. Es el modelo que seleccionó el protocolo sin sesgo de espionaje.
//
// Selección de los K menores por recorrido parcial y no por ordenación
// completa: con K = 10 sobre N = 505 son unas 5000 comparaciones, frente a
// las ~4500 de una ordenación, pero sin necesidad de un vector auxiliar de
// 505 posiciones en la pila del microcontrolador.
// ---------------------------------------------------------------------
inline float puntuarLOF(const float* z) {
  float dK[MODELO_LOF_K];
  uint16_t iK[MODELO_LOF_K];
  for (uint8_t i = 0; i < MODELO_LOF_K; i++) {
    dK[i] = INFINITY;
    iK[i] = 0;
  }
  for (uint16_t n = 0; n < MODELO_LOF_N; n++) {
    float d2 = 0.0f;
    for (uint8_t i = 0; i < MODELO_N_CARACTERISTICAS; i++) {
      const float t = z[i] - MODELO_LOF_AJUSTE[n][i];
      d2 += t * t;
    }
    if (d2 >= dK[MODELO_LOF_K - 1]) continue;      // no entra entre los K
    uint8_t p = MODELO_LOF_K - 1;
    while (p > 0 && dK[p - 1] > d2) {
      dK[p] = dK[p - 1];
      iK[p] = iK[p - 1];
      p--;
    }
    dK[p] = d2;
    iK[p] = n;
  }
  // Las distancias se acumulaban al cuadrado para evitar 505 raíces; aquí
  // solo hacen falta K.
  float suma_alcance = 0.0f, suma_lrd = 0.0f;
  for (uint8_t i = 0; i < MODELO_LOF_K; i++) {
    const float d = sqrtf(dK[i]);
    const float kd = MODELO_LOF_KDIST[iK[i]];
    suma_alcance += (kd > d) ? kd : d;              // distancia de alcance
    suma_lrd += MODELO_LOF_LRD[iK[i]];
  }
  const float lrd_z = 1.0f / (suma_alcance / (float)MODELO_LOF_K + 1e-10f);
  return -(suma_lrd / (float)MODELO_LOF_K) / lrd_z;
}
#endif  // MODELO_SIN_LOF

// ---------------------------------------------------------------------
// Histéresis. Un detector que avisa con una ráfaga suelta es inservible en
// la práctica: la tasa de falsos positivos medida es del 7,8 % sobre
// ráfagas AISLADAS, y exigir varias consecutivas la reduce en dos órdenes
// de magnitud bajo el supuesto de independencia.
//
// Las ráfagas no evaluables NO rompen la cuenta ni la incrementan: no
// aportan información sobre el estado de la máquina.
// ---------------------------------------------------------------------
struct Histeresis {
  uint8_t requeridas;    // ráfagas anómalas consecutivas para notificar
  uint8_t consecutivas;
  bool notificado;

  void inicializar(uint8_t n) {
    requeridas = n;
    consecutivas = 0;
    notificado = false;
  }

  // Devuelve true solo en la transición a estado notificable, para no
  // republicar la misma alarma en cada ráfaga.
  bool actualizar(Veredicto v) {
    if (v == VEREDICTO_NO_EVALUABLE) return false;
    if (v == VEREDICTO_ANOMALIA) {
      if (consecutivas < 255) consecutivas++;
      if (consecutivas >= requeridas && !notificado) {
        notificado = true;
        return true;
      }
    } else {
      consecutivas = 0;
      notificado = false;
    }
    return false;
  }
};

#endif  // DETECTOR_H

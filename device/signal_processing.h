// =====================================================================
// signal_processing.h — Procesado digital de señal: extracción de
// características de vibración y audio.
//
// Qué contiene: las matemáticas que convierten una ráfaga de muestras
// crudas en unos pocos números interpretables (nivel de vibración,
// frecuencia a la que vibra, impulsividad, reparto de energía acústica).
// No lee sensores ni publica nada: eso es trabajo de device.ino.
//
// Sin dependencias de Arduino a propósito: permite compilar y verificar
// estas funciones en el PC con g++ antes de subirlas a la placa
// (ver device/test/test_signal_processing.cpp).
//
// Justificación del diseño: muestrear a 1 Hz limita el análisis a
// frecuencias por debajo de 0,5 Hz (Nyquist), mientras que la vibración
// de un compresor está en torno a los 48 Hz (2900 RPM) y sus armónicos.
// Estas funciones operan sobre ráfagas capturadas a alta tasa, de las
// que se extraen características en el propio nodo. Así se obtiene
// contenido frecuencial sin transmitir la señal cruda.
// =====================================================================
#pragma once

#include <math.h>
#include <stdint.h>

static const float PI_SIGNAL = 3.14159265358979323846f;

// Número máximo de muestras por ráfaga. Debe ser potencia de dos.
#define MAX_SAMPLES 1024

// ---------------------------------------------------------------------
// Características de una ráfaga de un eje de vibración
// ---------------------------------------------------------------------
struct AxisFeatures {
  float rms;        // Valor eficaz de la componente alterna, en m/s^2
  float peak;       // Máximo valor absoluto tras eliminar la continua
  float kurtosis;   // Factor de forma. 3,0 = gaussiano; >3 indica impulsividad
  float domFreq;    // Frecuencia dominante, en Hz
  float domAmp;     // Amplitud estimada a la frecuencia dominante, en m/s^2
  // Segundo y tercer pico espectral, ORDENADOS POR MAGNITUD DECRECIENTE.
  //
  // Por qué tres y no solo el dominante: en el banco se midieron
  // componentes entre 398 Hz y 497 Hz que se llevan el 95 % de la energía
  // y dejan la fundamental del compresor (49 Hz) fuera del pico principal.
  // Con un solo pico esa información se perdía en el nodo y no era
  // recuperable en el hub, porque solo se transmiten características y no
  // la señal. Se prefirió esto a acotar la búsqueda a una banda fija, y
  // resultó determinante: esas componentes son los armónicos 8x, 9x y 10x
  // del giro, es decir la firma de un fallo real, y un límite de banda las
  // habría dejado fuera.
  //
  // AVISO PARA QUIEN CONSUMA ESTOS CAMPOS. El orden es por AMPLITUD, no
  // por frecuencia, y las dos componentes pueden tener amplitudes muy
  // próximas: en el activo con fallo el armónico supera a la fundamental
  // por un 2 % en el 9 % de las ráfagas y le quita la posición de
  // dominante. Un cociente del tipo freq2/domFreq es por tanto INESTABLE
  // (da 9,0 en unas ráfagas y 0,111 en otras describiendo el mismo
  // fenómeno). Hay que reordenar por frecuencia y descartar antes los picos
  // por debajo del 20 % de la amplitud mayor. Ver server/analisis/README.md.
  //
  // TRES SON INSUFICIENTES: uno es la fundamental, así que solo caben dos
  // armónicos por ráfaga y la familia de tres no se registra completa.
  // Ampliarlo a cinco está pendiente.
  float freq2, amp2;
  float freq3, amp3;
};

// ---------------------------------------------------------------------
// Transformada rápida de Fourier, radix-2, en el sitio.
// n debe ser potencia de dos. Los factores de giro se calculan de forma
// directa (no por recurrencia) para no acumular error; cuesta más tiempo
// de cálculo pero el resultado es reproducible.
// ---------------------------------------------------------------------
static void fourierTransform(float* re, float* im, uint16_t n) {
  // Permutación por inversión de bits
  for (uint16_t i = 1, j = 0; i < n; i++) {
    uint16_t bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      float t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }

  for (uint16_t len = 2; len <= n; len <<= 1) {
    uint16_t half = len >> 1;
    for (uint16_t k = 0; k < half; k++) {
      float ang = -2.0f * PI_SIGNAL * (float)k / (float)len;
      float cr = cosf(ang);
      float ci = sinf(ang);
      for (uint16_t i = 0; i < n; i += len) {
        float ur = re[i + k],        ui = im[i + k];
        float ar = re[i + k + half], ai = im[i + k + half];
        float vr = ar * cr - ai * ci;
        float vi = ar * ci + ai * cr;
        re[i + k] = ur + vr;        im[i + k] = ui + vi;
        re[i + k + half] = ur - vr; im[i + k + half] = ui - vi;
      }
    }
  }
}

// ---------------------------------------------------------------------
// Ventana de Hann. Reduce la fuga espectral de una señal no periódica
// en la ventana de análisis. Su ganancia coherente es 0,5, de donde sale
// el factor 4/N que se aplica al recuperar la amplitud.
// ---------------------------------------------------------------------
static void applyHannWindow(float* x, uint16_t n) {
  for (uint16_t i = 0; i < n; i++) {
    x[i] *= 0.5f * (1.0f - cosf(2.0f * PI_SIGNAL * (float)i / (float)(n - 1)));
  }
}

// ---------------------------------------------------------------------
// Filtro paso bajo Butterworth de segundo orden, en forma directa I.
// Los coeficientes se calculan a partir de la frecuencia de corte por
// transformada bilineal, en lugar de tabularse, para que la función sea
// verificable frente a su respuesta teórica.
//
// Se aplica únicamente a los estadísticos temporales (valor eficaz, pico
// y kurtosis) y no al espectro. El motivo: una componente de alta
// frecuencia dominante contamina esos tres estadísticos, que se calculan
// en el dominio del tiempo y por tanto integran toda la banda, mientras
// que en el espectro interesa seguir viéndola. Esto último no es un
// detalle: los estadísticos filtrados NO registran el fallo detectado en
// EXP-003, y su detección depende por completo del espectro sin filtrar.
// ---------------------------------------------------------------------
struct Biquad {
  float b0, b1, b2, a1, a2;   // coeficientes
  float x1, x2, y1, y2;       // estado
};

static void biquadLowPass(Biquad& f, float cutoff, float fs) {
  const float k = tanf(PI_SIGNAL * cutoff / fs);
  const float norm = 1.0f / (1.0f + 1.41421356f * k + k * k);
  f.b0 = k * k * norm;
  f.b1 = 2.0f * f.b0;
  f.b2 = f.b0;
  f.a1 = 2.0f * (k * k - 1.0f) * norm;
  f.a2 = (1.0f - 1.41421356f * k + k * k) * norm;
  f.x1 = f.x2 = f.y1 = f.y2 = 0.0f;
}

// Inicializa el estado en régimen permanente para la primera muestra, de
// forma que el filtro no introduzca un transitorio de arranque que
// falsearía el valor de pico y la kurtosis.
static void biquadPrime(Biquad& f, float x0) {
  f.x1 = f.x2 = x0;
  f.y1 = f.y2 = x0;
}

static inline float biquadStep(Biquad& f, float x) {
  const float y = f.b0 * x + f.b1 * f.x1 + f.b2 * f.x2 - f.a1 * f.y1 - f.a2 * f.y2;
  f.x2 = f.x1; f.x1 = x;
  f.y2 = f.y1; f.y1 = y;
  return y;
}

// ---------------------------------------------------------------------
// Localiza el coeficiente de mayor magnitud del espectro, excluyendo las
// vecindades de los picos ya encontrados. La ventana de Hann reparte un
// tono sobre cuatro coeficientes, de modo que la guarda evita devolver
// como pico distinto la falda del mismo tono.
// ---------------------------------------------------------------------
static uint16_t bestBinExcluding(const float* re, const float* im,
                                 uint16_t minBin, uint16_t maxBin,
                                 const uint16_t* excl, uint8_t nExcl,
                                 float& bestMag) {
  const uint16_t GUARD = 4;
  bestMag = -1.0f;
  uint16_t best = minBin;
  for (uint16_t k = minBin; k < maxBin; k++) {
    bool cerca = false;
    for (uint8_t e = 0; e < nExcl; e++) {
      const uint16_t d = (k > excl[e]) ? (k - excl[e]) : (excl[e] - k);
      if (d <= GUARD) { cerca = true; break; }
    }
    if (cerca) continue;
    const float mag = sqrtf(re[k] * re[k] + im[k] * im[k]);
    if (mag > bestMag) { bestMag = mag; best = k; }
  }
  return best;
}

// Refina un pico por interpolación parabólica sobre la log-magnitud de
// los tres coeficientes centrales y devuelve frecuencia y amplitud.
static void refinePeak(const float* re, const float* im, uint16_t n, float fs,
                       uint16_t bin, float mag, float& freq, float& amp) {
  float magLow = 0.0f, magHigh = 0.0f;
  if (bin >= 1) magLow = sqrtf(re[bin-1]*re[bin-1] + im[bin-1]*im[bin-1]);
  if (bin + 1 < n) magHigh = sqrtf(re[bin+1]*re[bin+1] + im[bin+1]*im[bin+1]);

  const float alpha = logf(magLow + 1e-20f);
  const float beta  = logf(mag + 1e-20f);
  const float gamma = logf(magHigh + 1e-20f);
  const float den = alpha - 2.0f * beta + gamma;

  float delta = 0.0f, peakLog = beta;
  if (fabsf(den) > 1e-12f) {
    delta = 0.5f * (alpha - gamma) / den;
    if (delta >  0.5f) delta =  0.5f;
    if (delta < -0.5f) delta = -0.5f;
    peakLog = beta - 0.25f * (alpha - gamma) * delta;
  }
  freq = ((float)bin + delta) * fs / (float)n;
  amp  = 4.0f * expf(peakLog) / (float)n;   // ganancia coherente de Hann
}

// ---------------------------------------------------------------------
// Analiza una ráfaga de un eje.
//   samples : señal en unidades físicas (m/s^2)
//   n       : número de muestras, potencia de dos, <= MAX_SAMPLES
//   fs      : frecuencia de muestreo en Hz
//   re, im  : buffers de trabajo de al menos n elementos (los sobrescribe)
//   minFreq : frecuencia mínima considerada al buscar la dominante, en Hz.
//             Descarta la continua residual y la deriva de baja frecuencia.
//
// La resolución frecuencial resultante es fs/n.
// ---------------------------------------------------------------------
static AxisFeatures analyzeAxis(const float* samples, uint16_t n,
                                float fs, float* re, float* im,
                                float minFreq = 2.0f, float lpCutoff = 0.0f) {
  AxisFeatures f = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
  if (n == 0) return f;

  // 1. Eliminar la componente continua. En el eje vertical la continua es
  //    la gravedad, que no aporta información de vibración.
  double sum = 0.0;
  for (uint16_t i = 0; i < n; i++) sum += samples[i];
  const float mean = (float)(sum / (double)n);

  // 2. La componente alterna se deja en re[] para el análisis espectral,
  //    que interesa SIN filtrar: las componentes de alta frecuencia deben
  //    seguir siendo visibles, porque es donde reside la firma del fallo.
  for (uint16_t i = 0; i < n; i++) {
    re[i] = samples[i] - mean;
    im[i] = 0.0f;
  }

  // 3. Estadísticos temporales, sobre la señal opcionalmente filtrada.
  //    El filtro se recorre muestra a muestra y no requiere almacén
  //    adicional: el biquad solo mantiene cuatro variables de estado.
  const bool filtrar = (lpCutoff > 0.0f && lpCutoff < fs * 0.5f);
  Biquad bq;
  if (filtrar) {
    biquadLowPass(bq, lpCutoff, fs);
    biquadPrime(bq, re[0]);
  }

  double m2 = 0.0, m4 = 0.0;
  for (uint16_t i = 0; i < n; i++) {
    const float d = filtrar ? biquadStep(bq, re[i]) : re[i];
    const double d2 = (double)d * (double)d;
    m2 += d2;
    m4 += d2 * d2;
    const float a = fabsf(d);
    if (a > f.peak) f.peak = a;
  }
  m2 /= (double)n;
  m4 /= (double)n;
  f.rms = (float)sqrt(m2);
  // Kurtosis en la convención de monitorización de condición: 3,0 para
  // ruido gaussiano. Indefinida si la señal es constante.
  f.kurtosis = (m2 > 1e-12) ? (float)(m4 / (m2 * m2)) : 0.0f;

  // 4. Espectro sobre la componente alterna sin filtrar.
  applyHannWindow(re, n);
  fourierTransform(re, im, n);

  uint16_t minBin = (uint16_t)(minFreq * (float)n / fs);
  if (minBin < 1) minBin = 1;
  const uint16_t maxBin = n / 2;              // hasta Nyquist
  if (minBin >= maxBin) return f;

  // 5. Los tres picos de mayor magnitud, con guarda entre ellos.
  uint16_t excl[3];
  uint8_t nExcl = 0;
  float mag = 0.0f;

  uint16_t bin = bestBinExcluding(re, im, minBin, maxBin, excl, nExcl, mag);
  if (mag <= 0.0f) return f;                  // señal sin contenido alterno
  refinePeak(re, im, n, fs, bin, mag, f.domFreq, f.domAmp);
  excl[nExcl++] = bin;

  bin = bestBinExcluding(re, im, minBin, maxBin, excl, nExcl, mag);
  if (mag > 0.0f) {
    refinePeak(re, im, n, fs, bin, mag, f.freq2, f.amp2);
    excl[nExcl++] = bin;

    bin = bestBinExcluding(re, im, minBin, maxBin, excl, nExcl, mag);
    if (mag > 0.0f) refinePeak(re, im, n, fs, bin, mag, f.freq3, f.amp3);
  }

  return f;
}

// ---------------------------------------------------------------------
// Energía acústica por bandas.
//   Devuelve en energy[] la fracción de energía espectral de cada banda
//   definida por los límites edges[0..numBands] (en Hz), normalizada
//   respecto a la energía total analizada. Valores en [0, 1].
// ---------------------------------------------------------------------
static void bandEnergy(const float* samples, uint16_t n, float fs,
                       float* re, float* im,
                       const float* edges, uint8_t numBands,
                       float* energy) {
  for (uint8_t b = 0; b < numBands; b++) energy[b] = 0.0f;
  if (n == 0) return;

  double sum = 0.0;
  for (uint16_t i = 0; i < n; i++) sum += samples[i];
  float mean = (float)(sum / (double)n);
  for (uint16_t i = 0; i < n; i++) { re[i] = samples[i] - mean; im[i] = 0.0f; }

  applyHannWindow(re, n);
  fourierTransform(re, im, n);

  double total = 0.0;
  for (uint16_t k = 1; k < n / 2; k++) {
    total += (double)re[k] * re[k] + (double)im[k] * im[k];
  }
  if (total <= 0.0) return;

  for (uint8_t b = 0; b < numBands; b++) {
    uint16_t k0 = (uint16_t)(edges[b] * (float)n / fs);
    uint16_t k1 = (uint16_t)(edges[b + 1] * (float)n / fs);
    if (k0 < 1) k0 = 1;
    if (k1 > n / 2) k1 = n / 2;
    double acc = 0.0;
    for (uint16_t k = k0; k < k1; k++) {
      acc += (double)re[k] * re[k] + (double)im[k] * im[k];
    }
    energy[b] = (float)(acc / total);
  }
}

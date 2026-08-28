// =====================================================================
// Verificación de device/signal_processing.h en el PC, con señales
// sintéticas de propiedades conocidas analíticamente.
//
//   g++ -std=c++11 -O2 -o /tmp/test_signal \
//       device/test/test_signal_processing.cpp && /tmp/test_signal
//
// Comprobar estas funciones aquí evita depurar matemáticas a través del
// puerto serie de la placa.
// =====================================================================
#include "../signal_processing.h"
#include <stdio.h>
#include <stdlib.h>

static float re[MAX_SAMPLES], im[MAX_SAMPLES], sig[MAX_SAMPLES];
static int failures = 0, checks = 0;

static void expectNear(const char* name, float actual, float expected, float tol) {
  checks++;
  bool ok = fabsf(actual - expected) <= tol;
  if (!ok) failures++;
  printf("  [%s] %-46s obtenido=%10.4f esperado=%10.4f (tol %.4f)\n",
         ok ? "OK " : "FAL", name, actual, expected, tol);
}

int main() {
  const uint16_t N = 1024;

  // -----------------------------------------------------------------
  // 1. Vibración: seno de 48 Hz y amplitud 2 m/s^2 sobre la gravedad.
  //    Es el caso de uso real: compresor a 2900 RPM con el eje vertical
  //    soportando 9,81 m/s^2 de continua.
  // -----------------------------------------------------------------
  printf("\n1. Seno 48 Hz, amplitud 2,0 m/s^2, continua 9,81 (fs=1000 Hz, N=1024)\n");
  float fs = 1000.0f;
  for (uint16_t i = 0; i < N; i++) {
    sig[i] = 9.81f + 2.0f * sinf(2.0f * PI_SIGNAL * 48.0f * i / fs);
  }
  AxisFeatures f = analyzeAxis(sig, N, fs, re, im);
  // Con interpolación parabólica la frecuencia se resuelve muy por debajo
  // del bin (fs/N = 0,977 Hz), de ahí la tolerancia estrecha.
  expectNear("frecuencia dominante", f.domFreq, 48.0f, 0.05f);
  expectNear("RMS (A/raiz(2), la continua se elimina)", f.rms, 2.0f / sqrtf(2.0f), 0.01f);
  expectNear("pico", f.peak, 2.0f, 0.02f);
  expectNear("amplitud a la frecuencia dominante", f.domAmp, 2.0f, 0.08f);
  expectNear("kurtosis de un seno (valor analitico 1,5)", f.kurtosis, 1.5f, 0.02f);

  // -----------------------------------------------------------------
  // 2. La continua no debe contaminar ninguna característica: misma
  //    señal sin gravedad debe dar los mismos resultados.
  // -----------------------------------------------------------------
  printf("\n2. Misma senal sin componente continua\n");
  for (uint16_t i = 0; i < N; i++) {
    sig[i] = 2.0f * sinf(2.0f * PI_SIGNAL * 48.0f * i / fs);
  }
  AxisFeatures f2 = analyzeAxis(sig, N, fs, re, im);
  expectNear("frecuencia dominante invariante", f2.domFreq, f.domFreq, 0.001f);
  expectNear("RMS invariante", f2.rms, f.rms, 0.001f);

  // -----------------------------------------------------------------
  // 3. Segundo armónico dominante: 96 Hz con más amplitud que 48 Hz.
  //    Verifica que se elige el máximo real y no el primer pico.
  // -----------------------------------------------------------------
  printf("\n3. 48 Hz (amp 1,0) + 96 Hz (amp 3,0): debe elegir 96 Hz\n");
  for (uint16_t i = 0; i < N; i++) {
    sig[i] = 1.0f * sinf(2.0f * PI_SIGNAL * 48.0f * i / fs)
           + 3.0f * sinf(2.0f * PI_SIGNAL * 96.0f * i / fs);
  }
  AxisFeatures f3 = analyzeAxis(sig, N, fs, re, im);
  expectNear("frecuencia dominante", f3.domFreq, 96.0f, 0.05f);
  // Error de amplitud acotado al 4 % en el peor caso de festoneado
  expectNear("amplitud dominante", f3.domAmp, 3.0f, 0.12f);
  // RMS de la suma de dos senos incoherentes: sqrt((1^2+3^2)/2)
  expectNear("RMS de la suma", f3.rms, sqrtf((1.0f + 9.0f) / 2.0f), 0.02f);

  // -----------------------------------------------------------------
  // 4. Señal constante: no debe dividir por cero ni devolver NaN.
  // -----------------------------------------------------------------
  printf("\n4. Senal constante (caso degenerado)\n");
  for (uint16_t i = 0; i < N; i++) sig[i] = 9.81f;
  AxisFeatures f4 = analyzeAxis(sig, N, fs, re, im);
  expectNear("RMS nulo", f4.rms, 0.0f, 1e-4f);
  expectNear("kurtosis definida (no NaN)", isnan(f4.kurtosis) ? 999.0f : f4.kurtosis, 0.0f, 1e-4f);
  expectNear("amplitud dominante ~0", f4.domAmp, 0.0f, 1e-3f);

  // -----------------------------------------------------------------
  // 5. Kurtosis de un impulso: debe ser muy superior a la de un seno.
  //    Es el indicador de fallo incipiente en rodamientos.
  // -----------------------------------------------------------------
  printf("\n5. Tren de impulsos: la kurtosis debe dispararse\n");
  for (uint16_t i = 0; i < N; i++) sig[i] = 0.0f;
  for (uint16_t i = 0; i < N; i += 128) sig[i] = 10.0f;
  AxisFeatures f5 = analyzeAxis(sig, N, fs, re, im);
  checks++;
  if (f5.kurtosis > 20.0f) {
    printf("  [OK ] %-46s obtenido=%10.4f (> 20)\n", "kurtosis de impulsos", f5.kurtosis);
  } else {
    failures++;
    printf("  [FAL] %-46s obtenido=%10.4f (deberia ser > 20)\n", "kurtosis de impulsos", f5.kurtosis);
  }

  // -----------------------------------------------------------------
  // 6. Audio: tono de 2 kHz a fs=16 kHz. Su energía debe concentrarse
  //    en la banda 1000-4000 Hz.
  // -----------------------------------------------------------------
  printf("\n6. Audio: tono de 2 kHz a fs=16 kHz, energia por bandas\n");
  float audioFs = 16000.0f;
  for (uint16_t i = 0; i < N; i++) {
    sig[i] = 1000.0f * sinf(2.0f * PI_SIGNAL * 2000.0f * i / audioFs);
  }
  const float edges[5] = {0.0f, 250.0f, 1000.0f, 4000.0f, 8000.0f};
  float energy[4];
  bandEnergy(sig, N, audioFs, re, im, edges, 4, energy);
  printf("  bandas: 0-250=%.4f  250-1k=%.4f  1k-4k=%.4f  4k-8k=%.4f\n",
         energy[0], energy[1], energy[2], energy[3]);
  expectNear("energia concentrada en 1k-4k", energy[2], 1.0f, 0.02f);
  expectNear("banda 0-250 practicamente vacia", energy[0], 0.0f, 0.01f);
  expectNear("suma de bandas = 1", energy[0]+energy[1]+energy[2]+energy[3], 1.0f, 0.02f);

  // -----------------------------------------------------------------
  // 7. Demostración del problema que motivó el cambio: la misma
  //    vibración de 48 Hz muestreada a 1 Hz produce un valor sin
  //    relación con la frecuencia real (aliasing).
  // -----------------------------------------------------------------
  printf("\n7. Demostracion de aliasing: 48 Hz muestreado a 1 Hz\n");
  const uint16_t N2 = 64;
  for (uint16_t i = 0; i < N2; i++) {
    sig[i] = 2.0f * sinf(2.0f * PI_SIGNAL * 48.0f * i / 1.0f);   // fs = 1 Hz
  }
  AxisFeatures f7 = analyzeAxis(sig, N2, 1.0f, re, im, 0.0f);
  printf("  frecuencia 'detectada' = %.4f Hz (Nyquist a 1 Hz es 0,5 Hz;\n", f7.domFreq);
  printf("  la senal real esta a 48 Hz, luego el resultado no tiene sentido fisico)\n");

  // 8. Tres picos: la resonancia del acoplamiento no debe ocultar la
  //    fundamental del compresor. Reproduce el caso medido en el banco:
  //    449 Hz con amplitud 0,93 (resonancia) y 49 Hz con 0,21 (motor).
  {
    printf("\n8. Resonancia 449 Hz (amp 0,93) + fundamental 49 Hz (amp 0,21)\n");
    static float sig[1024];
    for (int i = 0; i < 1024; i++) {
      sig[i] = 0.93f * sinf(2.0f * PI_SIGNAL * 449.0f * i / 1000.0f)
             + 0.21f * sinf(2.0f * PI_SIGNAL *  49.0f * i / 1000.0f);
    }
    AxisFeatures f8 = analyzeAxis(sig, 1024, 1000.0f, re, im);
    expectNear("pico 1: la resonancia", f8.domFreq, 449.0f, 0.5f);
    expectNear("pico 2: la fundamental del compresor", f8.freq2, 49.0f, 0.5f);
    expectNear("amplitud del pico 1", f8.domAmp, 0.93f, 0.05f);
    expectNear("amplitud del pico 2", f8.amp2, 0.21f, 0.03f);
  }

  // 9. Filtro paso bajo sobre los estadisticos temporales: con la misma
  //    senal, filtrar a 150 Hz debe eliminar la resonancia y dejar solo
  //    la fundamental, cuyo valor eficaz es 0,21/raiz(2).
  {
    printf("\n9. Filtro a 150 Hz: rms debe pasar de la suma a solo 49 Hz\n");
    static float sig[1024];
    for (int i = 0; i < 1024; i++) {
      sig[i] = 0.93f * sinf(2.0f * PI_SIGNAL * 449.0f * i / 1000.0f)
             + 0.21f * sinf(2.0f * PI_SIGNAL *  49.0f * i / 1000.0f);
    }
    AxisFeatures sinF = analyzeAxis(sig, 1024, 1000.0f, re, im, 2.0f, 0.0f);
    AxisFeatures conF = analyzeAxis(sig, 1024, 1000.0f, re, im, 2.0f, 150.0f);
    const float rmsTotal = sqrtf((0.93f*0.93f + 0.21f*0.21f) / 2.0f);
    expectNear("rms sin filtrar (suma de las dos)", sinF.rms, rmsTotal, 0.02f);
    expectNear("rms filtrado (solo la de 49 Hz)", conF.rms, 0.21f/sqrtf(2.0f), 0.02f);
    expectNear("kurtosis filtrada -> seno puro (1,5)", conF.kurtosis, 1.5f, 0.1f);
    // El espectro NO debe filtrarse: la resonancia sigue siendo visible.
    expectNear("el espectro conserva la resonancia", conF.domFreq, 449.0f, 0.5f);
  }

  // 10. El filtro debe respetar la banda de paso: un tono de 49 Hz no
  //     puede quedar atenuado por un corte en 150 Hz.
  {
    printf("\n10. Ganancia del filtro en la banda de paso\n");
    static float sig[1024];
    for (int i = 0; i < 1024; i++)
      sig[i] = 2.0f * sinf(2.0f * PI_SIGNAL * 49.0f * i / 1000.0f);
    AxisFeatures f10 = analyzeAxis(sig, 1024, 1000.0f, re, im, 2.0f, 150.0f);
    expectNear("rms de 49 Hz filtrado a 150 Hz (sin atenuar)", f10.rms,
               2.0f/sqrtf(2.0f), 0.05f);
  }

  // 11. Audio: el filtro debe poder desactivarse, o destruiria el
  //     analisis acustico a 16 kHz.
  {
    printf("\n11. Sin filtro por omision (necesario para el audio)\n");
    static float sig[1024];
    for (int i = 0; i < 1024; i++)
      sig[i] = 1.0f * sinf(2.0f * PI_SIGNAL * 2000.0f * i / 16000.0f);
    AxisFeatures f11 = analyzeAxis(sig, 1024, 16000.0f, re, im, 20.0f);
    expectNear("tono de 2 kHz intacto sin filtro", f11.rms, 1.0f/sqrtf(2.0f), 0.02f);
  }

  printf("\n=====================================================\n");
  printf("Pruebas: %d   Fallos: %d\n", checks, failures);
  printf("=====================================================\n");
  return failures == 0 ? 0 : 1;
}

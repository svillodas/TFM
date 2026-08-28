// =====================================================================
// Verificación de la integración del detector en el firmware, SIN PLACA.
//
//   g++ -std=c++11 -O2 -o /tmp/test_int device/test/test_integracion.cpp \
//       && /tmp/test_int
//
// Extrae de device.ino la lógica que no depende de periféricos —la ventana
// térmica, la estimación de la pendiente y la construcción del payload de
// estado— con stubs mínimos de Arduino, y comprueba que el veredicto sobre
// ráfagas reales coincide con el que produjo scikit-learn.
//
// Qué NO comprueba: nada que dependa de I2C, I2S, Wi-Fi o MQTT. Eso exige la
// placa. Lo que sí garantiza es que la aritmética y el formato del mensaje son
// correctos antes de gastar un ciclo de flasheo en descubrirlo.
// =====================================================================
#include <cstdio>
#include <cstring>
#include <cmath>
#include <cstdint>

#include "../detector.h"
#include "casos_modelo.h"

// --- stubs mínimos ----------------------------------------------------
static uint32_t g_millis = 0;
static uint32_t millis() { return g_millis; }
static uint32_t micros() { return g_millis * 1000; }
static char payload[1152];

// --- copia literal de la lógica de device.ino -------------------------
static const uint8_t DET_RAFAGAS_CONSECUTIVAS = 3;
static Histeresis histeresis;

static const uint8_t TERM_N = MODELO_VENTANA_GRADIENTE_S + 8;
static float termTemp[TERM_N];
static uint32_t termMs[TERM_N];
static uint8_t termCabeza = 0;
static uint8_t termLlenado = 0;

static void registrarTemperatura(float motorTemp, uint32_t ahora) {
  termTemp[termCabeza] = motorTemp;
  termMs[termCabeza] = ahora;
  termCabeza = (uint8_t)((termCabeza + 1) % TERM_N);
  if (termLlenado < TERM_N) termLlenado++;
}

static float gradienteMotor(uint32_t ahora) {
  const uint32_t desde = ahora - (uint32_t)MODELO_VENTANA_GRADIENTE_S * 1000UL;
  double sx = 0, sy = 0, sxx = 0, sxy = 0;
  uint16_t n = 0;
  for (uint8_t i = 0; i < termLlenado; i++) {
    if (termMs[i] < desde || termMs[i] > ahora) continue;
    const double x = ((double)termMs[i] - (double)ahora) / 1000.0;
    const double y = (double)termTemp[i];
    sx += x; sy += y; sxx += x * x; sxy += x * y;
    n++;
  }
  if (n < 5) return 0.0f;
  const double den = (double)n * sxx - sx * sx;
  if (den == 0.0) return 0.0f;
  return (float)((((double)n * sxy - sx * sy) / den) * 60.0);
}

// --- comprobaciones ---------------------------------------------------
static int fallos = 0;
static void comprobar(bool ok, const char* que) {
  std::printf("  [%s] %s\n", ok ? "OK " : "FALLO", que);
  if (!ok) fallos++;
}

int main() {
  std::printf("\nIntegración del detector en el firmware (sin placa)\n\n");

  // ---- 1. Ventana térmica y pendiente --------------------------------
  std::printf("1. Ventana térmica circular\n");
  comprobar(TERM_N > MODELO_VENTANA_GRADIENTE_S,
            "la ventana tiene margen sobre el intervalo del modelo");

  termCabeza = termLlenado = 0;
  g_millis = 100000;
  // Rampa de 0,5 grados por minuto durante 90 s, a 1 Hz.
  for (int i = 0; i < 90; i++) {
    registrarTemperatura(40.0f + 0.5f * (float)i / 60.0f, g_millis);
    g_millis += 1000;
  }
  const float g = gradienteMotor(g_millis - 1000);
  std::printf("     rampa sintética de 0,500 °C/min -> estimado %.4f\n", g);
  comprobar(std::fabs(g - 0.5f) < 0.02f, "la pendiente se estima correctamente");

  termCabeza = termLlenado = 0;
  comprobar(gradienteMotor(g_millis) == 0.0f,
            "sin histórico devuelve 0 y no divide por cero");

  termCabeza = termLlenado = 0;
  for (int i = 0; i < 3; i++) { registrarTemperatura(40.0f, g_millis); g_millis += 1000; }
  comprobar(gradienteMotor(g_millis) == 0.0f,
            "con menos de 5 lecturas devuelve 0, igual que el análisis");

  // Sobreescritura circular: se registran más lecturas que posiciones.
  termCabeza = termLlenado = 0;
  g_millis = 500000;
  for (int i = 0; i < TERM_N * 3; i++) {
    registrarTemperatura(30.0f + 1.0f * (float)i / 60.0f, g_millis);
    g_millis += 1000;
  }
  const float gc = gradienteMotor(g_millis - 1000);
  std::printf("     tras %d lecturas en %d posiciones -> %.4f (esperado 1,000)\n",
              TERM_N * 3, TERM_N, gc);
  comprobar(std::fabs(gc - 1.0f) < 0.05f,
            "la ventana circular no corrompe la estimación al dar la vuelta");

  // ---- 2. Payload de estado ------------------------------------------
  std::printf("\n2. Payload de estado\n");
  std::snprintf(payload, sizeof(payload),
    "{\"health\":\"%s\",\"streak\":%u,\"notify\":%u,"
    "\"lof\":%.4f,\"env\":%.2f,\"n_peaks\":%u,"
    "\"us_inference\":%u}",
    "not_evaluable", 255u, 1u, -12345.6789f, -999999.99f, 3u, 4294967295u);
  std::printf("     peor caso (%zu B): %s\n", std::strlen(payload), payload);
  comprobar(std::strlen(payload) < sizeof(payload),
            "el peor caso cabe en el buffer");
  comprobar(std::strlen(payload) < 1024,
            "y en el buffer de PubSubClient con holgura");

  // ---- 3. Veredicto sobre ráfagas reales -----------------------------
  std::printf("\n3. Veredicto sobre las %d ráfagas reales\n", CASOS_N);
  int anom_nom = 0, anom_fal = 0, discrepancias = 0;
  for (int i = 0; i < CASOS_N; i++) {
    float z[MODELO_N_CARACTERISTICAS];
    normalizar(CASOS_X[i], z);
#ifndef MODELO_SIN_LOF
    const float s = puntuarLOF(z);
    const Veredicto v = (s < MODELO_LOF_UMBRAL) ? VEREDICTO_ANOMALIA
                                                : VEREDICTO_NOMINAL;
    const bool ref = CASOS_LOF[i] < CASOS_LOF_UMBRAL;
#else
    const float s = puntuarEnvolvente(z);
    const Veredicto v = (s < MODELO_ENV_UMBRAL) ? VEREDICTO_ANOMALIA
                                                : VEREDICTO_NOMINAL;
    const bool ref = CASOS_ENV[i] < CASOS_ENV_UMBRAL;
#endif
    if ((v == VEREDICTO_ANOMALIA) != ref) discrepancias++;
    if (v == VEREDICTO_ANOMALIA) {
      if (i < CASOS_N_NOMINAL) anom_nom++; else anom_fal++;
    }
  }
  std::printf("     activo nominal: %d de %d marcadas (%.1f %%)\n",
              anom_nom, CASOS_N_NOMINAL, 100.0 * anom_nom / CASOS_N_NOMINAL);
  std::printf("     activo con fallo: %d de %d marcadas (%.1f %%)\n",
              anom_fal, CASOS_N - CASOS_N_NOMINAL,
              100.0 * anom_fal / (CASOS_N - CASOS_N_NOMINAL));
  comprobar(discrepancias == 0,
            "el veredicto del firmware coincide con scikit-learn en los 1161");

  // ---- 4. Histéresis sobre la secuencia real -------------------------
  // Simula el flujo de ráfagas tal como llegarían: primero las del activo
  // nominal y después las del activo con fallo, y cuenta cuántas veces
  // notificaría el nodo. Es la cifra que importa en operación: no el
  // porcentaje de ráfagas marcadas, sino el número de avisos emitidos.
  std::printf("\n4. Avisos emitidos con histéresis de %d ráfagas\n",
              DET_RAFAGAS_CONSECUTIVAS);
  for (int req = 1; req <= 4; req++) {
    histeresis.inicializar((uint8_t)req);
    int avisos_nom = 0, avisos_fal = 0;
    for (int i = 0; i < CASOS_N; i++) {
      float z[MODELO_N_CARACTERISTICAS];
      normalizar(CASOS_X[i], z);
#ifndef MODELO_SIN_LOF
      const bool anom = puntuarLOF(z) < MODELO_LOF_UMBRAL;
#else
      const bool anom = puntuarEnvolvente(z) < MODELO_ENV_UMBRAL;
#endif
      const bool aviso = histeresis.actualizar(anom ? VEREDICTO_ANOMALIA
                                                    : VEREDICTO_NOMINAL);
      if (aviso) { if (i < CASOS_N_NOMINAL) avisos_nom++; else avisos_fal++; }
    }
    std::printf("     exigiendo %d: %2d avisos falsos sobre el nominal, "
                "%d sobre el fallo\n", req, avisos_nom, avisos_fal);
    if (req == DET_RAFAGAS_CONSECUTIVAS) {
      comprobar(avisos_nom <= 1,
                "con la histéresis elegida, a lo sumo un aviso falso");
      comprobar(avisos_fal >= 1, "y el fallo se notifica");
    }
  }

  std::printf("\n=====================================================\n");
  std::printf("Fallos: %d\n", fallos);
  std::printf("=====================================================\n\n");
  return fallos == 0 ? 0 : 1;
}

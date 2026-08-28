// =====================================================================
// Verificación en el PC del detector embarcado, contra la referencia de
// scikit-learn sobre las 1161 ráfagas reales de las dos campañas.
//
//   g++ -std=c++11 -O2 -o /tmp/test_det device/test/test_detector.cpp \
//       && /tmp/test_det
//
// Qué comprueba y por qué importa: si el C++ reproduce el veredicto de
// Python sobre datos reales, la implementación es correcta y en la placa
// solo queda medir tiempo y memoria. Depurar aritmética por el puerto serie
// cuesta un orden de magnitud más.
//
// La tolerancia se declara y se justifica: el modelo se ajusta en Python en
// doble precisión y el firmware evalúa en simple, de modo que una
// discrepancia del orden de 1e-5 en la puntuación es esperable. Lo que NO se
// tolera es una discrepancia en el VEREDICTO, que es lo que el nodo publica.
// =====================================================================
#include <cstdio>
#include <cmath>

#include "../detector.h"
#include "casos_modelo.h"

static int fallos = 0;

// Tolerancias, y el motivo de que sean dos.
//
// El error relativo sobre la puntuación no es la magnitud que decide: las
// puntuaciones abarcan de -2,7 a -364 000 y las de mayor magnitud están
// lejísimas del umbral, de modo que un error apreciable en ellas no cambia
// ningún veredicto. Lo que importa es el error CERCA DE LA FRONTERA, que es
// donde una discrepancia sí invierte la decisión.
static const float TOL_GLOBAL = 1e-3f;    // error relativo en todo el rango
// Criterio que de verdad decide, y se calibra a sí mismo: el error ABSOLUTO de
// la puntuación debe ser mucho menor que la distancia del caso más próximo al
// umbral. Si lo es, ningún veredicto puede invertirse por precisión numérica.
// El factor 5 es el margen de seguridad exigido.
static const float FACTOR_SEGURIDAD = 5.0f;

static void comprobar(bool ok, const char* que) {
  std::printf("  [%s] %s\n", ok ? "OK " : "FALLO", que);
  if (!ok) fallos++;
}

int main() {
  std::printf("\nVerificación del detector embarcado frente a scikit-learn\n");
  std::printf("%d casos reales: %d del activo nominal, %d del activo con fallo\n\n",
              CASOS_N, CASOS_N_NOMINAL, CASOS_N - CASOS_N_NOMINAL);

  // ---- 1. Coherencia entre las dos cabeceras generadas -----------------
  std::printf("1. Coherencia de las cabeceras generadas\n");
  comprobar(CASOS_D == MODELO_N_CARACTERISTICAS,
            "el número de características coincide");
  comprobar(std::fabs(CASOS_ENV_UMBRAL - MODELO_ENV_UMBRAL) < 1e-3f,
            "el umbral de la envolvente coincide");

  // ---- 1b. Derivación de características -------------------------------
  // Es la comprobación que más importa: si el C++ deriva el vector de forma
  // distinta a Python, no hay ningún error visible, solo un veredicto sin
  // sentido. Se compara contra el vector que calculó pipeline.py sobre la
  // MISMA ráfaga.
  // Se verifica SOLO sobre el activo nominal, y el motivo no es de comodidad.
  // Tres características (rms_x_rel, adom_x_rel, dif_rel) se normalizan por la
  // mediana del PROPIO activo, que el nodo aprende en su campaña de referencia
  // y que viaja en modelo_referencia.h. El análisis en Python, en cambio,
  // normaliza cada conjunto por su propia mediana, de modo que para el activo
  // con fallo emplea la mediana de datos ya defectuosos.
  //
  // LIMITACIÓN QUE ESTO PONE DE MANIFIESTO: esas tres características NO PUEDEN
  // VALIDARSE con los datos disponibles. Existen para detectar un fallo que
  // solo altere el nivel sobre una máquina con su propia referencia sana, y del
  // activo con fallo no hay ningún periodo sano medido. Usar su propia mediana
  // las anula; usar la del activo de referencia reintroduciría el sesgo entre
  // máquinas. Solo un fallo inducido sobre el activo de referencia lo resuelve.
  std::printf("\n1b. Derivación de características desde la medida cruda\n");
  std::printf("     (solo el activo nominal: las 3 características relativas se\n");
  std::printf("      normalizan por la mediana del propio activo)\n");
  float peor_deriv = 0.0f;
  int peor_i = -1, peor_j = -1, discrepancias_picos = 0;
  for (int i = 0; i < CASOS_N_NOMINAL; i++) {
    MedidaRafaga m;
    const float* c = CASOS_CRUDO[i];
    m.rms = c[0];  m.peak = c[1];  m.kurt = c[2];
    m.fdom = c[3]; m.adom = c[4];
    m.f2 = c[5];   m.a2 = c[6];
    m.f3 = c[7];   m.a3 = c[8];
    m.audB0 = c[9]; m.audB1 = c[10]; m.audB2 = c[11];
    m.difTermico = c[12]; m.gradMotor = c[13];
    m.retries = (uint16_t)c[14]; m.contRejects = (uint16_t)c[15];

    float x[MODELO_N_CARACTERISTICAS];
    derivarCaracteristicas(m, x);
    for (int j = 0; j < MODELO_N_CARACTERISTICAS; j++) {
      const float err = std::fabs(x[j] - CASOS_X[i][j]) /
                        (std::fabs(CASOS_X[i][j]) + 1e-3f);
      if (err > peor_deriv) { peor_deriv = err; peor_i = i; peor_j = j; }
    }
    // El recuento de picos es entero: debe coincidir exactamente.
    if ((int)x[6] != (int)(CASOS_X[i][6] + 0.5f)) discrepancias_picos++;
  }
  // El recuento de picos y los cocientes espectrales NO dependen de ninguna
  // mediana, de modo que sí se comprueban sobre los 1161 casos.
  int discrep_todos = 0;
  float peor_espectral = 0.0f;
  for (int i = 0; i < CASOS_N; i++) {
    MedidaRafaga m;
    const float* c = CASOS_CRUDO[i];
    m.rms = c[0];  m.peak = c[1];  m.kurt = c[2];
    m.fdom = c[3]; m.adom = c[4];
    m.f2 = c[5];   m.a2 = c[6];
    m.f3 = c[7];   m.a3 = c[8];
    m.audB0 = c[9]; m.audB1 = c[10]; m.audB2 = c[11];
    m.difTermico = c[12]; m.gradMotor = c[13];
    float x[MODELO_N_CARACTERISTICAS];
    derivarCaracteristicas(m, x);
    if ((int)x[6] != (int)(CASOS_X[i][6] + 0.5f)) discrep_todos++;
    const int espectrales[6] = {0, 1, 2, 3, 4, 5};
    for (int k = 0; k < 6; k++) {
      const int j = espectrales[k];
      const float err = std::fabs(x[j] - CASOS_X[i][j]) /
                        (std::fabs(CASOS_X[i][j]) + 1e-3f);
      if (err > peor_espectral) peor_espectral = err;
    }
  }
  std::printf("     sobre los %d casos, características independientes de\n", CASOS_N);
  std::printf("     medianas (kurtosis, cresta, r2, r3, q2, q3): error %.3e\n",
              peor_espectral);
  comprobar(peor_espectral < 1e-4f,
            "coinciden en AMBOS activos, incluido el del fallo");
  comprobar(discrep_todos == 0,
            "y el recuento de picos coincide en los 1161");
  std::printf("     error relativo máximo: %.3e", peor_deriv);
  if (peor_i >= 0) std::printf("  (caso %d, característica %d)", peor_i, peor_j);
  std::printf("\n");
  comprobar(peor_deriv < 1e-4f,
            "las 14 características coinciden con pipeline.py");
  std::printf("     recuentos de picos discrepantes: %d de %d\n",
              discrepancias_picos, CASOS_N_NOMINAL);
  comprobar(discrepancias_picos == 0, "el recuento de picos coincide exactamente");

  // Criterio de evaluabilidad. Se comprueba SOLO sobre el activo nominal, y el
  // motivo es una consecuencia de diseño que conviene tener presente: el umbral
  // marcha/parada se derivó del propio activo de referencia y vale 0,199 m/s²,
  // mientras que el activo con fallo tiene un valor eficaz en marcha de
  // 0,16 m/s². Con el modelo del nodo A, las ráfagas del nodo B se clasifican
  // como "compresor detenido".
  //
  // NO es un defecto: EL MODELO EXPORTADO ES ESPECÍFICO DEL ACTIVO SOBRE EL QUE
  // SE AJUSTÓ. No se puede flashear el modelo de una máquina en otra. Cada nodo
  // necesita su propia campaña de referencia.
  int eval_nom = 0, eval_fal = 0;
  for (int i = 0; i < CASOS_N; i++) {
    MedidaRafaga m;
    const float* c = CASOS_CRUDO[i];
    m.rms = c[0]; m.kurt = c[2];
    m.retries = (uint16_t)c[14]; m.contRejects = (uint16_t)c[15];
    if (rafagaEvaluable(m)) { if (i < CASOS_N_NOMINAL) eval_nom++; else eval_fal++; }
  }
  std::printf("     evaluables del activo nominal: %d de %d\n",
              eval_nom, CASOS_N_NOMINAL);
  comprobar(eval_nom == CASOS_N_NOMINAL,
            "todas las del conjunto ya filtrado son evaluables, como debe ser");
  std::printf("     evaluables del activo con fallo: %d de %d"
              "  (su nivel en marcha queda por debajo del umbral del nodo A)\n",
              eval_fal, CASOS_N - CASOS_N_NOMINAL);

  // ---- 2. Puntuación de la envolvente ----------------------------------
  std::printf("\n2. Envolvente robusta\n");
  float peor_rel = 0.0f, peor_abs = 0.0f, margen_min = INFINITY;
  int discrepancias_env = 0;
  for (int i = 0; i < CASOS_N; i++) {
    float z[MODELO_N_CARACTERISTICAS];
    normalizar(CASOS_X[i], z);
    const float mio = puntuarEnvolvente(z);
    const float ref = CASOS_ENV[i];
    const float abs_err = std::fabs(mio - ref);
    const float rel_err = abs_err / (std::fabs(ref) + 1.0f);
    if (rel_err > peor_rel) peor_rel = rel_err;
    if (abs_err > peor_abs) peor_abs = abs_err;
    if ((mio < MODELO_ENV_UMBRAL) != (ref < CASOS_ENV_UMBRAL)) discrepancias_env++;
    const float dist = std::fabs(ref - CASOS_ENV_UMBRAL);
    if (dist < margen_min) margen_min = dist;
  }
  std::printf("     error relativo máximo:              %.3e\n", peor_rel);
  comprobar(peor_rel < TOL_GLOBAL, "la puntuación coincide con scikit-learn");
  std::printf("     error absoluto máximo:              %.3e\n", peor_abs);
  std::printf("     margen del caso más próximo al umbral: %.3e\n", margen_min);
  std::printf("     cociente margen/error:              %.1fx (se exige %.0fx)\n",
              margen_min / (peor_abs + 1e-30f), FACTOR_SEGURIDAD);
  comprobar(margen_min > FACTOR_SEGURIDAD * peor_abs,
            "el error es muy inferior al margen: ningún veredicto puede invertirse");
  std::printf("     veredictos discrepantes: %d de %d\n", discrepancias_env, CASOS_N);
  comprobar(discrepancias_env == 0, "TODOS los veredictos coinciden");

  // ---- 3. Puntuación de LOF -------------------------------------------
#ifndef MODELO_SIN_LOF
  std::printf("\n3. LOF (el modelo que seleccionó el protocolo)\n");
  float peor_lof = 0.0f;
  int discrepancias_lof = 0, det_fallo = 0, fp_nominal = 0;
  for (int i = 0; i < CASOS_N; i++) {
    float z[MODELO_N_CARACTERISTICAS];
    normalizar(CASOS_X[i], z);
    const float mio = puntuarLOF(z);
    const float ref = CASOS_LOF[i];
    const float err = std::fabs(mio - ref) / (std::fabs(ref) + 1.0f);
    if (err > peor_lof) peor_lof = err;
    const bool anom_mio = mio < MODELO_LOF_UMBRAL;
    const bool anom_ref = ref < CASOS_LOF_UMBRAL;
    if (anom_mio != anom_ref) discrepancias_lof++;
    if (i < CASOS_N_NOMINAL) { if (anom_mio) fp_nominal++; }
    else                     { if (anom_mio) det_fallo++; }
  }
  std::printf("     error relativo máximo en la puntuación: %.3e\n", peor_lof);
  comprobar(peor_lof < TOL_GLOBAL, "la puntuación coincide con scikit-learn");
  std::printf("     veredictos discrepantes: %d de %d\n", discrepancias_lof, CASOS_N);
  comprobar(discrepancias_lof == 0, "TODOS los veredictos coinciden");
  std::printf("     falsos positivos sobre el nominal: %d/%d = %.1f %%\n",
              fp_nominal, CASOS_N_NOMINAL, 100.0 * fp_nominal / CASOS_N_NOMINAL);
  std::printf("     detección sobre el fallo:          %d/%d = %.1f %%\n",
              det_fallo, CASOS_N - CASOS_N_NOMINAL,
              100.0 * det_fallo / (CASOS_N - CASOS_N_NOMINAL));
#endif

  // ---- 4. Recuento de picos significativos -----------------------------
  std::printf("\n4. Recuento de picos significativos\n");
  comprobar(countSignificantPeaks(1.0f, 0.05f, 0.03f) == 1,
            "una fundamental dominante y dos picos de ruido dan 1");
  comprobar(countSignificantPeaks(1.0f, 0.80f, 0.30f) == 3,
            "tres componentes apreciables dan 3");
  // Este es el caso que motiva el recuento: en el activo con fallo el armónico
  // supera a la fundamental por un 2 %, y con el orden por amplitud del
  // firmware el mismo fenómeno cambiaba de posición. El recuento debe ser
  // invariante a esa permutación.
  comprobar(countSignificantPeaks(0.2016f, 0.2056f, 0.01f) == 2,
            "dos amplitudes casi iguales y una despreciable dan 2");
  comprobar(countSignificantPeaks(0.2056f, 0.2016f, 0.01f) == 2,
            "y el resultado no cambia al permutarlas");
  // 0,05 sí alcanza el 20 % de 0,2056: son tres picos significativos, no dos.
  comprobar(countSignificantPeaks(0.2016f, 0.2056f, 0.05f) == 3,
            "un tercer pico al 24 % del mayor sí cuenta");
  comprobar(countSignificantPeaks(0.0f, 0.0f, 0.0f) == 0,
            "una ráfaga sin contenido espectral da 0, no divide por cero");

  // ---- 5. Histéresis ---------------------------------------------------
  std::printf("\n5. Histéresis\n");
  Histeresis h;
  h.inicializar(3);
  comprobar(!h.actualizar(VEREDICTO_ANOMALIA), "una anomalía aislada no notifica");
  comprobar(!h.actualizar(VEREDICTO_ANOMALIA), "dos consecutivas tampoco");
  comprobar(h.actualizar(VEREDICTO_ANOMALIA), "la tercera consecutiva notifica");
  comprobar(!h.actualizar(VEREDICTO_ANOMALIA), "la cuarta no vuelve a notificar");

  h.inicializar(3);
  h.actualizar(VEREDICTO_ANOMALIA);
  h.actualizar(VEREDICTO_ANOMALIA);
  h.actualizar(VEREDICTO_NOMINAL);
  comprobar(!h.actualizar(VEREDICTO_ANOMALIA),
            "una ráfaga nominal intercalada reinicia la cuenta");

  h.inicializar(3);
  h.actualizar(VEREDICTO_ANOMALIA);
  h.actualizar(VEREDICTO_NO_EVALUABLE);
  comprobar(h.actualizar(VEREDICTO_ANOMALIA) == false,
            "una ráfaga no evaluable no cuenta como anomalía");
  comprobar(h.actualizar(VEREDICTO_ANOMALIA),
            "ni rompe la cuenta: la tercera anómala notifica");

  std::printf("\n=====================================================\n");
  std::printf("Fallos: %d\n", fallos);
  std::printf("=====================================================\n\n");
  return fallos == 0 ? 0 : 1;
}

// =====================================================================
// Nodo edge de mantenimiento predictivo — TFM MUIoT (UDC)
//
// Captura la firma física de un compresor de refrigeración (vibración,
// temperatura y sonido) y publica por MQTT.
//
// El nodo trabaja con dos cadencias distintas y publica en dos topics:
//
//   fridge/sensors     1 Hz. Nueve variables instantáneas.
//
//   fridge/vibration   Cada BURST_PERIOD_MS. Características extraídas
//                      de una ráfaga de vibración muestreada a 1 kHz y
//                      de una ventana de audio a 16 kHz.
//
// A 1 Hz no cabe analisis frecuencial: el compresor vibra en torno a 48 Hz
// (2900 RPM). De ahi la rafaga a 1 kHz, con las caracteristicas calculadas
// en el nodo para no transmitir senal cruda.
// =====================================================================
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <driver/i2s.h>
#include <WiFi.h>
#include <PubSubClient.h>

#include "signal_processing.h"
#include "detector.h"  // Detector embarcado. Los parametros, en modelo_referencia.h
#include "secrets.h"   // Copiar desde secrets.h.example y rellenar

// --- TOPICS MQTT ---
#ifndef MQTT_TOPIC_PREFIX
#define MQTT_TOPIC_PREFIX ""
#endif
const char* TOPIC_SLOW  = MQTT_TOPIC_PREFIX "fridge/sensors";
const char* TOPIC_BURST = MQTT_TOPIC_PREFIX "fridge/vibration";
// Topic PROPIO, no campos nuevos del payload de rafaga: anadir campos cambia
// la cabecera del CSV, que el registrador solo escribe al crear el fichero, y
// las filas posteriores quedan desplazadas. Ya ocurrio (server/data/README.md).
const char* TOPIC_STATUS = MQTT_TOPIC_PREFIX "fridge/status";

// --- CADENCIAS (no bloqueantes, gestionadas con millis) ---
const uint32_t SLOW_PERIOD_MS  = 1000;           // canal lento: 1 Hz
const uint32_t BURST_PERIOD_MS = 30000;          // ráfaga cada 30 s

// --- PARÁMETROS DE LA RÁFAGA DE VIBRACIÓN ---
const uint16_t VIB_N         = 1024;
const uint32_t VIB_FS        = 1000;
const uint32_t VIB_PERIOD_US = 1000000UL / VIB_FS;

// --- PARÁMETROS DE LA VENTANA DE AUDIO ---
const uint16_t AUDIO_N  = 1024;
const uint32_t AUDIO_FS = 16000;
const float AUDIO_EDGES[5] = {0.0f, 250.0f, 1000.0f, 4000.0f, 8000.0f};

WiFiClient espClient;
PubSubClient client(espClient);

// --- CONFIGURACIÓN TEMPERATURA (DS18B20) ---
const int TEMPERATURE_DATA_PIN = 14;
OneWire oneWire(TEMPERATURE_DATA_PIN);
DallasTemperature tempSensor(&oneWire);

// --- BUS I2C ---
#define I2C_SDA 1
#define I2C_SCL 2
#define I2C_FREQ_HZ 200000

// --- CONFIGURACIÓN VIBRACIÓN (MPU-6050) ---
Adafruit_MPU6050 mpu;
#define MPU_ADDR        0x68
#define MPU_ACCEL_XOUT  0x3B
#define MPU_GYRO_CONFIG 0x1B

// --- CONFIGURACIÓN MICRÓFONO (INMP441 - I2S) ---
#define I2S_WS 12
#define I2S_SD 13
#define I2S_SCK 17
#define I2S_PORT I2S_NUM_0

// --- BUFFERS ESTÁTICOS ---
static int16_t burstX[VIB_N], burstY[VIB_N], burstZ[VIB_N];
static int32_t rawAudio[AUDIO_N];
static float workRe[MAX_SAMPLES], workIm[MAX_SAMPLES];
static float floatSamples[MAX_SAMPLES];
// 1152 B con setBufferSize(1408): la cabecera del PUBLISH y el topic ocupan
// ~45 B. Peor caso medido del payload de rafaga: ~1015 B.
//
// AVISO: un desbordamiento haria que snprintf truncase y publicase JSON
// invalido en silencio. Todo campo nuevo exige recalcular esto.
static char payload[1152];

// Factor de conversión de cuentas a m/s^2 para el rango +-4 g
// (8192 LSB/g según la hoja de características) y g = 9,80665 m/s^2.
const float LSB_TO_MS2 = 9.80665f / 8192.0f;

// Escalado del giróscopo. NO es una constante: el factor depende del
// rango que tenga configurado el chip, y darlo por supuesto fue un error
// medido en la placa. Adafruit_MPU6050::_init() pide +-500 grados/s, pero
// si mpu.begin() no llegó a completarse el chip se queda en su rango de
// arranque de +-250, y una constante fija devuelve el doble del valor
// real. Se inicializa al rango de arranque y updateGyroScale() lo corrige
// leyendo GYRO_CONFIG del propio dispositivo.
const float DPS_TO_RADS = 0.0174532925f;
float gyroLsbToRads = (1.0f / 131.0f) * DPS_TO_RADS;   // +-250 grados/s

// Banda de plausibilidad del módulo del vector de aceleración. El sensor
// mide siempre la gravedad, y un compresor doméstico no produce decenas
// de m/s^2, de modo que una lectura fuera de esta banda es basura del bus
// y no una medida. La banda es deliberadamente ancha para no descartar
// vibración real. Es la segunda línea de defensa: la primera es la
// validación de la propia transacción I2C en readRegisters().
const float ACC_MAG_MIN = 2.0f;    // m/s^2
const float ACC_MAG_MAX = 25.0f;   // m/s^2
const float ACC_MAG2_MIN_LSB = (ACC_MAG_MIN / LSB_TO_MS2) * (ACC_MAG_MIN / LSB_TO_MS2);
const float ACC_MAG2_MAX_LSB = (ACC_MAG_MAX / LSB_TO_MS2) * (ACC_MAG_MAX / LSB_TO_MS2);

// Salto maximo admisible entre dos muestras consecutivas de un mismo eje. La
// comprobacion de modulo es ancha y NO detecta la caida de un solo eje si los
// otros dos la compensan: se midio kurt_z de 750 con peak_z en 5,8-6,16 m/s^2
// y failed_bursts en 0, porque el modulo seguia en banda.
//
// El umbral queda entre los dos limites medidos:
//   pendiente legitima maxima      2,6 m/s^2 por muestra (0,93 m/s^2 a 448 Hz)
//   salto de muestra corrupta      5,8 a 11,9 m/s^2, segun la orientacion
// 6 m/s^2 deja factor 2,3 sobre la primera y queda bajo el menor salto de
// corrupcion observado.
//
// PENDIENTE: deberia ser relativo a la continua de cada eje. Con 6 m/s^2 los
// cortes del eje Z del nodo A no se detectan, porque la gravedad reposa sobre X
// y la continua de Z es de 1,66 m/s^2. No modificar con una campana en curso.
const float ACC_STEP_MAX_MS2 = 6.0f;   // m/s^2 por muestra (periodo 1 ms)
const float ACC_STEP_MAX_LSB = ACC_STEP_MAX_MS2 / LSB_TO_MS2;

// Corte del filtro paso bajo aplicado a los estadísticos temporales de la
// ráfaga: valor eficaz, pico y kurtosis. Se calculan en el dominio del
// tiempo y por tanto integran toda la banda, de modo que una componente de
// alta frecuencia dominante los dejaba sin información diagnóstica: con
// ella presente, la kurtosis quedaba clavada en 1,75 (el 1,5 de una
// senoide pura) hiciera lo que hiciera el compresor.
//
// 150 Hz conserva la fundamental del activo (49 Hz) y sus dos primeros
// armónicos. El valor se derivó de la regla de no pasar de un tercio de la
// resonancia del montaje, aplicada a los 448 Hz que entonces se atribuían
// al pegado adhesivo. Esa atribución era FALSA (son armónicos del giro) y
// la resonancia real del montaje sigue sin medir, de modo que 150 Hz es una
// cota conservadora sin verificar.
//
// El espectro NO se filtra, y esa decisión es la que hizo posible detectar
// el fallo: los estadísticos filtrados NO lo registran. Para eso están los
// tres picos.
const float VIB_LP_CUTOFF_HZ = 150.0f;

// --- ESTADO DEL DETECTOR ---
//
// Histeresis: no se notifica con una rafaga suelta. La tasa de falsos positivos
// medida es del 7,8 % sobre rafagas AISLADAS, y exigir tres consecutivas la
// reduce en dos ordenes de magnitud si se suponen independientes.
const uint8_t DET_RAFAGAS_CONSECUTIVAS = 3;
Histeresis histeresis;

// Ventana circular de temperatura del motor: estima la pendiente termica del
// minuto anterior, que distingue el arranque en frio del regimen estacionario.
// Con margen sobre la ventana del modelo, porque el canal lento puede desviarse.
const uint8_t TERM_N = MODELO_VENTANA_GRADIENTE_S + 8;
float termTemp[TERM_N];
uint32_t termMs[TERM_N];
uint8_t termCabeza = 0;
uint8_t termLlenado = 0;

// Diferencial termico mas reciente. Lo escribe el canal lento y lo lee el de
// rafaga: es la union entre ambas cadencias dentro del nodo.
float ultimoDifTermico = 0.0f;
bool difTermicoValido = false;

// Registra una lectura de temperatura del motor en la ventana circular.
void registrarTemperatura(float motorTemp, uint32_t ahora) {
  termTemp[termCabeza] = motorTemp;
  termMs[termCabeza] = ahora;
  termCabeza = (uint8_t)((termCabeza + 1) % TERM_N);
  if (termLlenado < TERM_N) termLlenado++;
}

// Pendiente de la temperatura del motor en grados por minuto, por minimos
// cuadrados sobre las lecturas de la ventana. Devuelve 0 si no hay suficientes:
// no es una estimacion neutra, pero es lo que el analisis hace en ese caso.
float gradienteMotor(uint32_t ahora) {
  const uint32_t desde = ahora - (uint32_t)MODELO_VENTANA_GRADIENTE_S * 1000UL;
  double sx = 0, sy = 0, sxx = 0, sxy = 0;
  uint16_t n = 0;
  for (uint8_t i = 0; i < termLlenado; i++) {
    if (termMs[i] < desde || termMs[i] > ahora) continue;
    const double x = ((double)termMs[i] - (double)ahora) / 1000.0;   // segundos
    const double y = (double)termTemp[i];
    sx += x; sy += y; sxx += x * x; sxy += x * y;
    n++;
  }
  if (n < 5) return 0.0f;
  const double den = (double)n * sxx - sx * sx;
  if (den == 0.0) return 0.0f;
  return (float)((((double)n * sxy - sx * sy) / den) * 60.0);   // por minuto
}

// Temporizadores y estado
uint32_t lastSlow = 0;
uint32_t lastBurst = 0;
bool tempConversionRequested = false;
float cachedExtTemp = DEVICE_DISCONNECTED_C;
uint32_t failedBursts = 0;    // ráfagas descartadas por fallo del bus
uint32_t badFrames = 0;       // tramas del canal lento descartadas
uint32_t totalRetries = 0;    // reintentos de lectura acumulados
uint32_t totalContRejects = 0;  // rechazos por salto de continuidad acumulados
// Ráfagas que SÍ se calcularon (capturaron y procesaron con éxito) pero no se
// publicaron porque el cliente MQTT no estaba conectado en el instante de
// publicar. A diferencia de failedBursts (fallo del bus I2C durante la
// captura), aquí la señal existe y se descarta solo por falta de enlace: es
// la carencia de instrumentación que dejaba huecos de 102 s y 73 s entre
// ráfagas sin que ningún contador se moviera. Como la ráfaga perdida nunca
// llega al broker, este contador acumulado solo puede verse reflejado en la
// SIGUIENTE ráfaga que sí se publique.
uint32_t unpublishedBursts = 0;

// Diagnóstico del primer rechazo por continuidad de cada ráfaga: se guarda
// para imprimirlo DESPUÉS de completar las 1024 muestras, nunca dentro del
// bucle de captura, que debe permanecer determinista en tiempo (ver cabecera
// del fichero). Sirve para distinguir en campo si la causa es EMI, un
// conector suelto o una lectura no atómica del sensor, sin resolverlo aquí.
bool contRejectLogged = false;
int16_t contRejectX = 0, contRejectY = 0, contRejectZ = 0;
int16_t contRejectPrevX = 0, contRejectPrevY = 0, contRejectPrevZ = 0;

void setupI2S() {
  const i2s_config_t i2s_config = {
    .mode = i2s_mode_t(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = AUDIO_FS,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = i2s_comm_format_t(I2S_COMM_FORMAT_STAND_I2S),
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 256,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  const i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD
  };

  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_config);
}

void setupWifi() {
  Serial.println();
  Serial.print("Conectando a Wi-Fi (SSID: ");
  Serial.print(WIFI_SSID);
  Serial.println(")...");

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("");
    Serial.println("✓ Wi-Fi conectado exitosamente.");
    Serial.print("Dirección IP del ESP32: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("");
    Serial.print("✗ No se pudo conectar a la red. Código de estado: ");
    int status = WiFi.status();
    Serial.print(status);
    switch (status) {
      case WL_NO_SSID_AVAIL:
        Serial.println(" (Red no encontrada. Verifica el SSID y que sea 2.4 GHz)");
        break;
      case WL_CONNECT_FAILED:
        Serial.println(" (Fallo de autenticación. Verifica la contraseña)");
        break;
      case WL_DISCONNECTED:
        Serial.println(" (Desconectado)");
        break;
      default:
        Serial.println(" (Error desconocido al asociar con el AP)");
        break;
    }
  }
}

void reconnect() {
  if (WiFi.status() != WL_CONNECTED) return;

  if (!client.connected()) {
    Serial.print("Intentando conexión MQTT a ");
    Serial.print(MQTT_SERVER);
    Serial.println("...");
    String clientId = "ESP32-Fridge-";
    clientId += String(random(0xffff), HEX);

    if (client.connect(clientId.c_str())) {
      Serial.println("✓ ¡Conectado al servidor MQTT!");
    } else {
      Serial.print("✗ Fallo MQTT, rc=");
      Serial.print(client.state());
      Serial.println(" (reintentará en el siguiente ciclo)");
    }
  }
}

// ---------------------------------------------------------------------
// Rutina de recuperación del bus I2C.
// Se ejecuta SOLO cuando detectamos que una lectura real ha fallado.
// Resetea físicamente el bus y reconfigura el MPU6050.
// ---------------------------------------------------------------------
bool recoverI2C() {
  Serial.println("⚠ Bus I2C atascado. Intentando recuperación...");
  Wire.end();
  delay(100);
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(I2C_FREQ_HZ);

  if (mpu.begin()) {
    mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
    mpu.setFilterBandwidth(MPU6050_BAND_260_HZ);
    mpu.setSampleRateDivisor(0);
    delay(50);
    updateGyroScale();          // begin() reprograma el rango
    Serial.println("✓ Bus I2C recuperado con éxito.");
    return true;
  }
  Serial.println("✗ Fallo crítico: no se pudo recuperar el bus I2C.");
  return false;
}

// ---------------------------------------------------------------------
// Lectura validada de n registros consecutivos del MPU.
//
// Es el único punto del firmware que habla con el acelerómetro, y valida
// la transacción en cuatro puntos, porque la vibración del compresor
// provoca microcortes y ninguna de las capas de arriba avisa por su
// cuenta:
//
//   1. endTransmission(true) fuerza un STOP en lugar de un repeated
//      start. La implementación I2C del ESP32 falla con repeated starts
//      y ahí se originaban los "unexpected nack detected".
//   2. requestFrom() puede devolver la cuenta pedida aunque la
//      transacción de abajo haya fracasado (el driver lo registra como
//      "i2c_master_transmit_receive failed" pero no lo propaga).
//   3. Por eso se comprueba available(): con el buffer vacío,
//   4. Wire.read() devuelve -1, que al truncarse a uint8_t se convertía
//      en 0xFF sin que nada lo detectase. Los tres ejes salían como
//      0xFFFF = -1 y esa muestra basura se publicaba como medida válida,
//      disparando la kurtosis de 2,7 a 847. Verificado en la placa con
//      los campos de diagnóstico dbg_*.
//
// Devuelve false ante cualquiera de los cuatro casos: es responsabilidad
// de quien llama decidir si reintenta o descarta.
// ---------------------------------------------------------------------
inline bool readRegisters(uint8_t reg, uint8_t* dest, uint8_t n) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(true) != 0) return false;
  if (Wire.requestFrom(MPU_ADDR, n) != n) return false;
  if (Wire.available() < n) return false;

  for (uint8_t i = 0; i < n; i++) {
    int b = Wire.read();
    if (b < 0) return false;
    dest[i] = (uint8_t)b;
  }
  return true;
}

// Lee del chip el rango configurado del giróscopo y ajusta el factor de
// escala. Se llama al configurar y tras cada recuperación del bus, porque
// mpu.begin() reprograma el rango. Si la lectura falla se conserva el
// factor anterior: es mejor una escala posiblemente vieja que una escala
// inventada.
void updateGyroScale() {
  uint8_t cfg;
  if (!readRegisters(MPU_GYRO_CONFIG, &cfg, 1)) {
    Serial.println("⚠ No se pudo leer GYRO_CONFIG; se mantiene la escala anterior.");
    return;
  }
  const float lsbPerDps[4] = {131.0f, 65.5f, 32.8f, 16.4f};   // hoja de características
  const uint16_t rangeDps[4] = {250, 500, 1000, 2000};
  uint8_t fsSel = (cfg >> 3) & 0x03;
  gyroLsbToRads = (1.0f / lsbPerDps[fsSel]) * DPS_TO_RADS;

  Serial.print("Rango del giroscopo leido del chip: +-");
  Serial.print(rangeDps[fsSel]);
  Serial.print(" grados/s (");
  Serial.print(lsbPerDps[fsSel], 1);
  Serial.println(" LSB por grado/s)");
}

// Comprueba que el vector de aceleración es físicamente posible. Atrapa
// la basura que sí supera la validación de la transacción: valores
// saturados, ceros o mezclas de bytes de dos muestras distintas.
// Trabaja en cuentas crudas para no convertir a m/s^2 en el bucle de la
// ráfaga. Sin dependencias de Arduino: verificable en el PC.
inline bool isPlausibleRaw(int16_t x, int16_t y, int16_t z) {
  float mag2 = (float)x * (float)x + (float)y * (float)y + (float)z * (float)z;
  return mag2 >= ACC_MAG2_MIN_LSB && mag2 <= ACC_MAG2_MAX_LSB;
}

// Comprueba que la muestra candidata es alcanzable físicamente desde la
// última muestra aceptada del mismo eje, dado el periodo de 1 ms de la
// ráfaga (ver justificación física de ACC_STEP_MAX_MS2 más arriba). Segunda
// línea de defensa tras isPlausibleRaw(): esta atrapa la caída de UN solo
// eje que el módulo total no ve porque los otros dos la compensan. Trabaja
// en cuentas crudas, igual que isPlausibleRaw(), y sin dependencias de
// Arduino: verificable en el PC.
inline bool isContinuous(int16_t x, int16_t y, int16_t z,
                          int16_t prevX, int16_t prevY, int16_t prevZ) {
  float dx = fabsf((float)x - (float)prevX);
  float dy = fabsf((float)y - (float)prevY);
  float dz = fabsf((float)z - (float)prevZ);
  return dx <= ACC_STEP_MAX_LSB && dy <= ACC_STEP_MAX_LSB && dz <= ACC_STEP_MAX_LSB;
}

// Lectura de los tres ejes del acelerómetro para la ráfaga.
//
// Se leen exactamente 6 bytes. Se probó a leer 8 (descartando los dos de
// temperatura) por si la muestra corrupta que aparecía en el eje Z fuese
// un efecto posicional de la cola de la transacción, pero no hizo falta:
// validar la transacción y reintentar una vez ya elimina el problema
// (kurtosis de 900 a 3,3, medido en la placa). Y leer 8 bytes deja el
// reintento en ~1010 us, por encima del periodo de muestreo de 1000 us.
//
// hasPrev/prevX/prevY/prevZ son la última muestra ACEPTADA de la ráfaga:
// para la primera muestra (i==0) no hay continuidad que comprobar y se
// pasa hasPrev=false. contFail distingue, para quien llama, si un rechazo
// vino del módulo o de la continuidad, sin duplicar el bloque de reintento
// entre las dos comprobaciones.
inline bool readRawAccel(int16_t &x, int16_t &y, int16_t &z,
                          bool hasPrev, int16_t prevX, int16_t prevY, int16_t prevZ,
                          bool &contFail) {
  contFail = false;
  uint8_t b[6];
  if (!readRegisters(MPU_ACCEL_XOUT, b, 6)) return false;

  // Variables intermedias a propósito: el orden de evaluación de los
  // operandos de | no está especificado en C++, y montar el entero
  // directamente desde dos read() podría intercambiar los bytes.
  x = (int16_t)(((uint16_t)b[0] << 8) | b[1]);
  y = (int16_t)(((uint16_t)b[2] << 8) | b[3]);
  z = (int16_t)(((uint16_t)b[4] << 8) | b[5]);
  if (!isPlausibleRaw(x, y, z)) return false;
  if (hasPrev && !isContinuous(x, y, z, prevX, prevY, prevZ)) {
    contFail = true;
    return false;
  }
  return true;
}

// Lectura del bloque completo del MPU en una sola transacción:
// aceleración (0x3B), temperatura (0x41) y giróscopo (0x43), 14 bytes
// consecutivos. Sustituye a mpu.getEvent(), que devuelve true de forma
// incondicional y trabaja sobre un buffer de pila sin inicializar: si la
// lectura I2C fallaba, publicaba la basura que hubiera en la pila como
// medida (se observó accY = -38,25 y motorTemp = 61,18).
inline bool readMpuBlock(int16_t &ax, int16_t &ay, int16_t &az, int16_t &t,
                         int16_t &gx, int16_t &gy, int16_t &gz) {
  uint8_t b[14];
  if (!readRegisters(MPU_ACCEL_XOUT, b, 14)) return false;

  ax = (int16_t)(((uint16_t)b[0]  << 8) | b[1]);
  ay = (int16_t)(((uint16_t)b[2]  << 8) | b[3]);
  az = (int16_t)(((uint16_t)b[4]  << 8) | b[5]);
  t  = (int16_t)(((uint16_t)b[6]  << 8) | b[7]);
  gx = (int16_t)(((uint16_t)b[8]  << 8) | b[9]);
  gy = (int16_t)(((uint16_t)b[10] << 8) | b[11]);
  gz = (int16_t)(((uint16_t)b[12] << 8) | b[13]);
  return isPlausibleRaw(ax, ay, az);
}

// ---------------------------------------------------------------------
// Captura una ráfaga de VIB_N muestras a VIB_FS.
//
// contRejects cuenta cuántas de esas muestras fallaron específicamente por
// el salto de continuidad (no por módulo ni por fallo de la transacción
// I2C), para poder distinguir en campo si la corrupción viene de EMI, de un
// conector suelto o de una lectura no atómica del sensor. Es un contador de
// diagnóstico: no se toca el mecanismo de reintento existente, solo se le
// añade una segunda condición de rechazo que reutiliza el mismo bloque.
// ---------------------------------------------------------------------
bool captureVibrationBurst(uint16_t &retries, uint16_t &contRejects) {
  retries = 0;
  contRejects = 0;
  contRejectLogged = false;
  uint32_t nextTick = micros();

  for (uint16_t i = 0; i < VIB_N; i++) {
    // La continuidad solo se comprueba contra la muestra ANTERIOR ACEPTADA
    // de esta misma ráfaga (burst[i-1]); para i==0 no hay tal muestra
    // dentro de la ráfaga, así que se omite solo en ese primer punto.
    bool hasPrev = (i > 0);
    int16_t prevX = hasPrev ? burstX[i - 1] : 0;
    int16_t prevY = hasPrev ? burstY[i - 1] : 0;
    int16_t prevZ = hasPrev ? burstZ[i - 1] : 0;
    bool contFail = false;

    if (!readRawAccel(burstX[i], burstY[i], burstZ[i],
                       hasPrev, prevX, prevY, prevZ, contFail)) {
      // Un fallo aislado se reintenta una vez dentro del mismo hueco
      // temporal. A 200 kHz una lectura cuesta ~420 us de los 1000 us
      // disponibles, asi que el reintento cabe sin romper la cadencia. Sin el,
      // con una tasa de fallo del 0,1 % por lectura solo sobreviviria el 36 %
      // de las rafagas (0,999^1024); con el, practicamente todas.
      //
      // Coste: esa muestra queda ~420 us desplazada. Queda declarado en el
      // campo retries para poder filtrar en el analisis.
      if (contFail) {
        contRejects++;
        totalContRejects++;
        if (!contRejectLogged) {
          // Se guarda solo el primer rechazo de la ráfaga; imprimirlo
          // aquí dentro del bucle introduciría jitter en el espectro.
          contRejectLogged = true;
          contRejectX = burstX[i];
          contRejectY = burstY[i];
          contRejectZ = burstZ[i];
          contRejectPrevX = prevX;
          contRejectPrevY = prevY;
          contRejectPrevZ = prevZ;
        }
      }
      retries++;
      totalRetries++;
      bool contFail2 = false;
      if (!readRawAccel(burstX[i], burstY[i], burstZ[i],
                         hasPrev, prevX, prevY, prevZ, contFail2)) {
        // Dos fallos seguidos no son un glitch: el bus está caído (ya sea
        // por módulo o por continuidad). Se descarta la ráfaga entera,
        // porque una señal con un hueco produce un espectro sin sentido.
        recoverI2C();
        return false;
      }
    }

    nextTick += VIB_PERIOD_US;
    int32_t remaining = (int32_t)(nextTick - micros());
    // Si sale negativa, la lectura tardó más que el periodo y la cadencia
    // real no es la nominal. Queda reflejado en ms_capture.
    if (remaining > 0) delayMicroseconds((uint32_t)remaining);
  }
  return true;
}

AxisFeatures analyzeRawAxis(const int16_t* raw) {
  for (uint16_t i = 0; i < VIB_N; i++) {
    floatSamples[i] = (float)raw[i] * LSB_TO_MS2;
  }
  return analyzeAxis(floatSamples, VIB_N, (float)VIB_FS, workRe, workIm,
                     2.0f, VIB_LP_CUTOFF_HZ);
}

// ---------------------------------------------------------------------
// Publica el canal lento: nueve variables instantáneas.
// ---------------------------------------------------------------------
void publishSlowChannel() {
  if (tempConversionRequested) {
    cachedExtTemp = tempSensor.getTempCByIndex(0);
  }
  tempSensor.requestTemperatures();
  tempConversionRequested = true;

  // Los ceros son el centinela de "ausencia de dato" que documenta
  // docs/DATA_SCHEMA.md: un accZ de 0,00 exacto es físicamente imposible
  // con el sensor sano, porque la gravedad no se apaga.
  float accX = 0, accY = 0, accZ = 0;
  float gyroX = 0, gyroY = 0, gyroZ = 0;
  float motorTemp = 0;

  int16_t rax, ray, raz, rt, rgx, rgy, rgz;
  if (readMpuBlock(rax, ray, raz, rt, rgx, rgy, rgz)) {
    accX = (float)rax * LSB_TO_MS2;
    accY = (float)ray * LSB_TO_MS2;
    accZ = (float)raz * LSB_TO_MS2;
    gyroX = (float)rgx * gyroLsbToRads;
    gyroY = (float)rgy * gyroLsbToRads;
    gyroZ = (float)rgz * gyroLsbToRads;
    motorTemp = ((float)rt / 340.0f) + 36.53f;   // hoja de características
    // Alimenta la ventana térmica del detector. Va aquí y no en el canal de
    // ráfaga porque la pendiente exige un histórico a 1 Hz, y esta es la única
    // rutina que lo tiene.
    registrarTemperatura(motorTemp, millis());
    if (cachedExtTemp > -100.0f) {
      ultimoDifTermico = motorTemp - cachedExtTemp;
      difTermicoValido = true;
    }
  } else {
    // La trama se descarta y el descarte se declara en bad_frames del
    // canal de ráfaga. Nunca en silencio: un dato perdido que no se
    // cuenta es indistinguible de un dato bueno en el análisis.
    badFrames++;
    Serial.println("⚠ Trama del canal lento descartada: lectura no válida.");
    recoverI2C();
  }

  size_t bytesRead = 0;
  int32_t buffer[64];
  i2s_read(I2S_PORT, &buffer, sizeof(buffer), &bytesRead, portMAX_DELAY);
  long noiseLevel = 0;
  uint32_t numSamples = bytesRead / 4;
  if (numSamples > 0) {
    for (uint32_t i = 0; i < numSamples; i++) noiseLevel += abs(buffer[i] >> 14);
    noiseLevel = noiseLevel / (long)numSamples;
  }

  snprintf(payload, sizeof(payload),
    "{\"tempExt\":%.2f,\"accX\":%.2f,\"accY\":%.2f,\"accZ\":%.2f,"
    "\"gyroX\":%.2f,\"gyroY\":%.2f,\"gyroZ\":%.2f,\"motorTemp\":%.2f,"
    "\"noise\":%ld}",
    cachedExtTemp, accX, accY, accZ, gyroX, gyroY, gyroZ, motorTemp, noiseLevel);

  Serial.print("Lecturas -> ");
  Serial.println(payload);

  if (client.connected()) {
    client.publish(TOPIC_SLOW, payload);
  }
}

// ---------------------------------------------------------------------
// Publica el canal de ráfaga: características espectrales y temporales.
// ---------------------------------------------------------------------
// Prototipo explícito: el preprocesador de Arduino inserta los prototipos
// generados ANTES de las definiciones de tipo del usuario, de modo que una
// función con un parámetro de tipo propio no compila sin declararla a mano.
void publishStatus(const AxisFeatures& fx, const float* energy,
                   uint16_t retries, uint16_t contRejects);

void publishBurst() {
  uint32_t start = millis();

  uint16_t retries = 0;
  uint16_t contRejects = 0;
  if (!captureVibrationBurst(retries, contRejects)) {
    failedBursts++;
    Serial.println("✗ Ráfaga descartada: fallo del bus I2C durante la captura.");
    return;
  }
  uint32_t msCapture = millis() - start;

  // Diagnóstico fuera del bucle de captura a propósito (ver comentario de
  // captureVibrationBurst): solo se imprime el primer rechazo por
  // continuidad de la ráfaga, para no meter jitter en el muestreo.
  if (contRejectLogged) {
    Serial.print("⚠ Rechazo por continuidad -> muestra=(");
    Serial.print(contRejectX); Serial.print(",");
    Serial.print(contRejectY); Serial.print(",");
    Serial.print(contRejectZ); Serial.print(") anterior=(");
    Serial.print(contRejectPrevX); Serial.print(",");
    Serial.print(contRejectPrevY); Serial.print(",");
    Serial.print(contRejectPrevZ); Serial.println(") [cuentas crudas LSB]");
  }

  AxisFeatures fx = analyzeRawAxis(burstX);
  AxisFeatures fy = analyzeRawAxis(burstY);
  AxisFeatures fz = analyzeRawAxis(burstZ);

  size_t bytesRead = 0;
  i2s_read(I2S_PORT, rawAudio, sizeof(rawAudio), &bytesRead, portMAX_DELAY);
  uint16_t numAudio = (uint16_t)(bytesRead / 4);
  float energy[4] = {0, 0, 0, 0};
  float audioRms = 0.0f;
  if (numAudio >= AUDIO_N) {
    for (uint16_t i = 0; i < AUDIO_N; i++) {
      floatSamples[i] = (float)(rawAudio[i] >> 14);
    }
    AxisFeatures fa = analyzeAxis(floatSamples, AUDIO_N, (float)AUDIO_FS,
                                 workRe, workIm, 20.0f);
    audioRms = fa.rms;
    bandEnergy(floatSamples, AUDIO_N, (float)AUDIO_FS,
               workRe, workIm, AUDIO_EDGES, 4, energy);
  }

  uint32_t msTotal = millis() - start;

  snprintf(payload, sizeof(payload),
    "{\"vib_fs\":%u,\"vib_n\":%u,\"ms_capture\":%u,\"ms_total\":%u,"
    "\"failed_bursts\":%u,\"bad_frames\":%u,"
    "\"retries\":%u,\"total_retries\":%u,"
    "\"cont_rejects\":%u,\"total_cont_rejects\":%u,"
    "\"unpublished_bursts\":%u,"
    "\"rms_x\":%.4f,\"rms_y\":%.4f,\"rms_z\":%.4f,"
    "\"peak_x\":%.4f,\"peak_y\":%.4f,\"peak_z\":%.4f,"
    "\"kurt_x\":%.3f,\"kurt_y\":%.3f,\"kurt_z\":%.3f,"
    "\"fdom_x\":%.2f,\"fdom_y\":%.2f,\"fdom_z\":%.2f,"
    "\"adom_x\":%.4f,\"adom_y\":%.4f,\"adom_z\":%.4f,"
    "\"f2_x\":%.2f,\"f2_y\":%.2f,\"f2_z\":%.2f,"
    "\"a2_x\":%.4f,\"a2_y\":%.4f,\"a2_z\":%.4f,"
    "\"f3_x\":%.2f,\"f3_y\":%.2f,\"f3_z\":%.2f,"
    "\"a3_x\":%.4f,\"a3_y\":%.4f,\"a3_z\":%.4f,"
    "\"aud_fs\":%u,\"aud_n\":%u,\"aud_rms\":%.2f,"
    "\"aud_b0\":%.4f,\"aud_b1\":%.4f,\"aud_b2\":%.4f,\"aud_b3\":%.4f}",
    (unsigned)VIB_FS, (unsigned)VIB_N, (unsigned)msCapture, (unsigned)msTotal,
    (unsigned)failedBursts, (unsigned)badFrames,
    (unsigned)retries, (unsigned)totalRetries,
    (unsigned)contRejects, (unsigned)totalContRejects,
    (unsigned)unpublishedBursts,
    fx.rms, fy.rms, fz.rms,
    fx.peak, fy.peak, fz.peak,
    fx.kurtosis, fy.kurtosis, fz.kurtosis,
    fx.domFreq, fy.domFreq, fz.domFreq,
    fx.domAmp, fy.domAmp, fz.domAmp,
    fx.freq2, fy.freq2, fz.freq2,
    fx.amp2,  fy.amp2,  fz.amp2,
    fx.freq3, fy.freq3, fz.freq3,
    fx.amp3,  fy.amp3,  fz.amp3,
    (unsigned)AUDIO_FS, (unsigned)numAudio, audioRms,
    energy[0], energy[1], energy[2], energy[3]);

  Serial.print("Ráfaga  -> ");
  Serial.println(payload);

  if (client.connected()) {
    client.publish(TOPIC_BURST, payload);
  } else {
    // La ráfaga ya se calculó (captura + características), pero no hay enlace
    // MQTT en este instante: se pierde sin remedio, igual que si nunca se
    // hubiera medido. Solo queda constancia de ello en el contador, que se
    // publicará en la siguiente ráfaga que sí llegue al broker.
    unpublishedBursts++;
  }

  publishStatus(fx, energy, retries, contRejects);
}

// ---------------------------------------------------------------------
// Emite el veredicto de salud del activo en TOPIC_STATUS.
//
// Es el objetivo del TFM: el diagnóstico ocurre en el nodo. Un consumidor que
// solo quiera saber el estado recibe un mensaje corto en lugar de las 46
// características, y el nodo no depende de que nadie analice nada aguas arriba.
//
// Solo el eje X: es el único cuya kurtosis se mantiene en rango físico en el
// 100 % de las ráfagas de los dos activos medidos.
// ---------------------------------------------------------------------
void publishStatus(const AxisFeatures& fx, const float* energy,
                   uint16_t retries, uint16_t contRejects) {
  MedidaRafaga m;
  m.rms = fx.rms;   m.peak = fx.peak;  m.kurt = fx.kurtosis;
  m.fdom = fx.domFreq; m.adom = fx.domAmp;
  m.f2 = fx.freq2;  m.a2 = fx.amp2;
  m.f3 = fx.freq3;  m.a3 = fx.amp3;
  m.audB0 = energy[0]; m.audB1 = energy[1]; m.audB2 = energy[2];
  m.difTermico = ultimoDifTermico;
  m.gradMotor = gradienteMotor(millis());
  m.retries = retries;
  m.contRejects = contRejects;

  uint32_t t0 = micros();

  // El nodo se NIEGA a juzgar antes que juzgar mal. Los reintentos del bus
  // fabrican la firma del fallo sobre un activo sano: con más de diez, el
  // número de picos significativos de un activo NOMINAL pasa de 1 a 3 y la
  // fundamental estimada se derrumba de 49 Hz a 20 Hz. Y con el compresor
  // detenido no hay vibración que analizar.
  const bool evaluable = rafagaEvaluable(m) && difTermicoValido;

  Veredicto v = VEREDICTO_NO_EVALUABLE;
  float sLof = 0.0f, sEnv = 0.0f;
  uint8_t nPicos = 0;

  if (evaluable) {
    float x[MODELO_N_CARACTERISTICAS], z[MODELO_N_CARACTERISTICAS];
    derivarCaracteristicas(m, x);
    nPicos = (uint8_t)(x[6] + 0.5f);
    normalizar(x, z);
    sEnv = puntuarEnvolvente(z);
#ifndef MODELO_SIN_LOF
    sLof = puntuarLOF(z);
    // El detector principal es LOF: es el modelo que seleccionó el protocolo
    // libre de sesgo de espionaje (server/analisis/protocolo.py), y cubre las
    // cinco direcciones de fallo examinadas frente a una de la regla de picos.
    v = (sLof < MODELO_LOF_UMBRAL) ? VEREDICTO_ANOMALIA : VEREDICTO_NOMINAL;
#else
    v = (sEnv < MODELO_ENV_UMBRAL) ? VEREDICTO_ANOMALIA : VEREDICTO_NOMINAL;
#endif
  }

  const bool notificar = histeresis.actualizar(v);
  uint32_t usInferencia = micros() - t0;

  // Se publican las tres puntuaciones y no solo el veredicto. El motivo es que
  // los tres indicadores dicen cosas distintas: la envolvente señala que el
  // estado se ha alejado del de referencia, y la cuenta de picos que la
  // desviación es una familia armónica. Con los tres, la discrepancia entre
  // ellos es diagnosticable a posteriori; con uno solo, no.
  const char* etiqueta = (v == VEREDICTO_ANOMALIA)  ? "anomaly"
                       : (v == VEREDICTO_NOMINAL)   ? "nominal"
                                                    : "not_evaluable";
  snprintf(payload, sizeof(payload),
    "{\"health\":\"%s\",\"streak\":%u,\"notify\":%u,"
    "\"lof\":%.4f,\"env\":%.2f,\"n_peaks\":%u,"
    "\"us_inference\":%u}",
    etiqueta, (unsigned)histeresis.consecutivas, notificar ? 1u : 0u,
    sLof, sEnv, (unsigned)nPicos, (unsigned)usInferencia);

  Serial.print("Estado  -> ");
  Serial.println(payload);

  if (client.connected()) {
    client.publish(TOPIC_STATUS, payload);
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("Iniciando Sistema de Mantenimiento Predictivo...");

  setupWifi();
  client.setServer(MQTT_SERVER, MQTT_PORT);
  // 1408 B: payload de 1152 B más el topic y la cabecera del PUBLISH.
  client.setBufferSize(1408);
  histeresis.inicializar(DET_RAFAGAS_CONSECUTIVAS);
  Serial.print("Detector: ");
  Serial.print(MODELO_N_CARACTERISTICAS);
  Serial.print(" caracteristicas, veredicto en ");
  Serial.println(TOPIC_STATUS);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(I2C_FREQ_HZ);

  tempSensor.begin();
  tempSensor.setWaitForConversion(false);

  if (!mpu.begin()) {
    Serial.println("Aviso: MPU6050 no detectado al inicio.");
  } else {
    mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
    mpu.setFilterBandwidth(MPU6050_BAND_260_HZ);
    mpu.setSampleRateDivisor(0);
  }
  updateGyroScale();

  setupI2S();
  Serial.println("¡Sensores listos!");
  Serial.print("Ráfaga de vibración: ");
  Serial.print(VIB_N);
  Serial.print(" muestras a ");
  Serial.print(VIB_FS);
  Serial.print(" Hz (resolución ");
  Serial.print((float)VIB_FS / VIB_N, 2);
  Serial.println(" Hz)");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    setupWifi();
  }
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  uint32_t now = millis();

  if (now - lastSlow >= SLOW_PERIOD_MS) {
    lastSlow = now;
    publishSlowChannel();
  }

  if (now - lastBurst >= BURST_PERIOD_MS) {
    lastBurst = now;
    publishBurst();
    client.loop();
  }
}
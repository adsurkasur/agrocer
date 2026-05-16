#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>
#include <BH1750.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// =========================
// WIFI
// =========================
// WiFi choices (try in order; will pick a present SSID)
const char* wifiSSIDs[] = {"Adsur B20", "ades24"};
const char* wifiPasswords[] = {"adsurananda", "ngajioke"};
const int wifiCount = sizeof(wifiSSIDs) / sizeof(wifiSSIDs[0]);

// =========================
// FLASK SERVER
// =========================
const char* serverURL =
  "https://agrocermut.adsurkasur.my.id/api/sensor";

// =========================
// DHT22
// =========================
#define DHTPIN 4
#define DHTTYPE DHT22

DHT dht(DHTPIN, DHTTYPE);

// =========================
// RELAY
// =========================
#define RELAY_POMPA 26
#define RELAY_KIPAS 27

// =========================
// LCD
// =========================
LiquidCrystal_I2C lcd(0x27, 16, 2);

// =========================
// BH1750
// =========================
BH1750 lightMeter;

// =========================
// DATA SENSOR
// =========================
float suhu = 0;
float hum  = 0;
float lux  = 0;

// =========================
// THRESHOLDS & ACTUATORS
// =========================
float FAN_ON_TEMP       = 30.0;
float FAN_OFF_TEMP      = 28.0;
float PUMP_ON_HUMIDITY  = 40.0;
float PUMP_OFF_HUMIDITY = 45.0;

int fan_status  = 0;  // 0 = OFF, 1 = ON
int pump_status = 0;  // 0 = OFF, 1 = ON

unsigned long fan_last_changed  = 0;
unsigned long pump_last_changed = 0;

// =========================
// TIMER
// =========================
unsigned long lastSensor = 0;
unsigned long lastLCD = 0;
unsigned long lastHTTP = 0;
unsigned long lastWiFiRetry = 0;

// =========================
// WIFI CONNECT
// =========================
void connectWiFi() {

  // Ensure station mode and clear previous connections
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(100);

  // Scan for available networks and pick the first preferred SSID present
  Serial.println("Scanning for WiFi networks...");
  int n = WiFi.scanNetworks();
  Serial.printf("Scan found %d networks\n", n);

  int chosen = -1;

  // Prefer the first configured SSID (index 0)
  for (int i = 0; i < n; i++) {
    if (WiFi.SSID(i) == String(wifiSSIDs[0])) {
      chosen = 0;
      break;
    }
  }

  // If primary not found, search other configured SSIDs in order
  if (chosen == -1) {
    for (int j = 1; j < wifiCount; j++) {
      for (int i = 0; i < n; i++) {
        if (WiFi.SSID(i) == String(wifiSSIDs[j])) {
          chosen = j;
          break;
        }
      }
      if (chosen != -1) break;
    }
  }

  // Default to primary if none found
  if (chosen == -1) chosen = 0;

  Serial.print("Attempting WiFi SSID: '");
  Serial.print(wifiSSIDs[chosen]);
  Serial.println("'");

  WiFi.begin(wifiSSIDs[chosen], wifiPasswords[chosen]);

  unsigned long wifiStart = millis();

  // Give a bit more time for networks with spaces or slower AP responses
  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - wifiStart < 20000
  ) {

    delay(500);
    Serial.print(".");
  }

  Serial.println("");

  if (WiFi.status() == WL_CONNECTED) {

    Serial.println("WiFi Connected");
    Serial.println(WiFi.localIP());

    // Disable WiFi sleep
    WiFi.setSleep(false);

  } else {

    Serial.println("WiFi Failed");
    Serial.println("Running Offline Mode");

    // Diagnostic: print scanned networks for debugging
    for (int i = 0; i < n; i++) {
      Serial.printf(" %d: %s (%d)\n", i + 1, WiFi.SSID(i).c_str(), WiFi.RSSI(i));
    }
  }
}

// =========================
// SETUP
// =========================
void setup() {

  // Serial for diagnostics
  Serial.begin(115200);

  // =========================
  // WIFI
  // =========================
  connectWiFi();

  // =========================
  // I2C
  // =========================
  Wire.begin(21, 22);
  // Lower I2C clock for stability
  Wire.setClock(50000);

  // =========================
  // SENSOR
  // =========================
  dht.begin();

  lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);

  // =========================
  // LCD
  // =========================
  lcd.init();
  lcd.backlight();

  // =========================
  // RELAY
  // =========================
  pinMode(RELAY_POMPA, OUTPUT);
  pinMode(RELAY_KIPAS, OUTPUT);

  // Relay OFF
  digitalWrite(RELAY_POMPA, HIGH);
  digitalWrite(RELAY_KIPAS, HIGH);

  // =========================
  // SPLASH SCREEN
  // =========================
  lcd.setCursor(0, 0);
  lcd.print("SMART FARMING");

  lcd.setCursor(0, 1);
  lcd.print("SYSTEM READY");

  delay(1500);

  // Clear once only
  lcd.clear();
}

// =========================
// LOOP
// =========================
void loop() {

  // =========================
  // WIFI AUTO RECONNECT
  // =========================
  if (
    WiFi.status() != WL_CONNECTED &&
    millis() - lastWiFiRetry >= 10000
  ) {

    lastWiFiRetry = millis();

    Serial.println(
      "Reconnecting WiFi..."
    );

    WiFi.disconnect();

    connectWiFi();
  }

  // =========================
  // SENSOR READ
  // =========================
  if (
    millis() - lastSensor >= 1000
  ) {

    lastSensor = millis();

    float t =
      dht.readTemperature();

    float h =
      dht.readHumidity();

    float l =
      lightMeter.readLightLevel();

    // =========================
    // VALIDATION
    // =========================
    if (!isnan(t)) {

      if (t > -10 && t < 80) {

        suhu = t;
      }
    }

    if (!isnan(h)) {

      if (h >= 0 && h <= 100) {

        hum = h;
      }
    }

    if (l >= 0) {

      lux = l;
    }

    // =========================
    // SERIAL
    // =========================
    Serial.printf(
      "T: %.1f C | H: %.1f %% | L: %.1f lx\n",
      suhu,
      hum,
      lux
    );
  }

  // =========================
  // FAN CONTROL (Hysteresis)
  // =========================
  if (suhu > FAN_ON_TEMP && fan_status == 0) {
    fan_status = 1;
    fan_last_changed = millis();
    digitalWrite(RELAY_KIPAS, LOW); // ON
    Serial.printf("ACTUATOR: Fan ON | Temp: %.1f > %.1f\n", suhu, FAN_ON_TEMP);
  } else if (suhu < FAN_OFF_TEMP && fan_status == 1) {
    fan_status = 0;
    fan_last_changed = millis();
    digitalWrite(RELAY_KIPAS, HIGH); // OFF
    Serial.printf("ACTUATOR: Fan OFF | Temp: %.1f < %.1f\n", suhu, FAN_OFF_TEMP);
  }

  delay(10);

  // =========================
  // PUMP CONTROL (Hysteresis)
  // =========================
  if (hum < PUMP_ON_HUMIDITY && pump_status == 0) {
    pump_status = 1;
    pump_last_changed = millis();
    digitalWrite(RELAY_POMPA, LOW); // ON
    Serial.printf("ACTUATOR: Pump ON | Hum: %.1f < %.1f\n", hum, PUMP_ON_HUMIDITY);
  } else if (hum > PUMP_OFF_HUMIDITY && pump_status == 1) {
    pump_status = 0;
    pump_last_changed = millis();
    digitalWrite(RELAY_POMPA, HIGH); // OFF
    Serial.printf("ACTUATOR: Pump OFF | Hum: %.1f > %.1f\n", hum, PUMP_OFF_HUMIDITY);
  }

  delay(10);

  // =========================
  // SEND TO FLASK (HTTPS)
  // =========================
  if (

    WiFi.status() == WL_CONNECTED &&

    millis() - lastHTTP >= 1000

  ) {

    lastHTTP = millis();

    Serial.print("WiFi status: ");
    Serial.println(WiFi.status());
    Serial.print("Local IP: ");
    Serial.println(WiFi.localIP());

    // Build JSON payload
    String jsonData = "{";
    jsonData += "\"temperature\":" + String(suhu, 1) + ",";
    jsonData += "\"humidity\":" + String(hum, 1) + ",";
    jsonData += "\"lux\":" + String(lux, 1) + ",";
    jsonData += "\"fan_status\":" + String(fan_status) + ",";
    jsonData += "\"pump_status\":" + String(pump_status) + ",";
    jsonData += "\"fan_on_temp\":" + String(FAN_ON_TEMP, 0) + ",";
    jsonData += "\"fan_off_temp\":" + String(FAN_OFF_TEMP, 0) + ",";
    jsonData += "\"pump_on_humidity\":" + String(PUMP_ON_HUMIDITY, 0) + ",";
    jsonData += "\"pump_off_humidity\":" + String(PUMP_OFF_HUMIDITY, 0);
    jsonData += "}";

    // Payload preview
    Serial.println("JSON Payload Preview:");
    Serial.println(jsonData);

    // HTTPS via secure client (Cloudflare Tunnel)
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;

    Serial.print("Beginning HTTPS POST to: ");
    Serial.println(serverURL);

    if (!http.begin(client, serverURL)) {
      Serial.println("HTTP.begin() failed for HTTPS URL");
    } else {

      http.addHeader("Content-Type", "application/json");

      int httpResponseCode = http.POST(jsonData);

      Serial.print("HTTPS response code: ");
      Serial.println(httpResponseCode);

      if (httpResponseCode > 0) {
        String payload = http.getString();
        if (payload.length() > 0) {
          Serial.println("HTTPS response body:");
          Serial.println(payload);
        } else {
          Serial.println("HTTPS response body: <empty>");
        }
      } else {
        Serial.print("HTTPS POST failed, code: ");
        Serial.println(httpResponseCode);
        Serial.print("Error string: ");
        Serial.println(http.errorToString(httpResponseCode));
      }

      http.end();
    }
  }

  // =========================
  // LCD UPDATE
  // =========================
  if (
    millis() - lastLCD >= 1000
  ) {

    lastLCD = millis();

    // =========================
    // LINE 1
    // =========================
    lcd.setCursor(0, 0);

    lcd.print("T:");
    lcd.print(suhu, 1);

    lcd.print((char)223);

    lcd.print("C ");

    lcd.print("H:");

    lcd.print((int)hum);

    lcd.print("% ");

    // Padding overwrite
    lcd.print(" ");

    // =========================
    // LINE 2
    // =========================
    lcd.setCursor(0, 1);

    lcd.print("L:");

    lcd.print((int)lux);

    lcd.print("lx ");

    if (
      WiFi.status() == WL_CONNECTED
    ) {

      lcd.print("ON ");

    } else {

      lcd.print("OFF");
    }

    // Padding overwrite
    lcd.print(" ");
  }

  // =========================
  // ESP32 YIELD
  // =========================
  yield();

  delay(50);
}
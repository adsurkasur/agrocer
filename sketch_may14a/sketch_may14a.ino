#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>
#include <BH1750.h>
#include <WiFi.h>
#include <HTTPClient.h>

// =========================
// WIFI
// =========================
const char* ssid = "Adsur B20";
const char* password = "adsurananda";

// =========================
// FLASK SERVER
// =========================
const char* serverURL =
  "http://172.23.246.31:5000/api/sensor";

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

  WiFi.begin(ssid, password);

  Serial.print("Connecting WiFi");

  unsigned long wifiStart = millis();

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - wifiStart < 10000
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
  }
}

// =========================
// SETUP
// =========================
void setup() {

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

  lightMeter.begin(
    BH1750::CONTINUOUS_HIGH_RES_MODE
  );

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
    millis() - lastSensor >= 3000
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
  // FAN CONTROL
  // =========================
  if (suhu > 29) {

    digitalWrite(
      RELAY_KIPAS,
      LOW
    );

  } else if (suhu < 28) {

    digitalWrite(
      RELAY_KIPAS,
      HIGH
    );
  }

  delay(10);

  // =========================
  // PUMP CONTROL
  // =========================
  if (hum < 75) {

    digitalWrite(
      RELAY_POMPA,
      LOW
    );

  } else if (hum > 80) {

    digitalWrite(
      RELAY_POMPA,
      HIGH
    );
  }

  delay(10);

  // =========================
  // SEND TO FLASK
  // =========================
  if (

    WiFi.status() == WL_CONNECTED &&

    millis() - lastHTTP >= 3000

  ) {

    lastHTTP = millis();

    HTTPClient http;

    http.begin(serverURL);

    http.addHeader(
      "Content-Type",
      "application/json"
    );

    String jsonData = "{";

    jsonData +=
      "\"temperature\":" +
      String(suhu, 1) + ",";

    jsonData +=
      "\"humidity\":" +
      String(hum, 1) + ",";

    jsonData +=
      "\"lux\":" +
      String(lux, 1);

    jsonData += "}";

    int httpResponseCode =
      http.POST(jsonData);

    Serial.print("HTTP: ");
    Serial.println(
      httpResponseCode
    );

    http.end();
  }

  // =========================
  // LCD UPDATE
  // =========================
  if (
    millis() - lastLCD >= 3000
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
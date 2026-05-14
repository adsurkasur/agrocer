from flask import Flask, request, jsonify, render_template
import sqlite3
from datetime import datetime
import requests

app = Flask(__name__)

DATABASE = "sensor.db"


# =========================
# DATABASE INIT
# =========================
def init_db():

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            temperature REAL NOT NULL,
            humidity REAL NOT NULL,
            lux REAL NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# =========================
# INSERT SENSOR DATA
# =========================
def insert_sensor_data(temp, hum, lux):

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO sensor_data
        (timestamp, temperature, humidity, lux)
        VALUES (?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        temp,
        hum,
        lux
    ))

    conn.commit()
    conn.close()


# =========================
# ENVIRONMENT STATUS
# =========================
def get_environment_status(temp, hum):

    if temp < 18:
        temp_status = "COLD"

    elif temp <= 27:
        temp_status = "IDEAL"

    elif temp <= 32:
        temp_status = "HOT"

    else:
        temp_status = "EXTREME HEAT"

    if hum < 50:
        hum_status = "TOO DRY"

    elif hum <= 80:
        hum_status = "IDEAL"

    else:
        hum_status = "TOO HUMID"

    if temp_status == "IDEAL" and hum_status == "IDEAL":
        return "OPTIMAL FOR TOMATO"

    if temp_status == "HOT" and hum_status == "TOO HUMID":
        return "FUNGAL RISK"

    if temp_status == "EXTREME HEAT":
        return "HEAT STRESS"

    if hum_status == "TOO DRY":
        return "WATER STRESS"

    return f"{temp_status} / {hum_status}"


# =========================
# LIGHT STATUS
# =========================
def get_light_status(lux):

    if lux < 50:
        return "VERY LOW LIGHT"

    elif lux < 200:
        return "LOW LIGHT"

    elif lux < 1000:
        return "MODERATE LIGHT"

    elif lux < 25000:
        return "GOOD SUNLIGHT"

    return "INTENSE SUNLIGHT"


# =========================
# RELAY STATUS
# =========================
def get_fan_status(temp):

    return "ON" if temp > 28 else "OFF"


def get_pump_status(hum):

    return "ON" if hum < 60 else "OFF"


# =========================
# OPEN METEO
# =========================
def get_weather_data(lat, lon):

    try:

        url = (

            "https://api.open-meteo.com/v1/forecast"

            f"?latitude={lat}"

            f"&longitude={lon}"

            "&current="

            "temperature_2m,"

            "relative_humidity_2m,"

            "weather_code"
        )

        response = requests.get(url)

        data = response.json()

        current = data["current"]

        weather_code = current["weather_code"]

        if weather_code == 0:
            weather_text = "CLEAR"

        elif weather_code <= 3:
            weather_text = "PARTLY CLOUDY"

        elif weather_code <= 48:
            weather_text = "FOGGY"

        elif weather_code <= 67:
            weather_text = "RAIN"

        elif weather_code <= 77:
            weather_text = "SNOW"

        elif weather_code <= 99:
            weather_text = "STORM"

        else:
            weather_text = "UNKNOWN"

        return {

            "temperature":
                current["temperature_2m"],

            "humidity":
                current["relative_humidity_2m"],

            "weather":
                weather_text
        }

    except Exception as e:

        return {

            "temperature": None,

            "humidity": None,

            "weather": "UNAVAILABLE",

            "error": str(e)
        }


# =========================
# RECEIVE SENSOR
# =========================
@app.route('/api/sensor', methods=['POST'])
def receive_sensor():

    try:

        data = request.get_json()

        temperature = float(data['temperature'])
        humidity = float(data['humidity'])
        lux = float(data['lux'])

        insert_sensor_data(
            temperature,
            humidity,
            lux
        )

        return jsonify({
            "status": "success"
        })

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400


# =========================
# API LATEST
# =========================
@app.route('/api/latest')
def latest_data():

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM sensor_data
        ORDER BY id DESC
        LIMIT 30
    """)

    rows = cursor.fetchall()

    conn.close()

    rows.reverse()

    data = []

    for row in rows:

        temperature = row[2]
        humidity = row[3]
        lux = row[4]

        data.append({

            "id": row[0],
            "timestamp": row[1],
            "temperature": temperature,
            "humidity": humidity,
            "lux": lux,

            "environment_status":
                get_environment_status(
                    temperature,
                    humidity
                ),

            "light_status":
                get_light_status(lux),

            "fan_status":
                get_fan_status(temperature),

            "pump_status":
                get_pump_status(humidity)
        })

    return jsonify(data)


# =========================
# WEATHER API
# =========================
@app.route('/api/weather')
def weather():

    lat = request.args.get('lat')
    lon = request.args.get('lon')

    if not lat or not lon:

        return jsonify({
            "weather": "NO LOCATION"
        })

    return jsonify(
        get_weather_data(lat, lon)
    )


# =========================
# CLEAR DATABASE
# =========================
@app.route('/api/clear', methods=['POST'])
def clear_database():

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM sensor_data"
    )

    cursor.execute("""
        DELETE FROM sqlite_sequence
        WHERE name='sensor_data'
    """)

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": "Database cleared"
    })


# =========================
# DASHBOARD
# =========================
@app.route('/')
def dashboard():

    return render_template('index.html')


# =========================
# MAIN
# =========================
if __name__ == '__main__':

    init_db()

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
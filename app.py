from flask import Flask, request, jsonify, render_template
import sqlite3
from datetime import datetime

app = Flask(__name__)

DATABASE = "sensor.db"


# =========================
# INIT DATABASE
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
# INSERT DATA
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
# API RECEIVE SENSOR
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
# API GET LATEST DATA
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

        data.append({
            "id": row[0],
            "timestamp": row[1],
            "temperature": row[2],
            "humidity": row[3],
            "lux": row[4]
        })

    return jsonify(data)

# =========================
# DASHBOARD
# =========================
@app.route('/')
def dashboard():

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM sensor_data
        ORDER BY id DESC
        LIMIT 50
    """)

    rows = cursor.fetchall()

    conn.close()

    rows.reverse()

    timestamps = [row[1] for row in rows]
    temperatures = [row[2] for row in rows]
    humidities = [row[3] for row in rows]
    luxes = [row[4] for row in rows]

    return render_template(
        'index.html',
        rows=rows,
        timestamps=timestamps,
        temperatures=temperatures,
        humidities=humidities,
        luxes=luxes
    )


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
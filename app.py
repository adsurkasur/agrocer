from flask import Flask, request, jsonify, render_template, send_file
from io import BytesIO
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import requests
import logging
import math
import os
import platform
import sys

from openpyxl import Workbook

app = Flask(__name__)

# -------------------------
# Configuration (pathlib + env-driven)
# -------------------------
BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "sensor.db"

def parse_bool_env(val, default=False):
    if val is None:
        return default
    v = str(val).strip().lower()
    return v in ("1", "true", "yes", "on")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("FLASK_RUN_PORT", "5000")))
DEBUG = parse_bool_env(os.getenv("DEBUG"), False)
MAX_DATA_POINTS = int(os.getenv("MAX_DATA_POINTS", "1000"))
DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "-7.956"))
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "112.6159"))

# -------------------------
# Console UTF-8 logging (cross-platform)
# -------------------------
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
try:
    if hasattr(handler.stream, "reconfigure"):
        handler.stream.reconfigure(encoding="utf-8")
except Exception:
    pass
logger.propagate = False
if not logger.handlers:
    logger.addHandler(handler)


# =========================
# DATABASE INIT
# =========================
def init_db():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            temperature REAL NOT NULL,
            humidity REAL NOT NULL,
            lux REAL NOT NULL,
            fan_status INTEGER,
            pump_status INTEGER,
            fan_on_temp REAL,
            fan_off_temp REAL,
            pump_on_humidity REAL,
            pump_off_humidity REAL
        )
    """)

    # Migration: Add columns if they don't exist
    cursor.execute("PRAGMA table_info(sensor_data)")
    columns = [row[1] for row in cursor.fetchall()]
    new_cols = [
        ("fan_status", "INTEGER"),
        ("pump_status", "INTEGER"),
        ("fan_on_temp", "REAL"),
        ("fan_off_temp", "REAL"),
        ("pump_on_humidity", "REAL"),
        ("pump_off_humidity", "REAL")
    ]
    for col_name, col_type in new_cols:
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE sensor_data ADD COLUMN {col_name} {col_type}")

    # Create actuator_logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actuator_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actuator_name TEXT NOT NULL,
            previous_state INTEGER,
            new_state INTEGER,
            trigger_value REAL,
            trigger_type TEXT
        )
    """)

    conn.commit()
    conn.close()


# -------------------------
# Database helpers
# -------------------------
def get_db_connection():
    conn = sqlite3.connect(str(DATABASE), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn


def query_db(query, args=(), one=False):
    conn = get_db_connection()
    cur = conn.execute(query, args)
    rows = cur.fetchall()
    conn.commit()
    conn.close()
    if one:
        return rows[0] if rows else None
    return rows


# =========================
# INSERT SENSOR DATA
# =========================
def get_latest_actuator_states():
    row = query_db("SELECT fan_status, pump_status FROM sensor_data ORDER BY id DESC LIMIT 1", one=True)
    if row:
        return row["fan_status"], row["pump_status"]
    return None, None


def log_actuator_event(name, prev, new, val, type_):
    if prev == new:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO actuator_logs (timestamp, actuator_name, previous_state, new_state, trigger_value, trigger_type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ts, name, prev, new, val, type_)
    )
    conn.commit()
    conn.close()


def insert_sensor_data(temp, hum, lux, fan_stat=None, pump_stat=None, f_on=None, f_off=None, p_on=None, p_off=None, timestamp=None):
    """Insert a sensor row. Timestamp is ISO8601 UTC if not provided."""
    ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Get previous states for logging before insertion
    prev_fan, prev_pump = get_latest_actuator_states()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sensor_data (
            timestamp, temperature, humidity, lux, 
            fan_status, pump_status, 
            fan_on_temp, fan_off_temp, 
            pump_on_humidity, pump_off_humidity
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, temp, hum, lux, fan_stat, pump_stat, f_on, f_off, p_on, p_off)
    )
    conn.commit()
    conn.close()

    # Log events if state changed
    if fan_stat is not None and prev_fan is not None and fan_stat != prev_fan:
        log_actuator_event("Fan", prev_fan, fan_stat, temp, "temperature")
    if pump_stat is not None and prev_pump is not None and pump_stat != prev_pump:
        log_actuator_event("Pump", prev_pump, pump_stat, hum, "humidity")

    return ts


# -------------------------
# Validation helpers
# -------------------------
def is_valid_number(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    if math.isnan(v) or math.isinf(v):
        return False
    return True


def validate_sensor_payload(data):
    required = ("temperature", "humidity", "lux")
    for k in required:
        if k not in data:
            return False, f"missing {k}"
        if not is_valid_number(data[k]):
            return False, f"invalid {k}"
    
    t = float(data["temperature"])
    h = float(data["humidity"])
    l = float(data["lux"])
    
    if t < -20 or t > 80:
        return False, "temperature out of plausible range"
    if h < 0 or h > 100:
        return False, "humidity out of plausible range"
    if l < 0:
        return False, "lux must be >= 0"

    # Optional fields (Actuator telemetry)
    def to_float(v):
        try: return float(v) if v is not None else None
        except: return None
    
    def to_int(v):
        try: return int(v) if v is not None else None
        except: return None

    return True, {
        "temperature": t, 
        "humidity": h, 
        "lux": l,
        "fan_status": to_int(data.get("fan_status")),
        "pump_status": to_int(data.get("pump_status")),
        "fan_on_temp": to_float(data.get("fan_on_temp")),
        "fan_off_temp": to_float(data.get("fan_off_temp")),
        "pump_on_humidity": to_float(data.get("pump_on_humidity")),
        "pump_off_humidity": to_float(data.get("pump_off_humidity"))
    }


# -------------------------
# Anomaly detection
# -------------------------
def detect_anomaly(temperature, humidity, lux, repeat_window=5):
    # All zero anomaly
    if temperature == 0 and humidity == 0 and lux == 0:
        return "all_zero"
    # Repeated identical values
    rows = query_db(
        "SELECT temperature, humidity, lux FROM sensor_data ORDER BY id DESC LIMIT ?",
        (repeat_window,)
    )
    if rows and len(rows) >= repeat_window:
        if all(
            float(r["temperature"]) == temperature and
            float(r["humidity"]) == humidity and
            float(r["lux"]) == lux
            for r in rows
        ):
            return "repeated_values"
    # Obvious corruption
    if abs(temperature) > 1000 or abs(humidity) > 1e6 or lux > 1e9:
        return "corrupted"
    return None


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
            "&current=temperature_2m,relative_humidity_2m,weather_code"
        )
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        weather_code = current.get("weather_code")

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
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "weather": weather_text
        }
    except requests.RequestException as e:
        logger.error("Open-Meteo request failed: %s", e)
        return {"temperature": None, "humidity": None, "weather": "UNAVAILABLE", "error": str(e)}
    except Exception as e:
        logger.exception("Error parsing Open-Meteo response")
        return {"temperature": None, "humidity": None, "weather": "UNAVAILABLE", "error": str(e)}


# =========================
# RECEIVE SENSOR
# =========================
@app.route('/api/sensor', methods=['POST'])
def receive_sensor():
    try:
        data = request.get_json(force=True)
        valid, result = validate_sensor_payload(data)
        if not valid:
            logger.warning("Invalid sensor payload: %s", result)
            return jsonify({"status": "error", "message": result}), 400

        temperature = result["temperature"]
        humidity = result["humidity"]
        lux = result["lux"]

        anomaly = detect_anomaly(temperature, humidity, lux)

        inserted_ts = insert_sensor_data(
            temperature, humidity, lux,
            fan_stat=result.get("fan_status"),
            pump_stat=result.get("pump_status"),
            f_on=result.get("fan_on_temp"),
            f_off=result.get("fan_off_temp"),
            p_on=result.get("pump_on_humidity"),
            p_off=result.get("pump_off_humidity")
        )

        if anomaly:
            logger.warning("Sensor anomaly detected: %s data=%s", anomaly, result)
        else:
            logger.info("Sensor data ingested: ts=%s data=%s", inserted_ts, result)

        return jsonify({"status": "success", "anomaly": anomaly})

    except Exception as e:
        logger.exception("Failed to ingest sensor data")
        return jsonify({"status": "error", "message": str(e)}), 400


# =========================
# API LATEST
# =========================
@app.route('/api/latest')
def latest_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM sensor_data ORDER BY id DESC LIMIT ?
        """,
        (MAX_DATA_POINTS,)
    )
    rows = cursor.fetchall()
    conn.close()

    rows = list(rows)[::-1]
    data = []
    for row in rows:
        temperature = row["temperature"]
        humidity = row["humidity"]
        lux = row["lux"]
        
        # Actuator state with legacy fallback
        fan_stat = row["fan_status"]
        if fan_stat is None:
            fan_stat = 1 if get_fan_status(temperature) == "ON" else 0
            
        pump_stat = row["pump_status"]
        if pump_stat is None:
            pump_stat = 1 if get_pump_status(humidity) == "ON" else 0

        data.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "temperature": temperature,
            "humidity": humidity,
            "lux": lux,
            "fan_status": fan_stat,
            "pump_status": pump_stat,
            "fan_on_temp": row["fan_on_temp"],
            "fan_off_temp": row["fan_off_temp"],
            "pump_on_humidity": row["pump_on_humidity"],
            "pump_off_humidity": row["pump_off_humidity"],
            "environment_status": get_environment_status(temperature, humidity),
            "light_status": get_light_status(lux)
        })
    return jsonify(data)


@app.route('/api/actuator-logs')
def get_actuator_logs():
    limit = request.args.get('limit', 50, type=int)
    rows = query_db("SELECT * FROM actuator_logs ORDER BY id DESC LIMIT ?", (limit,))
    return jsonify([dict(row) for row in rows])


@app.route('/api/thresholds')
def get_thresholds():
    row = query_db("""
        SELECT fan_on_temp, fan_off_temp, pump_on_humidity, pump_off_humidity 
        FROM sensor_data 
        WHERE fan_on_temp IS NOT NULL 
        ORDER BY id DESC LIMIT 1
    """, one=True)
    
    if row:
        return jsonify(dict(row))
        
    return jsonify({
        "fan_on_temp": 30.0,
        "fan_off_temp": 28.0,
        "pump_on_humidity": 40.0,
        "pump_off_humidity": 45.0
    })


# =========================
# WEATHER API
# =========================
@app.route('/api/weather')
def weather():

    lat = request.args.get('lat')
    lon = request.args.get('lon')

    if not lat or not lon:
        lat = DEFAULT_LAT
        lon = DEFAULT_LON

    return jsonify(
        get_weather_data(lat, lon)
    )


# -------------------------
# System & health endpoints
# -------------------------
def get_total_rows():
    row = query_db("SELECT COUNT(*) as cnt FROM sensor_data", one=True)
    return int(row["cnt"]) if row else 0


def get_latest_timestamp():
    row = query_db("SELECT timestamp FROM sensor_data ORDER BY id DESC LIMIT 1", one=True)
    return row["timestamp"] if row else None


def get_database_size():
    try:
        return DATABASE.stat().st_size if DATABASE.exists() else 0
    except Exception:
        return 0


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/api/system')
def api_system():
    try:
        total_rows = get_total_rows()
        latest_sensor_timestamp = get_latest_timestamp()
        database_size = get_database_size()
        server_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return jsonify({
            "total_rows": total_rows,
            "latest_sensor_timestamp": latest_sensor_timestamp,
            "database_size": database_size,
            "server_time": server_time
        })
    except Exception as e:
        logger.exception("Failed to gather system info")
        return jsonify({"status": "error", "message": str(e)}), 500


# =========================
# CLEAR DATABASE
# =========================
@app.route('/api/clear', methods=['POST'])
def clear_database():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM sensor_data")
    cursor.execute("DELETE FROM actuator_logs")
    cursor.execute("""
        DELETE FROM sqlite_sequence
        WHERE name='sensor_data'
    """)
    cursor.execute("""
        DELETE FROM sqlite_sequence
        WHERE name='actuator_logs'
    """)

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": "Database cleared"
    })


# =========================
# EXPORT DATABASE
# =========================
@app.route('/api/export/xlsx')
def export_database_xlsx():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, timestamp, temperature, humidity, lux, 
               fan_status, pump_status, 
               fan_on_temp, fan_off_temp, 
               pump_on_humidity, pump_off_humidity
        FROM sensor_data
        ORDER BY id ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sensor Data"
    worksheet.append([
        "ID", "Timestamp", "Temperature", "Humidity", "Lux",
        "Fan Status", "Pump Status", 
        "Fan ON Temp", "Fan OFF Temp", 
        "Pump ON Hum", "Pump OFF Hum"
    ])

    for row in rows:
        worksheet.append([
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            row[8],
            row[9],
            row[10]
        ])

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    filename = f"sensor_data_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


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
    logger.info("Starting application")
    logger.info("OS: %s; Python: %s; DB: %s; DEBUG: %s", platform.platform(), sys.version.split()[0], DATABASE, DEBUG)
    app.run(host=HOST, port=PORT, debug=DEBUG)
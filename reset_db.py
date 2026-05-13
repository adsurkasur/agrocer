import sqlite3

conn = sqlite3.connect("sensor.db")

cursor = conn.cursor()

cursor.execute("DELETE FROM sensor_data")

conn.commit()
conn.close()

print("Database cleared")
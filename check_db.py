from database import get_connection

conn = get_connection()
rows = conn.execute(
    "SELECT name FROM sqlite_master WHERE type = 'table'"
).fetchall()

for row in rows:
    print(row["name"])
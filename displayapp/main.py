import os
import pymysql
from flask import Flask, render_template

app = Flask(__name__)

DB_HOST = os.environ.get("DB_HOST", "mariadb")
DB_USER = os.environ.get("DB_USER", "user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_NAME = os.environ.get("DB_NAME", "library")

def get_db():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

@app.route("/")
def index():
    borrowers = []
    error = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, created_at FROM borrowers ORDER BY id DESC")
            borrowers = cur.fetchall()
        conn.close()
    except Exception as e:
        error = f"Could not fetch data: {e}"
    return render_template("index.html", borrowers=borrowers, error=error)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

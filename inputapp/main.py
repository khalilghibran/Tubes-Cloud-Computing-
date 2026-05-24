import os
import pymysql
from flask import Flask, request, render_template, redirect, url_for

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

def init_db():
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS borrowers (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[inputapp] DB init error: {e}")

init_db()

@app.route("/", methods=["GET", "POST"])
def index():
    message = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            try:
                conn = get_db()
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO borrowers (name) VALUES (%s)", (name,))
                conn.commit()
                conn.close()
                message = f"Borrower '{name}' added successfully!"
            except Exception as e:
                message = f"Error: {e}"
        else:
            message = "Name cannot be empty."
    return render_template("index.html", message=message)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

import os
import pymysql
from flask import Flask, request, render_template
from datetime import datetime

app = Flask(__name__)

DB_HOST = os.environ.get("DB_HOST", "mariadb")
DB_USER = os.environ.get("DB_USER", "user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_NAME = os.environ.get("DB_NAME", "labdb")

def get_db():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def init_db():
    import time
    max_retries = 10
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            conn = get_db()
            with conn.cursor() as cur:
                # Create equipment table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS equipment (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(255) NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create borrow records table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS borrow_records (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        equipment_id INT NOT NULL,
                        borrower_name VARCHAR(255) NOT NULL,
                        nim VARCHAR(20),
                        fakultas VARCHAR(255),
                        borrow_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        return_date DATETIME,
                        status ENUM('borrowed', 'returned') DEFAULT 'borrowed',
                        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
                    )
                """)
                
                # Insert default equipment
                equipment_list = [
                    'Multimeter', 'Osiloskop', 'Solder', 'Wave Generator',
                    '3D Printer', 'Server', 'Komputer', 'Ruangan'
                ]
                for equip in equipment_list:
                    cur.execute(
                        "INSERT IGNORE INTO equipment (name) VALUES (%s)",
                        (equip,)
                    )
            
            conn.commit()
            conn.close()
            print("[inputapp] Database initialized successfully")
            return
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"[inputapp] DB init failed after {max_retries} retries: {e}")
                return
            print(f"[inputapp] Connection attempt {retry_count}/{max_retries} failed, retrying in 2 seconds...")
            time.sleep(2)

init_db()

@app.route("/", methods=["GET", "POST"])
@app.route("/input", methods=["GET", "POST"])
@app.route("/input/", methods=["GET", "POST"])
def index():
    message = None
    equipment_list = []
    
    try:
        conn = get_db()
        with conn.cursor() as cur:
            # Get equipment with availability count
            cur.execute("""
                SELECT e.id, e.name, 
                       COUNT(CASE WHEN br.status = 'borrowed' THEN 1 END) as borrowed_count
                FROM equipment e
                LEFT JOIN borrow_records br ON e.id = br.equipment_id
                GROUP BY e.id, e.name
                ORDER BY e.name
            """)
            equipment_list = cur.fetchall()
        conn.close()
    except Exception as e:
        message = f"Gagal memuat alat: {e}"
        return render_template("index.html", message=message, equipment_list=[])
    
    if request.method == "POST":
        equipment_id = request.form.get("equipment_id", "").strip()
        borrower_name = request.form.get("borrower_name", "").strip()
        nim = request.form.get("nim", "").strip()
        fakultas = request.form.get("fakultas", "").strip()
        return_date = request.form.get("return_date", "").strip()
        
        if not equipment_id or not borrower_name or not nim or not fakultas or not return_date:
            message = "Silakan lengkapi semua data."
        else:
            try:
                conn = get_db()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO borrow_records (equipment_id, borrower_name, nim, fakultas, return_date)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (equipment_id, borrower_name, nim, fakultas, return_date)
                    )
                    cur.execute("SELECT name FROM equipment WHERE id = %s", (equipment_id,))
                    equip = cur.fetchone()
                conn.commit()
                conn.close()
                equip_name = equip["name"] if equip else "Unknown"
                message = f"'{borrower_name}' berhasil meminjam '{equip_name}'!"
            except Exception as e:
                message = f"Kesalahan: {e}"
    
    return render_template("index.html", message=message, equipment_list=equipment_list)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

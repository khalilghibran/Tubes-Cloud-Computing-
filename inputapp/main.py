import os
import pymysql
import random
from flask import Flask, request, render_template
from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")

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
                        quantity INT DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Add quantity column if it doesn't exist (try and catch if it already exists)
                try:
                    cur.execute("""
                        ALTER TABLE equipment ADD COLUMN quantity INT DEFAULT 1
                    """)
                except pymysql.err.OperationalError:
                    pass  # Column already exists
                
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
                        status ENUM('requested', 'borrowed', 'returned') DEFAULT 'requested',
                        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
                    )
                """)
                
                try:
                    cur.execute("""
                        ALTER TABLE borrow_records MODIFY COLUMN status ENUM('requested', 'borrowed', 'returned') DEFAULT 'requested'
                    """)
                except pymysql.err.OperationalError:
                    pass
                
                # Insert default equipment with random quantities
                equipment_list = [
                    'Multimeter', 'Osiloskop', 'Solder', 'Wave Generator',
                    '3D Printer', 'Server', 'Komputer', 'Ruangan'
                ]
                for equip in equipment_list:
                    random_qty = random.randint(1, 7)
                    cur.execute(
                        "INSERT INTO equipment (name, quantity) VALUES (%s, %s) ON DUPLICATE KEY UPDATE quantity = VALUES(quantity)",
                        (equip, random_qty)
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
        borrow_date = request.form.get("borrow_date", "").strip()
        return_date = request.form.get("return_date", "").strip()
        
        if not equipment_id or not borrower_name or not nim or not fakultas or not borrow_date or not return_date:
            message = "Silakan lengkapi semua data."
        else:
            try:
                borrow_date_obj = datetime.strptime(borrow_date, "%Y-%m-%d").date()
                return_date_obj = datetime.strptime(return_date, "%Y-%m-%d").date()
                today = datetime.now(WIB).date()

                valid = True
                if borrow_date_obj < today:
                    message = "Tanggal peminjaman tidak boleh sebelum hari ini."
                    valid = False
                elif return_date_obj < borrow_date_obj:
                    valid = False

                if not valid:
                    return render_template("index.html", message=message, equipment_list=equipment_list)
            except ValueError:
                message = "Format tanggal tidak valid."
                return render_template("index.html", message=message, equipment_list=equipment_list)

            try:
                conn = get_db()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO borrow_records (equipment_id, borrower_name, nim, fakultas, borrow_date, return_date)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (equipment_id, borrower_name, nim, fakultas, borrow_date, return_date)
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


@app.route("/status")
def status_peminjaman():
    """Show current borrowing status (items with status = 'borrowed')"""
    borrows = []
    message = None
    
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT br.id, br.equipment_id, e.name as equipment_name, br.borrower_name, 
                       br.nim, br.fakultas, br.borrow_date, br.return_date, br.status
                FROM borrow_records br
                JOIN equipment e ON br.equipment_id = e.id
                WHERE br.status = 'borrowed'
                ORDER BY br.borrow_date DESC
            """)
            borrows = cur.fetchall()
        conn.close()
    except Exception as e:
        message = f"Gagal memuat status: {e}"
    
    return render_template("status.html", borrows=borrows, message=message)


@app.route("/riwayat")
def riwayat_peminjaman():
    """Show borrowing history (items with status = 'returned')"""
    borrows = []
    message = None
    
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT br.id, br.equipment_id, e.name as equipment_name, br.borrower_name, 
                       br.nim, br.fakultas, br.borrow_date, br.return_date, br.status
                FROM borrow_records br
                JOIN equipment e ON br.equipment_id = e.id
                WHERE br.status = 'returned'
                ORDER BY br.return_date DESC
            """)
            borrows = cur.fetchall()
        conn.close()
    except Exception as e:
        message = f"Gagal memuat riwayat: {e}"
    
    return render_template("riwayat.html", borrows=borrows, message=message)


@app.route("/daftar-alat")
def daftar_alat():
    """Show all equipment with availability"""
    equipment_list = []
    message = None
    
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.id, e.name, e.quantity,
                       COUNT(CASE WHEN br.status = 'borrowed' THEN 1 END) as borrowed_count,
                       COUNT(br.id) as total_borrowed_history
                FROM equipment e
                LEFT JOIN borrow_records br ON e.id = br.equipment_id
                GROUP BY e.id, e.name, e.quantity
                ORDER BY e.name
            """)
            equipment_list = cur.fetchall()
        conn.close()
    except Exception as e:
        message = f"Gagal memuat daftar alat: {e}"
    
    return render_template("daftar_alat.html", equipment_list=equipment_list, message=message)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

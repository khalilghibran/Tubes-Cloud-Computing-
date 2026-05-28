import os
import pymysql
from flask import Flask, render_template, request, jsonify
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

@app.route("/")
@app.route("/display")
@app.route("/display/")
def index():
    borrow_records = []
    error = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT br.id, e.name as equipment_name, br.borrower_name, 
                       br.borrow_date, br.return_date, br.status
                FROM borrow_records br
                JOIN equipment e ON br.equipment_id = e.id
                ORDER BY br.borrow_date DESC
            """)
            borrow_records = cur.fetchall()
        conn.close()
    except Exception as e:
        error = f"Could not fetch data: {e}"
    
    return render_template("index.html", borrow_records=borrow_records, error=error)

@app.route("/api/return-equipment", methods=["POST"])
def return_equipment():
    """API endpoint to mark equipment as returned"""
    try:
        record_id = request.json.get("record_id")
        if not record_id:
            return jsonify({"success": False, "message": "Record ID required"}), 400
        
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE borrow_records 
                SET status = 'returned', return_date = NOW()
                WHERE id = %s
            """, (record_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Equipment returned successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

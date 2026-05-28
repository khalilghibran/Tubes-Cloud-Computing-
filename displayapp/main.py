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
    filters = {
        'nim': request.args.get('nim', ''),
        'equipment': request.args.get('equipment', ''),
        'fakultas': request.args.get('fakultas', ''),
        'status': request.args.get('status', '')
    }
    
    try:
        conn = get_db()
        with conn.cursor() as cur:
            # Build dynamic WHERE clause
            where_clauses = []
            params = []
            
            if filters['nim']:
                where_clauses.append("br.nim LIKE %s")
                params.append(f"%{filters['nim']}%")
            if filters['equipment']:
                where_clauses.append("e.name LIKE %s")
                params.append(f"%{filters['equipment']}%")
            if filters['fakultas']:
                where_clauses.append("br.fakultas = %s")
                params.append(filters['fakultas'])
            if filters['status']:
                where_clauses.append("br.status = %s")
                params.append(filters['status'])
            
            where_sql = " AND ".join(where_clauses)
            if where_sql:
                where_sql = " WHERE " + where_sql
            
            query = f"""
                SELECT br.id, e.name as equipment_name, br.borrower_name, 
                       br.nim, br.fakultas, br.borrow_date, br.return_date, br.status
                FROM borrow_records br
                JOIN equipment e ON br.equipment_id = e.id
                {where_sql}
                ORDER BY br.borrow_date DESC
            """
            
            cur.execute(query, params)
            borrow_records = cur.fetchall()
            
            # Calculate overdue status for each record
            from datetime import datetime, timedelta
            for record in borrow_records:
                record['is_overdue'] = False
                record['days_overdue'] = 0
                if record['status'] == 'borrowed' and record['return_date']:
                    return_date = record['return_date']
                    if isinstance(return_date, str):
                        return_date = datetime.strptime(return_date, '%Y-%m-%d')
                    today = datetime.now().date()
                    if return_date.date() < today:
                        record['is_overdue'] = True
                        record['days_overdue'] = (today - return_date.date()).days
        conn.close()
    except Exception as e:
        error = f"Gagal mengambil data: {e}"
    
    return render_template("index.html", borrow_records=borrow_records, error=error, filters=filters)

@app.route("/api/return-equipment", methods=["POST"])
def return_equipment():
    """API endpoint to mark equipment as returned"""
    try:
        record_id = request.json.get("record_id")
        if not record_id:
            return jsonify({"success": False, "message": "ID record diperlukan"}), 400
        
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE borrow_records 
                SET status = 'returned', return_date = NOW()
                WHERE id = %s
            """, (record_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Alat berhasil dikembalikan"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

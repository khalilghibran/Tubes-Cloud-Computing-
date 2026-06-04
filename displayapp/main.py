import os
import csv
import io
import pymysql
from flask import Flask, render_template, request, jsonify, Response
from datetime import datetime, date, timedelta
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

def ensure_schema(cur):
    """Ensure required columns exist (safe to call on every request)"""
    cur.execute("SHOW TABLES LIKE 'borrow_records'")
    if not cur.fetchone():
        return
    cur.execute("SHOW COLUMNS FROM borrow_records LIKE 'request_status'")
    if not cur.fetchone():
        cur.execute("""
            ALTER TABLE borrow_records ADD COLUMN request_status ENUM('pending', 'accepted', 'rejected') DEFAULT 'pending'
        """)
    cur.execute("SHOW COLUMNS FROM borrow_records LIKE 'status'")
    col = cur.fetchone()
    if col and 'requested' not in col['Type']:
        cur.execute("""
            ALTER TABLE borrow_records MODIFY COLUMN status ENUM('requested', 'borrowed', 'returned') DEFAULT 'requested'
        """)

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
        'status': request.args.get('status', ''),
        'request_status': request.args.get('request_status', '')
    }
    
    try:
        conn = get_db()
        with conn.cursor() as cur:
            ensure_schema(cur)

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
            if filters['request_status']:
                where_clauses.append("br.request_status = %s")
                params.append(filters['request_status'])
            
            where_sql = " AND ".join(where_clauses)
            if where_sql:
                where_sql = " WHERE " + where_sql
            
            query = f"""
                SELECT br.id, e.name as equipment_name, br.borrower_name, 
                       br.nim, br.fakultas, br.borrow_date, br.return_date, br.status, br.request_status
                FROM borrow_records br
                JOIN equipment e ON br.equipment_id = e.id
                {where_sql}
                ORDER BY br.borrow_date DESC
            """
            
            cur.execute(query, params)
            borrow_records = cur.fetchall()
            
            for record in borrow_records:
                record['is_overdue'] = False
                record['days_overdue'] = 0
                if record['status'] == 'borrowed' and record['return_date']:
                    return_date = record['return_date']
                    if isinstance(return_date, str):
                        return_date = datetime.strptime(return_date, '%Y-%m-%d')
                    today = datetime.now(WIB).date()
                    if return_date.date() < today:
                        record['is_overdue'] = True
                        record['days_overdue'] = (today - return_date.date()).days
        conn.commit()
        conn.close()
    except Exception as e:
        error = f"Gagal mengambil data: {e}"
    
    return render_template("index.html", borrow_records=borrow_records, error=error, filters=filters)

@app.route("/api/accept-request", methods=["POST"])
def accept_request():
    """API endpoint to accept a borrow request"""
    try:
        record_id = request.json.get("record_id")
        if not record_id:
            return jsonify({"success": False, "message": "ID record diperlukan"}), 400
        
        conn = get_db()
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute("SELECT borrow_date FROM borrow_records WHERE id = %s", (record_id,))
            rec = cur.fetchone()
            if not rec:
                return jsonify({"success": False, "message": "Record tidak ditemukan"}), 404
            if rec['borrow_date'] and rec['borrow_date'].date() < datetime.now(WIB).date():
                return jsonify({"success": False, "message": "Tanggal peminjaman sudah lewat, tidak dapat diterima."}), 400
            cur.execute("""
                UPDATE borrow_records 
                SET request_status = 'accepted', status = 'borrowed'
                WHERE id = %s
            """, (record_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Permintaan peminjaman diterima"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/reject-request", methods=["POST"])
def reject_request():
    """API endpoint to reject a borrow request"""
    try:
        record_id = request.json.get("record_id")
        if not record_id:
            return jsonify({"success": False, "message": "ID record diperlukan"}), 400
        
        conn = get_db()
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute("""
                UPDATE borrow_records 
                SET request_status = 'rejected', status = 'returned'
                WHERE id = %s
            """, (record_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Permintaan peminjaman ditolak"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

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

@app.route("/laporan")
def laporan():
    error = None
    today = datetime.now(WIB).date()
    date_from = request.args.get("date_from", (today - timedelta(days=30)).isoformat())
    date_to = request.args.get("date_to", today.isoformat())

    if date_from and date_to:
        try:
            if date.fromisoformat(date_from) > date.fromisoformat(date_to):
                error = "Tanggal 'Dari' tidak boleh lebih besar dari tanggal 'Sampai'."
                return render_template("laporan.html", error=error, total=0, borrowed=0,
                                       returned=0, overdue=0, pending=0, rejected=0,
                                       records=[], overdue_records=[],
                                       date_from=date_from, date_to=date_to)
        except ValueError:
            error = "Format tanggal tidak valid."
            return render_template("laporan.html", error=error, total=0, borrowed=0,
                                   returned=0, overdue=0, pending=0, rejected=0,
                                   records=[], overdue_records=[],
                                   date_from=date_from, date_to=date_to)

    try:
        conn = get_db()
        with conn.cursor() as cur:
            ensure_schema(cur)

            cur.execute("SELECT COUNT(*) as total FROM borrow_records")
            total = cur.fetchone()["total"]

            cur.execute("SELECT COUNT(*) as borrowed FROM borrow_records WHERE request_status = 'accepted' AND status = 'borrowed'")
            borrowed = cur.fetchone()["borrowed"]

            cur.execute("SELECT COUNT(*) as returned FROM borrow_records WHERE status = 'returned'")
            returned = cur.fetchone()["returned"]

            cur.execute("SELECT COUNT(*) as overdue FROM borrow_records WHERE status = 'borrowed' AND return_date IS NOT NULL AND return_date < NOW()")
            overdue = cur.fetchone()["overdue"]

            cur.execute("SELECT COUNT(*) as pending FROM borrow_records WHERE request_status = 'pending'")
            pending = cur.fetchone()["pending"]

            cur.execute("SELECT COUNT(*) as rejected FROM borrow_records WHERE request_status = 'rejected'")
            rejected = cur.fetchone()["rejected"]

            cur.execute("""
                SELECT br.id, e.name as equipment_name, br.borrower_name,
                       br.nim, br.fakultas, br.borrow_date, br.return_date, br.status, br.request_status
                FROM borrow_records br
                JOIN equipment e ON br.equipment_id = e.id
                WHERE DATE(br.borrow_date) >= %s AND DATE(br.borrow_date) <= %s
                ORDER BY br.borrow_date DESC
            """, (date_from, date_to))
            records = cur.fetchall()

            for r in records:
                r['is_overdue'] = False
                r['days_overdue'] = 0
                if r['status'] == 'borrowed' and r['return_date']:
                    rd = r['return_date']
                    if isinstance(rd, str):
                        rd = datetime.strptime(rd, '%Y-%m-%d')
                    if rd.date() < today:
                        r['is_overdue'] = True
                        r['days_overdue'] = (today - rd.date()).days

            cur.execute("""
                SELECT br.id, e.name as equipment_name, br.borrower_name,
                       br.nim, br.fakultas, br.borrow_date, br.return_date, br.status, br.request_status
                FROM borrow_records br
                JOIN equipment e ON br.equipment_id = e.id
                WHERE br.status = 'borrowed' AND br.return_date IS NOT NULL AND br.return_date < NOW()
                ORDER BY br.return_date ASC
            """)
            overdue_records = cur.fetchall()
            for r in overdue_records:
                rd = r['return_date']
                if isinstance(rd, str):
                    rd = datetime.strptime(rd, '%Y-%m-%d')
                r['days_overdue'] = (today - rd.date()).days
        conn.close()
    except Exception as e:
        error = f"Gagal memuat laporan: {e}"
        total = borrowed = returned = overdue = pending = rejected = 0
        records = []
        overdue_records = []

    return render_template("laporan.html", error=error, total=total, borrowed=borrowed,
                           returned=returned, overdue=overdue, pending=pending, rejected=rejected,
                           records=records, overdue_records=overdue_records,
                           date_from=date_from, date_to=date_to)


@app.route("/api/laporan/export")
def laporan_export():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    try:
        conn = get_db()
        with conn.cursor() as cur:
            ensure_schema(cur)
            if date_from and date_to:
                cur.execute("""
                    SELECT br.id, e.name as equipment_name, br.borrower_name,
                           br.nim, br.fakultas, br.borrow_date, br.return_date, br.status, br.request_status
                    FROM borrow_records br
                    JOIN equipment e ON br.equipment_id = e.id
                    WHERE DATE(br.borrow_date) >= %s AND DATE(br.borrow_date) <= %s
                    ORDER BY br.borrow_date DESC
                """, (date_from, date_to))
            else:
                cur.execute("""
                    SELECT br.id, e.name as equipment_name, br.borrower_name,
                           br.nim, br.fakultas, br.borrow_date, br.return_date, br.status, br.request_status
                    FROM borrow_records br
                    JOIN equipment e ON br.equipment_id = e.id
                    ORDER BY br.borrow_date DESC
                """)
            records = cur.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Alat", "Peminjam", "NIM", "Fakultas", "Tgl Pinjam", "Tgl Kembali", "Status Alat", "Status Request"])
        status_map = {'requested': 'Diminta', 'borrowed': 'Dipinjam', 'returned': 'Dikembalikan'}
        req_map = {'pending': 'Menunggu', 'accepted': 'Diterima', 'rejected': 'Ditolak'}
        for r in records:
            writer.writerow([
                r['id'], r['equipment_name'], r['borrower_name'], r['nim'], r['fakultas'],
                r['borrow_date'].strftime('%Y-%m-%d') if r['borrow_date'] else '',
                r['return_date'].strftime('%Y-%m-%d') if r['return_date'] else '',
                status_map.get(r['status'], r['status']),
                req_map.get(r['request_status'], r['request_status'])
            ])
        csv_content = output.getvalue()
        output.close()

        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=laporan_peminjaman_{datetime.now(WIB).date().isoformat()}.csv"}
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/pengaturan-alat")
def pengaturan_alat():
    error = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.id, e.name, e.quantity,
                       COUNT(CASE WHEN br.status = 'borrowed' AND br.request_status = 'accepted' THEN 1 END) as borrowed_count
                FROM equipment e
                LEFT JOIN borrow_records br ON e.id = br.equipment_id
                GROUP BY e.id, e.name, e.quantity
                ORDER BY e.name
            """)
            equipment_list = cur.fetchall()
        conn.close()
    except Exception as e:
        error = f"Gagal memuat alat: {e}"
        equipment_list = []

    return render_template("pengaturan_alat.html", equipment_list=equipment_list, error=error)


@app.route("/api/equipment/add", methods=["POST"])
def equipment_add():
    try:
        name = request.json.get("name", "").strip()
        quantity = request.json.get("quantity", 1)
        if not name:
            return jsonify({"success": False, "message": "Nama alat diperlukan"}), 400

        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO equipment (name, quantity) VALUES (%s, %s)", (name, quantity))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"Alat '{name}' berhasil ditambahkan"})
    except pymysql.err.IntegrityError:
        return jsonify({"success": False, "message": f"Alat '{name}' sudah ada"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/equipment/edit", methods=["POST"])
def equipment_edit():
    try:
        equip_id = request.json.get("id")
        name = request.json.get("name", "").strip()
        quantity = request.json.get("quantity", 1)
        if not equip_id or not name:
            return jsonify({"success": False, "message": "Data tidak lengkap"}), 400

        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("UPDATE equipment SET name = %s, quantity = %s WHERE id = %s", (name, quantity, equip_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"Alat '{name}' berhasil diperbarui"})
    except pymysql.err.IntegrityError:
        return jsonify({"success": False, "message": f"Alat '{name}' sudah ada"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/equipment/delete", methods=["POST"])
def equipment_delete():
    try:
        equip_id = request.json.get("id")
        if not equip_id:
            return jsonify({"success": False, "message": "ID alat diperlukan"}), 400

        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM equipment WHERE id = %s", (equip_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Alat berhasil dihapus"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

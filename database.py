import sqlite3

DB_FILE = "shop.db"

def init_db():
    """Initializes tables for repairs and customer ledger."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Repairs Table (autoincrement starts at 1001 for clean job tokens)
    c.execute("""
        CREATE TABLE IF NOT EXISTS repairs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            model TEXT,
            fault TEXT,
            cost REAL,
            charged REAL,
            lock_code TEXT,
            imei TEXT,
            image TEXT,
            status TEXT DEFAULT 'Pending',
            profit REAL
        )
    """)

    # Ledger Table (Udhar / Jama Tracking)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ledger (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            entry_type TEXT,
            amount REAL,
            note TEXT
        )
    """)

    # Ensure Job IDs start at 1001 if the table is fresh
    c.execute("SELECT count(*) FROM repairs")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('repairs', 1000)")

    conn.commit()
    conn.close()

# ================= REPAIR OPERATIONS =================
def db_add_repair(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    profit = float(data.get("charged", 0)) - float(data.get("cost", 0))
    c.execute("""
        INSERT INTO repairs (date, name, model, fault, cost, charged, lock_code, imei, image, status, profit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
    """, (
        data["date"], data["name"], data["model"], data["fault"],
        data["cost"], data["charged"], data.get("lock_code", "None"),
        data.get("imei", "N/A"), data.get("image", "No Image"), profit
    ))
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"status": "success", "job_id": job_id, "profit": profit}

def db_find_job(job_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT job_id, date, name, model, fault, cost, charged, imei, lock_code, status, profit FROM repairs WHERE job_id = ?", (int(job_id),))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"status": "not_found"}
    return {
        "status": "success",
        "job_id": row[0],
        "date": row[1],
        "name": row[2],
        "customer": row[2],
        "model": row[3],
        "fault": row[4],
        "cost": row[5],
        "charged": row[6],
        "imei": row[7],
        "lock_code": row[8],
        "job_status": row[9],
        "profit": row[10]
    }

def db_update_status(job_id, new_status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE repairs SET status = ? WHERE job_id = ?", (new_status, int(job_id)))
    conn.commit()
    conn.close()
    return {"status": "success"}

def db_get_today_jobs(date_str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT job_id, name, model, fault, cost, charged, profit FROM repairs WHERE date = ?", (date_str,))
    rows = c.fetchall()
    conn.close()

    jobs = []
    for r in rows:
        jobs.append({
            "job_id": r[0],
            "customer": r[1],
            "model": r[2],
            "fault": r[3],
            "cost": r[4],
            "charged": r[5],
            "auto_profit": r[6]
        })
    return {"status": "success", "jobs": jobs}

def db_update_profit(job_id, profit):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE repairs SET profit = ? WHERE job_id = ?", (float(profit), int(job_id)))
    conn.commit()
    conn.close()
    return {"status": "success"}

# ================= LEDGER OPERATIONS =================
def db_add_ledger(date_str, name, entry_type, amount, note):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO ledger (date, name, entry_type, amount, note)
        VALUES (?, ?, ?, ?, ?)
    """, (date_str, name.strip(), entry_type, float(amount), note))
    entry_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"status": "success", "entry_id": entry_id}

def db_get_customer_balance(name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT date, entry_type, amount, note 
        FROM ledger 
        WHERE LOWER(name) = LOWER(?)
        ORDER BY entry_id ASC
    """, (name.strip(),))
    rows = c.fetchall()
    conn.close()

    total_debit = 0.0
    total_credit = 0.0
    history = []

    for r in rows:
        e_type, amt = r[1], float(r[2])
        if e_type == "Debit":
            total_debit += amt
        elif e_type == "Credit":
            total_credit += amt
        history.append({"date": r[0], "type": e_type, "amount": amt, "note": r[3]})

    return {
        "status": "success",
        "customer": name,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balance": total_debit - total_credit,
        "history": history[-5:]
    }
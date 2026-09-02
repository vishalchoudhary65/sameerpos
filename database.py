import sqlite3
from config import DB_FILE

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 1. Repairs Table
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

    # 2. Customer Ledger Table
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

    # 3. Categories Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            cat_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    # 4. Inventory Table (with Category FK, Warranty, Cost, and Selling Price)
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT NOT NULL,
            qty INTEGER DEFAULT 0,
            cost_price REAL DEFAULT 0.0,
            selling_price REAL DEFAULT 0.0,
            warranty TEXT DEFAULT 'None',
            FOREIGN KEY (category_id) REFERENCES categories (cat_id) ON DELETE CASCADE
        )
    """)

    # Keep Repair tokens starting at 1001
    c.execute("SELECT count(*) FROM repairs")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('repairs', 1000)")

    conn.commit()
    conn.close()

# ================= REPAIRS =================
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
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT job_id, date, name, model, fault, cost, charged, imei, lock_code, status, profit FROM repairs WHERE job_id = ?", (int(job_id),))
        row = c.fetchone()
        conn.close()
        if not row:
            return {"status": "not_found"}
        return {
            "status": "success", "job_id": row[0], "date": row[1], "name": row[2],
            "customer": row[2], "model": row[3], "fault": row[4], "cost": row[5],
            "charged": row[6], "imei": row[7], "lock_code": row[8], "job_status": row[9], "profit": row[10]
        }
    except Exception:
        return {"status": "not_found"}

def db_update_status(job_id, new_status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE repairs SET status = ? WHERE job_id = ?", (new_status, int(job_id)))
    conn.commit()
    conn.close()

def db_get_today_jobs(date_str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT job_id, name, model, fault, cost, charged, profit FROM repairs WHERE date = ?", (date_str,))
    rows = c.fetchall()
    conn.close()
    return [{"job_id": r[0], "customer": r[1], "model": r[2], "fault": r[3], "cost": r[4], "charged": r[5], "auto_profit": r[6]} for r in rows]

def db_update_profit(job_id, profit):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE repairs SET profit = ? WHERE job_id = ?", (float(profit), int(job_id)))
    conn.commit()
    conn.close()

# ================= LEDGER =================
def db_add_ledger(date_str, name, entry_type, amount, note):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO ledger (date, name, entry_type, amount, note) VALUES (?, ?, ?, ?, ?)",
              (date_str, name.strip(), entry_type, float(amount), note))
    entry_id = c.lastrowid
    conn.commit()
    conn.close()
    return entry_id

def db_get_customer_balance(name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT date, entry_type, amount, note FROM ledger WHERE LOWER(name) = LOWER(?) ORDER BY entry_id ASC", (name.strip(),))
    rows = c.fetchall()
    conn.close()

    total_debit, total_credit = 0.0, 0.0
    history = []
    for r in rows:
        amt = float(r[2])
        if r[1] == "Debit": total_debit += amt
        elif r[1] == "Credit": total_credit += amt
        history.append({"date": r[0], "type": r[1], "amount": amt, "note": r[3]})

    return {
        "customer": name, "total_debit": total_debit, "total_credit": total_credit,
        "balance": total_debit - total_credit, "history": history[-5:]
    }

# ================= CATEGORIES =================
def db_get_categories():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT cat_id, name FROM categories ORDER BY name ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def db_add_category(name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name) VALUES (?)", (name.strip(),))
        cat_id = c.lastrowid
        conn.commit()
        conn.close()
        return True, cat_id
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Category already exists"

def db_get_category_by_id(cat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT cat_id, name FROM categories WHERE cat_id = ?", (int(cat_id),))
    row = c.fetchone()
    conn.close()
    return row

# ================= INVENTORY CRUD =================
def db_add_item(cat_id, name, qty, cost, sell, warranty):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO inventory (category_id, name, qty, cost_price, selling_price, warranty)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (int(cat_id), name.strip(), int(qty), float(cost), float(sell), warranty.strip()))
    item_id = c.lastrowid
    conn.commit()
    conn.close()
    return item_id

def db_get_items_by_category(cat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT item_id, name, qty, cost_price, selling_price, warranty 
        FROM inventory 
        WHERE category_id = ? 
        ORDER BY name ASC
    """, (int(cat_id),))
    rows = c.fetchall()
    conn.close()
    return rows

def db_get_item_by_id(item_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT item_id, category_id, name, qty, cost_price, selling_price, warranty 
        FROM inventory 
        WHERE item_id = ?
    """, (int(item_id),))
    row = c.fetchone()
    conn.close()
    return row

def db_adjust_qty(item_id, delta):
    """Adjusts quantity up or down (+1 or -1). Prevents dropping below 0."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE inventory SET qty = MAX(0, qty + ?) WHERE item_id = ?", (int(delta), int(item_id)))
    c.execute("SELECT item_id, name, qty FROM inventory WHERE item_id = ?", (int(item_id),))
    row = c.fetchone()
    conn.commit()
    conn.close()
    return row

def db_update_item(item_id, name, qty, cost, sell, warranty):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        UPDATE inventory 
        SET name = ?, qty = ?, cost_price = ?, selling_price = ?, warranty = ?
        WHERE item_id = ?
    """, (name.strip(), int(qty), float(cost), float(sell), warranty.strip(), int(item_id)))
    conn.commit()
    conn.close()
    return True

def db_delete_item(item_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM inventory WHERE item_id = ?", (int(item_id),))
    conn.commit()
    conn.close()
    return True

# ================= 8:00 AM RESTOCK QUERY =================
def db_get_low_stock_for_alert(threshold=2):
    """Fetches items that are running out across all categories."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT i.name, c.name, i.qty 
        FROM inventory i
        JOIN categories c ON i.category_id = c.cat_id
        WHERE i.qty <= ?
        ORDER BY i.qty ASC
    """, (threshold,))
    rows = c.fetchall()
    conn.close()
    return rows
import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, timezone

DB_DIR = os.environ.get("DB_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_PATH = os.path.join(DB_DIR, "qyouro.db")
os.makedirs(DB_DIR, exist_ok=True)


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _hash_password(password):
    salt = "qyouro_salt_v1"
    return hashlib.sha256((salt + password).encode()).hexdigest()


def init_auth_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            fio TEXT NOT NULL,
            phone TEXT DEFAULT '',
            role TEXT DEFAULT 'employee',
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def admin_login(email, password):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM admins WHERE email = ? AND password_hash = ?",
        (email.strip().lower(), _hash_password(password))
    ).fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "email": row["email"], "name": row["name"]}
    return None


def employee_login(email, password):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM employees WHERE email = ? AND password_hash = ? AND status = 'active'",
        (email.strip().lower(), _hash_password(password))
    ).fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "email": row["email"], "fio": row["fio"],
                "phone": row["phone"], "role": row["role"]}
    return None


def admin_exists():
    conn = _get_conn()
    count = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    conn.close()
    return count > 0


def create_admin(email, password, name):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO admins (email, password_hash, name, created_at) VALUES (?, ?, ?, ?)",
        (email.strip().lower(), _hash_password(password), name, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def list_employees():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM employees ORDER BY created_at DESC").fetchall()
    conn.close()
    return [{"id": r["id"], "email": r["email"], "fio": r["fio"],
             "phone": r["phone"], "role": r["role"], "status": r["status"],
             "created_at": r["created_at"]} for r in rows]


def create_employee(email, password, fio, phone="", role="employee"):
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO employees (email, password_hash, fio, phone, role, status, created_at) VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (email.strip().lower(), _hash_password(password), fio, phone, role,
             datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def update_employee(emp_id, **kwargs):
    conn = _get_conn()
    allowed = {"email", "fio", "phone", "role", "status"}
    for k, v in kwargs.items():
        if k in allowed:
            conn.execute(f"UPDATE employees SET {k} = ? WHERE id = ?", (v, emp_id))
    conn.commit()
    conn.close()


def delete_employee(emp_id):
    conn = _get_conn()
    conn.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()


def reset_password(emp_id, new_password):
    conn = _get_conn()
    conn.execute("UPDATE employees SET password_hash = ? WHERE id = ?",
                 (_hash_password(new_password), emp_id))
    conn.commit()
    conn.close()


def create_reset_token(email):
    conn = _get_conn()
    row = conn.execute("SELECT id FROM employees WHERE email = ? AND status = 'active'",
                       (email.strip().lower(),)).fetchone()
    if not row:
        conn.close()
        return None

    token = secrets.token_hex(16)
    expires = (datetime.now(timezone.utc) + datetime.timedelta(hours=1)).isoformat()
    conn.execute(
        "INSERT INTO reset_tokens (email, token, expires_at) VALUES (?, ?, ?)",
        (email.strip().lower(), token, expires)
    )
    conn.commit()
    conn.close()
    return token


def verify_reset_token(token):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM reset_tokens WHERE token = ? AND used = 0 AND expires_at > ?",
        (token, datetime.now(timezone.utc).isoformat())
    ).fetchone()
    if row:
        conn.execute("UPDATE reset_tokens SET used = 1 WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        return row["email"]
    conn.close()
    return None


def change_password_by_email(email, new_password):
    conn = _get_conn()
    conn.execute("UPDATE employees SET password_hash = ? WHERE email = ?",
                 (_hash_password(new_password), email.strip().lower()))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


init_auth_db()

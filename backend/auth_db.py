import sqlite3
import os
import secrets
from datetime import datetime, timedelta, timezone
from security import hash_password, verify_password

DB_DIR = os.environ.get("DB_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_PATH = os.path.join(DB_DIR, "qyouro.db")
os.makedirs(DB_DIR, exist_ok=True)


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _legacy_verify(stored_hash, password):
    import hashlib
    legacy = hashlib.sha256(("qyouro_salt_v1" + password).encode()).hexdigest()
    return legacy == stored_hash


def init_auth_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
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
            role TEXT DEFAULT 'operator',
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_type TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            revoked INTEGER DEFAULT 0
        )
    """)
    for col in ["role"]:
        try:
            conn.execute(f"ALTER TABLE admins ADD COLUMN {col} TEXT DEFAULT 'admin'")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def _migrate_password(email, password):
    """Миграция с SHA256 на bcrypt при успешном входе."""
    conn = _get_conn()
    conn.execute("UPDATE admins SET password_hash = ? WHERE email = ?",
                 (hash_password(password), email))
    conn.execute("UPDATE employees SET password_hash = ? WHERE email = ?",
                 (hash_password(password), email))
    conn.commit()
    conn.close()


def admin_login(email, password):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM admins WHERE email = ?",
                       (email.strip().lower(),)).fetchone()
    conn.close()
    if row:
        stored = row["password_hash"]
        if verify_password(password, stored) or _legacy_verify(stored, password):
            if not stored.startswith("$2"):
                _migrate_password(email.strip().lower(), password)
            return {"id": row["id"], "email": row["email"], "name": row["name"],
                    "role": row["role"] if "role" in row.keys() else "admin"}
    return None


def employee_login(email, password):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM employees WHERE email = ? AND status = 'active'",
        (email.strip().lower(),)).fetchone()
    conn.close()
    if row:
        stored = row["password_hash"]
        if verify_password(password, stored) or _legacy_verify(stored, password):
            if not stored.startswith("$2"):
                _migrate_password(email.strip().lower(), password)
            return {"id": row["id"], "email": row["email"], "fio": row["fio"],
                    "phone": row["phone"], "role": row["role"]}
    return None


def admin_exists():
    conn = _get_conn()
    count = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    conn.close()
    return count > 0


def create_admin(email, password, name, role="admin"):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO admins (email, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (email.strip().lower(), hash_password(password), name, role,
         datetime.now(timezone.utc).isoformat())
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


def list_admins():
    conn = _get_conn()
    rows = conn.execute("SELECT id, email, name, role, created_at FROM admins ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_employee(email, password, fio, phone="", role="operator"):
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO employees (email, password_hash, fio, phone, role, status, created_at) VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (email.strip().lower(), hash_password(password), fio, phone, role,
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
                 (hash_password(new_password), emp_id))
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
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
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
                 (hash_password(new_password), email.strip().lower()))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def get_user_by_id(user_id: int, user_type: str = "employee") -> dict | None:
    conn = _get_conn()
    table = "employees" if user_type == "employee" else "admins"
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result["user_type"] = user_type
        if user_type == "employee":
            result["name"] = result.get("fio", "")
        return result
    return None


init_auth_db()

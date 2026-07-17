import sqlite3
import os
import secrets
from datetime import datetime, timedelta, timezone

DB_DIR = os.environ.get("DB_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_PATH = os.path.join(DB_DIR, "qyouro.db")


def get_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS license_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            organization_name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            city TEXT DEFAULT '',
            comment TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            user_vk_id INTEGER,
            activated_at TEXT
        )
    """)
    # миграция для старых БД
    for col in ["phone", "city", "comment"]:
        try:
            conn.execute(f"ALTER TABLE license_keys ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def generate_key(organization_name: str, expiry_days: int, phone: str = "", city: str = "", comment: str = "") -> str:
    key = "qy-" + secrets.token_hex(8)
    now = datetime.now(timezone.utc)
    created_at = now.isoformat()
    expires_at = (now + timedelta(days=expiry_days)).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO license_keys (key, organization_name, phone, city, comment, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
        (key, organization_name, phone, city, comment, created_at, expires_at)
    )
    conn.commit()
    conn.close()
    return key


def validate_key(key: str, vk_user_id: int = None) -> dict:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM license_keys WHERE key = ? AND status = 'active'",
        (key,)
    ).fetchone()

    if not row:
        conn.close()
        return {"valid": False, "reason": "KEY_NOT_FOUND"}

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        conn.execute("UPDATE license_keys SET status = 'expired' WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        return {"valid": False, "reason": "KEY_EXPIRED"}

    if row["user_vk_id"] is not None and row["user_vk_id"] != vk_user_id:
        conn.close()
        return {"valid": False, "reason": "KEY_ALREADY_USED"}

    conn.close()
    return {
        "valid": True,
        "key": row["key"],
        "organization_name": row["organization_name"],
        "phone": row["phone"] or "",
        "city": row["city"] or "",
        "comment": row["comment"] or "",
        "expires_at": row["expires_at"],
        "is_activated": row["user_vk_id"] is not None
    }


def activate_key(key: str, vk_user_id: int) -> dict:
    result = validate_key(key, vk_user_id)
    if not result["valid"]:
        return result

    conn = get_db()
    conn.execute(
        "UPDATE license_keys SET user_vk_id = ?, activated_at = ? WHERE key = ?",
        (vk_user_id, datetime.now(timezone.utc).isoformat(), key)
    )
    conn.commit()
    conn.close()

    return {
        **result,
        "is_activated": True
    }


def get_profile(vk_user_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM license_keys WHERE user_vk_id = ? ORDER BY id DESC LIMIT 1",
        (vk_user_id,)
    ).fetchone()
    conn.close()

    if not row:
        return None

    expires_at = datetime.fromisoformat(row["expires_at"])
    now = datetime.now(timezone.utc)
    days_left = (expires_at - now).days

    return {
        "organization_name": row["organization_name"],
        "phone": row["phone"] or "",
        "city": row["city"] or "",
        "comment": row["comment"] or "",
        "status": row["status"],
        "created_at": row["created_at"],
        "activated_at": row["activated_at"],
        "expires_at": row["expires_at"],
        "days_left": max(0, days_left)
    }


def list_keys(status: str = None, search: str = "") -> list:
    conn = get_db()
    query = "SELECT * FROM license_keys WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)

    if search:
        query += " AND (organization_name LIKE ? OR phone LIKE ? OR city LIKE ? OR comment LIKE ? OR key LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like, like, like])

    query += " ORDER BY created_at DESC"

    rows = conn.execute(query, params).fetchall()

    result = []
    for row in rows:
        expires_at = datetime.fromisoformat(row["expires_at"])
        now = datetime.now(timezone.utc)
        result.append({
            "id": row["id"],
            "key": row["key"],
            "organization_name": row["organization_name"],
            "phone": row["phone"] or "",
            "city": row["city"] or "",
            "comment": row["comment"] or "",
            "status": row["status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "days_left": max(0, (expires_at - now).days),
            "user_vk_id": row["user_vk_id"]
        })

    conn.close()
    return result


def revoke_key(key_id: int) -> bool:
    conn = get_db()
    conn.execute(
        "UPDATE license_keys SET status = 'revoked', user_vk_id = NULL, activated_at = NULL WHERE id = ?",
        (key_id,)
    )
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def unbind_key(key_id: int = None, vk_user_id: int = None) -> bool:
    conn = get_db()
    if key_id:
        conn.execute(
            "UPDATE license_keys SET user_vk_id = NULL, activated_at = NULL WHERE id = ?",
            (key_id,)
        )
    elif vk_user_id:
        conn.execute(
            "UPDATE license_keys SET user_vk_id = NULL, activated_at = NULL WHERE user_vk_id = ?",
            (vk_user_id,)
        )
    else:
        conn.close()
        return False
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def delete_key(key_id: int) -> bool:
    conn = get_db()
    conn.execute("DELETE FROM license_keys WHERE id = ?", (key_id,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


init_db()

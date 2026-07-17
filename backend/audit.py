import sqlite3
import os
from datetime import datetime, timezone

DB_DIR = os.environ.get("DB_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_PATH = os.path.join(DB_DIR, "qyouro.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_audit():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            user_role TEXT,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_vk_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            scan_count INTEGER DEFAULT 0,
            UNIQUE(user_vk_id, date)
        )
    """)
    conn.commit()
    conn.close()


def log_action(user_id: int | None, user_name: str | None, user_role: str | None,
               action: str, entity_type: str = None, entity_id: int = None,
               details: str = None, ip_address: str = None):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO audit_log (user_id, user_name, user_role, action, entity_type, entity_id, details, ip_address, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, user_name, user_role, action, entity_type, entity_id, details, ip_address,
         datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def get_audit_log(limit: int = 200, user_id: int = None, action: str = None,
                  date_from: str = None, date_to: str = None) -> list:
    conn = _get_conn()
    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if action:
        query += " AND action = ?"
        params.append(action)
    if date_from:
        query += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND created_at <= ?"
        params.append(date_to)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def increment_scan(user_vk_id: int) -> int:
    conn = _get_conn()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO scan_stats (user_vk_id, date, scan_count) VALUES (?, ?, 1) "
        "ON CONFLICT(user_vk_id, date) DO UPDATE SET scan_count = scan_count + 1",
        (user_vk_id, today)
    )
    conn.commit()
    row = conn.execute(
        "SELECT scan_count FROM scan_stats WHERE user_vk_id = ? AND date = ?",
        (user_vk_id, today)
    ).fetchone()
    conn.close()
    return row["scan_count"] if row else 0


def get_scan_stats(user_vk_id: int, days: int = 30) -> list:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT date, scan_count FROM scan_stats WHERE user_vk_id = ? "
        "ORDER BY date DESC LIMIT ?",
        (user_vk_id, days)
    ).fetchall()
    conn.close()
    return [{"date": r["date"], "count": r["scan_count"]} for r in rows]


def get_scan_limit(user_vk_id: int) -> int | None:
    """Возвращает дневной лимит сканирований или None если безлимит."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT comment FROM license_keys WHERE user_vk_id = ? AND status = 'active' "
        "ORDER BY id DESC LIMIT 1",
        (user_vk_id,)
    ).fetchone()
    conn.close()
    if not row or not row["comment"]:
        return None
    import json
    try:
        meta = json.loads(row["comment"])
        return meta.get("scan_limit")
    except (json.JSONDecodeError, TypeError):
        return None


def get_today_scan_count(user_vk_id: int) -> int:
    conn = _get_conn()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT scan_count FROM scan_stats WHERE user_vk_id = ? AND date = ?",
        (user_vk_id, today)
    ).fetchone()
    conn.close()
    return row["scan_count"] if row else 0


init_audit()

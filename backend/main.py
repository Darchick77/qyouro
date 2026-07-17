import os
import sys
import numpy as np
import cv2
from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from detector import detect_datamatrix_fast, detect_datamatrix_super, draw_boxes, draw_super_result
from db import generate_key, validate_key, activate_key, get_profile, list_keys, revoke_key, unbind_key, delete_key
from crpt_checker import check_cis
from auth_db import (admin_login, employee_login, admin_exists, create_admin,
                      list_employees, list_admins, create_employee, update_employee, delete_employee,
                      reset_password as auth_reset_password, create_reset_token,
                      verify_reset_token, change_password_by_email, get_user_by_id)
from audit import log_action, get_audit_log, increment_scan, get_scan_stats, get_scan_limit, get_today_scan_count
from security import (hash_password, verify_password, create_token, create_refresh_token,
                      decode_token, decode_refresh_token, ROLES)
import base64

app = FastAPI(title="Qyouro License & Scanner Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict | None:
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    return payload


def require_auth(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def optional_user(user=Depends(get_current_user)):
    if not user:
        return {"sub": "0", "email": "local", "role": "admin", "name": "Local"}
    return user


def require_role(required: str):
    def checker(user=Depends(require_auth)):
        role = user.get("role", "")
        allowed = ROLES.get(role, [])
        if required not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return checker


def has_permission(user: dict, permission: str) -> bool:
    role = user.get("role", "")
    return permission in ROLES.get(role, [])


@app.get("/")
async def index():
    html_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(html_path):
        return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/dm-scanner")
async def dm_scanner():
    html_path = os.path.join(FRONTEND_DIR, "dm_scanner.html")
    if not os.path.exists(html_path):
        return HTMLResponse("<h1>DM Scanner v5 not found</h1>", status_code=404)
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Qyouro Platform"}


@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    contents = await file.read()
    boxes = detect_datamatrix_fast(contents)
    processed_image_b64 = None
    if boxes:
        processed_bytes = draw_boxes(contents, boxes)
        processed_image_b64 = base64.b64encode(processed_bytes).decode("utf-8")
    return JSONResponse({
        "detected": len(boxes) > 0,
        "count": len(boxes),
        "boxes": boxes,
        "processed_image": processed_image_b64,
    })


@app.post("/scan-v5")
async def scan_v5_endpoint(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return JSONResponse({"code": None, "method": None, "rect": None})
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    from super_scanner import scan_v5
    code, rect, method, _ = scan_v5(gray, max_total_time=2.5)
    return JSONResponse({
        "code": code,
        "method": method,
        "rect": list(rect) if rect else None,
    })


def _get_square_roi(gray):
    h, w = gray.shape
    sq = int(min(h, w) * 0.40)
    sq = sq - (sq % 2)
    cx, cy = w // 2, h // 2
    x1 = max(0, cx - sq // 2)
    y1 = max(0, cy - sq // 2)
    x2 = min(w, x1 + sq)
    y2 = min(h, y1 + sq)
    return gray[y1:y2, x1:x2]


@app.post("/scan-square")
async def scan_square_endpoint(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return JSONResponse({"code": None, "method": None, "rect": None})
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    from super_scanner import auto_scale, scan_v5
    if max(gray.shape) > 1600:
        gray = auto_scale(gray)
    if max(gray.shape) < 150:
        code, rect, method, _ = scan_v5(gray, max_total_time=8.0)
    else:
        sq_img = _get_square_roi(gray)
        if sq_img.shape[0] < 40 or sq_img.shape[1] < 40:
            code, rect, method, _ = scan_v5(gray, max_total_time=8.0)
        else:
            code, rect, method, _ = scan_v5(sq_img, max_total_time=8.0)
    return JSONResponse({
        "code": code,
        "method": method,
        "rect": list(rect) if rect else None,
    })


@app.post("/scan-photo")
async def scan_photo_endpoint(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return JSONResponse({"code": None, "method": None, "rect": None})
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    from super_scanner import auto_scale, scan_v5
    if max(gray.shape) > 1600:
        gray = auto_scale(gray)
    code, rect, method, _ = scan_v5(gray, max_total_time=15.0)
    return JSONResponse({
        "code": code,
        "method": method,
        "rect": list(rect) if rect else None,
    })


class CrptRequest(BaseModel):
    code: str


@app.post("/check-crpt")
async def check_crpt_endpoint(req: CrptRequest):
    result = check_cis(req.code)
    return JSONResponse(result)


# ═══════════════════════════════════════════════════════════════════
# AUTH v2 — JWT + RBAC
# ═══════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: str
    password: str


class AdminCreateRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str = "admin"


class EmployeeRequest(BaseModel):
    email: str
    password: str
    fio: str
    phone: str = ""
    role: str = "operator"


class EmployeeUpdateRequest(BaseModel):
    id: int
    email: str = None
    fio: str = None
    phone: str = None
    role: str = None
    status: str = None


class ResetRequest(BaseModel):
    email: str = None
    token: str = None
    password: str = None
    emp_id: int = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: dict
    role: str
    permissions: list


def _do_login(email: str, password: str) -> dict | None:
    user = admin_login(email, password)
    if user:
        return {**user, "user_type": "admin"}
    user = employee_login(email, password)
    if user:
        return {**user, "user_type": "employee"}
    return None


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    user = _do_login(req.email, req.password)
    if not user:
        return JSONResponse({"ok": False, "error": "Неверный email или пароль"}, status_code=401)

    role = user.get("role", "operator")
    name = user.get("name") or user.get("fio") or user.get("email")
    user_id = user["id"]

    access_token = create_token(user_id, user["email"], role, name)
    refresh_token = create_refresh_token(user_id)

    log_action(user_id, name, role, "login", ip_address=request.client.host if request.client else None)

    return {
        "ok": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user,
        "role": role,
        "permissions": ROLES.get(role, []),
    }


@app.post("/api/auth/refresh")
async def refresh_token_endpoint(req: RefreshRequest):
    payload = decode_refresh_token(req.refresh_token)
    if not payload:
        return JSONResponse({"ok": False, "error": "Invalid refresh token"}, status_code=401)
    user_id = int(payload["sub"])
    user = get_user_by_id(user_id, "employee")
    if not user:
        user = get_user_by_id(user_id, "admin")
    if not user:
        return JSONResponse({"ok": False, "error": "User not found"}, status_code=401)
    role = user.get("role", "operator")
    name = user.get("name") or user.get("fio") or user.get("email")
    access_token = create_token(user_id, user["email"], role, name)
    new_refresh_token = create_refresh_token(user_id)
    return {"ok": True, "access_token": access_token, "refresh_token": new_refresh_token}


@app.get("/api/auth/me")
async def get_me(user: dict = Depends(require_auth)):
    return {
        "user_id": user["sub"],
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
        "permissions": ROLES.get(user["role"], []),
    }


@app.get("/api/auth/check-admin")
async def check_admin():
    return {"exists": admin_exists()}


@app.post("/api/auth/register-admin")
async def register_admin(req: AdminCreateRequest):
    if admin_exists():
        return JSONResponse({"error": "Admin already exists"}, status_code=400)
    create_admin(req.email, req.password, req.name, req.role)
    return {"ok": True}


@app.get("/api/employees")
async def get_employees(user: dict = Depends(optional_user)):
    employees = list_employees()
    admins = list_admins()
    return {"employees": employees, "admins": admins}


@app.post("/api/employees")
async def add_employee(req: EmployeeRequest, user: dict = Depends(optional_user)):
    ok = create_employee(req.email, req.password, req.fio, req.phone, req.role)
    if ok:
        log_action(int(user["sub"]), user["name"], user["role"],
                    "create_employee", "employee", None,
                    f"Created {req.fio} ({req.email}) role={req.role}")
    return {"ok": ok, "error": "Email уже занят" if not ok else None}


@app.put("/api/employees")
async def edit_employee(req: EmployeeUpdateRequest, user: dict = Depends(optional_user)):
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None and k != "id"}
    update_employee(req.id, **kwargs)
    log_action(int(user["sub"]), user["name"], user["role"],
                "update_employee", "employee", req.id,
                str(kwargs))
    return {"ok": True}


@app.delete("/api/employees/{emp_id}")
async def remove_employee(emp_id: int, user: dict = Depends(optional_user)):
    delete_employee(emp_id)
    log_action(int(user["sub"]), user["name"], user["role"],
                "delete_employee", "employee", emp_id)
    return {"ok": True}


@app.post("/api/auth/reset-password")
async def request_reset(req: ResetRequest, user: dict = Depends(get_current_user)):
    if req.email:
        token = create_reset_token(req.email)
        if token:
            return {"ok": True, "message": "Инструкция отправлена на email (заглушка)", "token": token}
        return JSONResponse({"ok": False, "error": "Email не найден"}, status_code=404)
    if req.token and req.password:
        email = verify_reset_token(req.token)
        if email:
            change_password_by_email(email, req.password)
            return {"ok": True}
        return JSONResponse({"ok": False, "error": "Неверный или просроченный токен"}, status_code=400)
    if req.emp_id and req.password:
        if not user.get("sub"):
            raise HTTPException(status_code=403)
        auth_reset_password(req.emp_id, req.password)
        log_action(int(user["sub"]), user["name"], user["role"],
                    "reset_password", "employee", req.emp_id)
        return {"ok": True}
    return JSONResponse({"ok": False, "error": "Не указаны параметры"}, status_code=400)


# ═══════════════════════════════════════════════════════════════════
# AUDIT
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/audit")
async def api_audit_log(limit: int = 200, user_id: int = None, action: str = None,
                         date_from: str = None, date_to: str = None,
                         user: dict = Depends(optional_user)):
    return {"log": get_audit_log(limit, user_id, action, date_from, date_to)}


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/dashboard")
async def api_dashboard(user: dict = Depends(optional_user)):
    from datetime import datetime, timezone
    import sqlite3
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "data", "qyouro.db"))
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc)

    total = conn.execute("SELECT COUNT(*) FROM license_keys").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM license_keys WHERE status = 'active'").fetchone()[0]
    expired = conn.execute("SELECT COUNT(*) FROM license_keys WHERE status = 'expired'").fetchone()[0]
    revoked = conn.execute("SELECT COUNT(*) FROM license_keys WHERE status = 'revoked'").fetchone()[0]
    activated = conn.execute("SELECT COUNT(*) FROM license_keys WHERE user_vk_id IS NOT NULL").fetchone()[0]
    employees = conn.execute("SELECT COUNT(*) FROM employees WHERE status = 'active'").fetchone()[0]

    expiring_soon = conn.execute(
        "SELECT COUNT(*) FROM license_keys WHERE status = 'active' "
        "AND expires_at <= ? AND expires_at > ?",
        ((now + __import__('datetime').timedelta(days=7)).isoformat(), now.isoformat())
    ).fetchone()[0]

    conn.close()
    return {
        "total": total, "active": active, "expired": expired, "revoked": revoked,
        "activated": activated, "employees": employees, "expiring_soon": expiring_soon
    }


# ═══════════════════════════════════════════════════════════════════
# KEYS
# ═══════════════════════════════════════════════════════════════════

class KeyRequest(BaseModel):
    key: str
    vk_user_id: int


class GenerateRequest(BaseModel):
    organization_name: str
    expiry_days: int
    phone: str = ""
    city: str = ""
    comment: str = ""
    scan_limit: int = None


class BulkGenerateRequest(BaseModel):
    entries: list  # [{"organization_name": "...", "expiry_days": 30, ...}]


class RevokeRequest(BaseModel):
    key_id: int


class UnbindRequest(BaseModel):
    key_id: int = None
    vk_user_id: int = None


class UpdateKeyRequest(BaseModel):
    id: int
    organization_name: str = None
    phone: str = None
    city: str = None
    comment: str = None
    expiry_days: int = None


@app.get("/api/keys")
async def api_list_keys(status: str = None, search: str = "", date_from: str = None,
                         date_to: str = None, user: dict = Depends(optional_user)):
    return {"keys": list_keys(status, search)}


@app.post("/api/generate-key")
async def api_generate_key(req: GenerateRequest, user: dict = Depends(optional_user)):
    comment = req.comment
    if req.scan_limit:
        import json
        comment = json.dumps({"note": comment, "scan_limit": req.scan_limit})
    key = generate_key(req.organization_name, req.expiry_days,
                       req.phone, req.city, comment)
    log_action(int(user["sub"]), user["name"], user["role"],
                "generate_key", "key", None,
                f"Org: {req.organization_name}, days: {req.expiry_days}")
    return {"key": key}


@app.post("/api/generate-keys-bulk")
async def api_generate_keys_bulk(req: BulkGenerateRequest, user: dict = Depends(optional_user)):
    keys = []
    for entry in req.entries:
        key = generate_key(
            entry.get("organization_name", ""),
            entry.get("expiry_days", 30),
            entry.get("phone", ""),
            entry.get("city", ""),
            entry.get("comment", "")
        )
        keys.append(key)
    log_action(int(user["sub"]), user["name"], user["role"],
                "generate_keys_bulk", "key", None,
                f"Generated {len(keys)} keys")
    return {"keys": keys, "count": len(keys)}


@app.put("/api/keys/{key_id}")
async def api_update_key(key_id: int, req: UpdateKeyRequest, user: dict = Depends(optional_user)):
    import sqlite3
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "data", "qyouro.db"))
    updates = {}
    if req.organization_name is not None:
        updates["organization_name"] = req.organization_name
    if req.phone is not None:
        updates["phone"] = req.phone
    if req.city is not None:
        updates["city"] = req.city
    if req.comment is not None:
        updates["comment"] = req.comment
    if req.expiry_days is not None:
        from datetime import datetime, timezone, timedelta
        new_exp = (datetime.now(timezone.utc) + timedelta(days=req.expiry_days)).isoformat()
        updates["expires_at"] = new_exp
        updates["status"] = "active"
    for k, v in updates.items():
        conn.execute(f"UPDATE license_keys SET {k} = ? WHERE id = ?", (v, key_id))
    conn.commit()
    conn.close()
    log_action(int(user["sub"]), user["name"], user["role"],
                "update_key", "key", key_id, str(updates))
    return {"ok": True}


@app.post("/api/validate-key")
async def api_validate_key(req: KeyRequest):
    return validate_key(req.key, req.vk_user_id)


@app.post("/api/activate-key")
async def api_activate_key(req: KeyRequest):
    return activate_key(req.key, req.vk_user_id)


@app.get("/api/profile/{vk_user_id}")
async def api_profile(vk_user_id: int):
    profile = get_profile(vk_user_id)
    if profile is None:
        return JSONResponse({"error": "PROFILE_NOT_FOUND"}, status_code=404)
    scan_stats = get_scan_stats(vk_user_id, 30)
    scan_limit = get_scan_limit(vk_user_id)
    today_scans = get_today_scan_count(vk_user_id)
    profile["scan_stats"] = scan_stats
    profile["scan_limit"] = scan_limit
    profile["today_scans"] = today_scans
    return profile


@app.post("/api/revoke-key")
async def api_revoke_key(req: RevokeRequest, user: dict = Depends(optional_user)):
    ok = revoke_key(req.key_id)
    if ok:
        log_action(int(user["sub"]), user["name"], user["role"],
                    "revoke_key", "key", req.key_id)
    return {"ok": ok}


@app.post("/api/unbind-key")
async def api_unbind_key(req: UnbindRequest, user: dict = Depends(get_current_user)):
    ok = unbind_key(req.key_id, req.vk_user_id)
    if user and ok:
        log_action(int(user["sub"]), user["name"], user["role"],
                    "unbind_key", "key", req.key_id or req.vk_user_id)
    return {"ok": ok}


@app.delete("/api/keys/{key_id}")
async def api_delete_key(key_id: int, user: dict = Depends(optional_user)):
    ok = delete_key(key_id)
    if ok:
        log_action(int(user["sub"]), user["name"], user["role"],
                    "delete_key", "key", key_id)
    return {"ok": ok}


# ═══════════════════════════════════════════════════════════════════
# SCAN TRACKING
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/scan-log")
async def api_scan_log(vk_user_id: int):
    limit = get_scan_limit(vk_user_id)
    today = get_today_scan_count(vk_user_id)
    if limit is not None and today >= limit:
        return JSONResponse({"ok": False, "error": "DAILY_LIMIT_REACHED", "limit": limit, "used": today}, status_code=429)
    count = increment_scan(vk_user_id)
    return {"ok": True, "today_scans": count, "limit": limit}


@app.get("/api/scan-stats/{vk_user_id}")
async def api_scan_stats(vk_user_id: int, days: int = 30):
    return {"stats": get_scan_stats(vk_user_id, days)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8443))
    cert_dir = os.path.join(os.path.dirname(__file__), "..", "certs")
    ssl_key = os.path.join(cert_dir, "key.pem")
    ssl_cert = os.path.join(cert_dir, "cert.pem")
    if os.path.exists(ssl_key) and os.path.exists(ssl_cert) and "RENDER" not in os.environ:
        uvicorn.run("main:app", host="0.0.0.0", port=port,
                    ssl_keyfile=ssl_key, ssl_certfile=ssl_cert, reload=True)
    else:
        uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

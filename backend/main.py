import os
import sys
import numpy as np
import cv2
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from detector import detect_datamatrix_fast, detect_datamatrix_super, draw_boxes, draw_super_result
from db import generate_key, validate_key, activate_key, get_profile, list_keys, revoke_key, unbind_key, delete_key
from crpt_checker import check_cis
from auth_db import (admin_login, employee_login, admin_exists, create_admin,
                      list_employees, create_employee, update_employee, delete_employee,
                      reset_password as auth_reset_password, create_reset_token,
                      verify_reset_token, change_password_by_email)
import base64

app = FastAPI(title="Qyouro DataMatrix Detector")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


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
    return {"status": "ok", "service": "Qyouro DataMatrix Detector"}


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
    """Быстрое сканирование — scan_v5 на всём кадре."""
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
    """⚡ Интенсивное сканирование квадрата (аналог кнопки молнии)."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return JSONResponse({"code": None, "method": None, "rect": None})

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    from super_scanner import auto_scale, scan_v5
    
    # Auto-scale если изображение большое
    if max(gray.shape) > 1600:
        gray = auto_scale(gray)
    
    # Если изображение маленькое (< 150px), сканируем целиком
    if max(gray.shape) < 150:
        code, rect, method, _ = scan_v5(gray, max_total_time=8.0)
    else:
        # Иначе извлекаем центральный квадрат 40%
        sq_img = _get_square_roi(gray)
        if sq_img.shape[0] < 40 or sq_img.shape[1] < 40:
            # Если квадрат слишком маленький, сканируем целиком
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
    """📁 Интенсивное сканирование загруженного фото (полный кадр)."""
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
    """Проверить код DataMatrix в системе Честный Знак."""
    result = check_cis(req.code)
    return JSONResponse(result)


# ═══════════════════════════════════════════════════════════════════
# AUTH endpoints
# ═══════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: str
    password: str


class AdminCreateRequest(BaseModel):
    email: str
    password: str
    name: str


class EmployeeRequest(BaseModel):
    email: str
    password: str
    fio: str
    phone: str = ""
    role: str = "employee"


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


@app.get("/api/auth/check-admin")
async def check_admin():
    return {"exists": admin_exists()}

@app.post("/api/auth/register-admin")
async def register_admin(req: AdminCreateRequest):
    if admin_exists():
        return JSONResponse({"error": "Admin already exists"}, status_code=400)
    create_admin(req.email, req.password, req.name)
    return {"ok": True}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = admin_login(req.email, req.password)
    if user:
        return {"ok": True, "role": "admin", "user": user}
    user = employee_login(req.email, req.password)
    if user:
        return {"ok": True, "role": "employee", "user": user}
    return JSONResponse({"ok": False, "error": "Неверный email или пароль"}, status_code=401)

@app.get("/api/employees")
async def get_employees():
    return {"employees": list_employees()}

@app.post("/api/employees")
async def add_employee(req: EmployeeRequest):
    ok = create_employee(req.email, req.password, req.fio, req.phone, req.role)
    return {"ok": ok, "error": "Email уже занят" if not ok else None}

@app.put("/api/employees")
async def edit_employee(req: EmployeeUpdateRequest):
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None and k != "id"}
    update_employee(req.id, **kwargs)
    return {"ok": True}

@app.delete("/api/employees/{emp_id}")
async def remove_employee(emp_id: int):
    delete_employee(emp_id)
    return {"ok": True}

@app.post("/api/auth/reset-password")
async def request_reset(req: ResetRequest):
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
        auth_reset_password(req.emp_id, req.password)
        return {"ok": True}
    return JSONResponse({"ok": False, "error": "Не указаны параметры"}, status_code=400)


class KeyRequest(BaseModel):
    key: str
    vk_user_id: int


class GenerateRequest(BaseModel):
    organization_name: str
    expiry_days: int
    phone: str = ""
    city: str = ""
    comment: str = ""


class RevokeRequest(BaseModel):
    key_id: int


class UnbindRequest(BaseModel):
    key_id: int = None
    vk_user_id: int = None


@app.get("/api/keys")
async def api_list_keys(status: str = None, search: str = ""):
    return {"keys": list_keys(status, search)}


@app.post("/api/generate-key")
async def api_generate_key(req: GenerateRequest):
    key = generate_key(req.organization_name, req.expiry_days,
                       req.phone, req.city, req.comment)
    return {"key": key}


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
    return profile


@app.post("/api/revoke-key")
async def api_revoke_key(req: RevokeRequest):
    ok = revoke_key(req.key_id)
    return {"ok": ok}


@app.post("/api/unbind-key")
async def api_unbind_key(req: UnbindRequest):
    ok = unbind_key(req.key_id, req.vk_user_id)
    return {"ok": ok}


@app.delete("/api/keys/{key_id}")
async def api_delete_key(key_id: int):
    ok = delete_key(key_id)
    return {"ok": ok}


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

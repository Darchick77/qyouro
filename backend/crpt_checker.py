import requests
import time

# ═══════════════════════════════════════════════════════════════════
# API-ключ Честного Знака — получи на https://markirovka.crpt.ru
# Раздел «True API» → Создать ключ
# Без ключа будет работать публичная проверка через веб-сайт ЧЗ
# ═══════════════════════════════════════════════════════════════════
CRPT_API_KEY = ""  # ← вставь сюда API-ключ от Честного Знака

CRPT_AUTH_URL = "https://markirovka.crpt.ru/api/v3/true-api/auth/key"
CRPT_CIS_URL = "https://markirovka.crpt.ru/api/v3/true-api/cises/info"

_token_cache = {"token": None, "expires": 0}


def _get_token():
    """Получить JWT-токен для API Честного Знака."""
    if not CRPT_API_KEY:
        return None

    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]

    try:
        r = requests.post(CRPT_AUTH_URL, json={"apiKey": CRPT_API_KEY}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            token = data.get("token") or data.get("authToken")
            _token_cache["token"] = token
            _token_cache["expires"] = time.time() + 3600
            return token
    except Exception:
        pass
    return None


def check_cis(code):
    """
    Проверить код DataMatrix в системе Честный Знак.
    Возвращает словарь с информацией о товаре или None.
    """
    code = code.strip()

    # Если есть API-ключ — используем официальный API
    if CRPT_API_KEY:
        token = _get_token()
        if token:
            try:
                r = requests.get(
                    f"{CRPT_CIS_URL}?cis={code}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15
                )
                if r.status_code == 200:
                    data = r.json()
                    cis_data = data.get("cisInfo") or data.get("data") or data
                    return {
                        "found": True,
                        "product_name": _extract(cis_data, "productName", "goodsName", "name"),
                        "manufacturer": _extract(cis_data, "producerInn", "ownerInn", "manufacturer"),
                        "status": _extract(cis_data, "status", "emissionStatus"),
                        "gtin": _extract(cis_data, "gtin", "gtin"),
                        "package_type": _extract(cis_data, "packageType", "unitType"),
                        "production_date": _extract(cis_data, "productionDate", "productDate"),
                        "source": "crpt_api"
                    }
                elif r.status_code == 404:
                    return {"found": False, "reason": "Код не найден в системе"}
                else:
                    return {"found": False, "reason": f"Ошибка API: {r.status_code}"}
            except Exception as e:
                return {"found": False, "reason": f"Ошибка соединения: {str(e)[:100]}"}
        else:
            return {"found": False, "reason": "Не удалось авторизоваться в API. Проверьте CRPT_API_KEY"}

    # Без API-ключа — пробуем публичный веб-чекер
    return _check_public(code)


def _check_public(code):
    """Публичная проверка через открытые источники."""
    import urllib.request, ssl, json

    # Попытка через публичный endpoint мобильного приложения ЧЗ
    ctx = ssl.create_default_context()
    
    public_urls = [
        f"https://markirovka.crpt.ru/api/v3/true-api/cises/info?cis={code}",
    ]

    for url in public_urls:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"
            })
            r = urllib.request.urlopen(req, context=ctx, timeout=10)
            if r.status == 200:
                data = json.loads(r.read().decode())
                if data and not isinstance(data, dict):
                    continue
                if data.get("found") is False or data.get("error"):
                    continue
                if data:
                    return {
                        "found": True,
                        "product_name": _extract(data, "productName", "goodsName", "name", "title"),
                        "status": _extract(data, "status"),
                        "source": "public_api"
                    }
        except Exception:
            continue

    # Если ничего не сработало — возвращаем ссылку на веб-чекер
    return {
        "found": None,
        "reason": "Требуется API-ключ Честного Знака (вкладка True API в ЛК)",
        "web_check_url": "https://честныйзнак.рф"
    }


def _extract(data, *keys):
    """Безопасно извлечь значение по цепочке ключей."""
    if isinstance(data, dict):
        for k in keys:
            if k in data and data[k]:
                return str(data[k])
    return None

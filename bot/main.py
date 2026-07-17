import os
import requests
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN", "vk1.a.XAtzQqIzwir3KAup14kHfScscxpWcPP9fxz0o6YjMyTX9BSwlto2EsDWnUzy5z9ETw9T7pZhEuUOnLGARBRXxi-GxW_3tOMeELhK3yhJKvcrIvobfIN3VQaduQ7MSUZXLFQ9_SL6av07byLTH9uhEbwUujC_9OkHFQCFo42sMdb4BCbJQ-s9izX5n2e1ls0FbX7WA8BATNNeZu1wvcSWlQ")
BACKEND_URL = os.getenv("BACKEND_URL", "https://qyouro-1.onrender.com")
YANDEX_OPROSY_LINK = "https://forms.yandex.ru/u/6a5866a29029022444bb64ce"
VK_MINI_APP_ID = int(os.getenv("VK_MINI_APP_ID", "54682749"))
VK_MINI_APP_URL = f"https://vk.com/app{VK_MINI_APP_ID}"

user_states = {}

TEXT_WELCOME = """Добро пожаловать в Qyouro!

Сервис для обнаружения кодов DataMatrix в реальном времени.

Для начала работы получите лицензионный ключ и нажмите «Ввести ключ»."""

TEXT_HOWTO = """КАК РАБОТАТЬ С QYOURO

1. Получите лицензионный ключ у поставщика
2. Нажмите «Ввести ключ» и отправьте его боту
3. Ознакомьтесь с соглашением и примите его
4. Нажмите «Сканировать» для запуска сканера
5. Наведите камеру на DataMatrix-код

СКАНИРОВАНИЕ:
• Расстояние: 15-30 см от кода
• Освещение: равномерное, без бликов
• Приложение обводит DataMatrix зелёной рамкой"""

TEXT_SUPPORT = f"""ПОДДЕРЖКА QYOURO

Для вопросов и предложений заполните форму:
{YANDEX_OPROSY_LINK}"""

TEXT_AGREEMENT_FULL = """ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ QYOURO

1.1. Настоящее Соглашение регулирует использование сервиса Qyouro.
1.2. Используя Сервис, Пользователь принимает условия Соглашения.
1.3. Доступ предоставляется по лицензионному ключу. Один ключ — одно устройство.

2.1. Пользователь обязуется не передавать ключ третьим лицам.
2.2. Запрещена обратная разработка компонентов Сервиса.

3.1. Видеокадры обрабатываются «на лету» в оперативной памяти.
3.2. Изображения НЕ СОХРАНЯЮТСЯ и НЕ ПЕРЕДАЮТСЯ третьим лицам.

4.1. Лицензия действует в течение срока, указанного при выдаче ключа.
4.2. По истечении срока доступ прекращается.

5.1. Сервис предоставляется «как есть» (as is).
5.2. Администрация не гарантирует 100% обнаружения кодов.

Нажимая «Принимаю», вы подтверждаете согласие со всеми пунктами."""

TEXT_ENTER_KEY = """Введите ваш лицензионный ключ в ответном сообщении.

Формат: qy-xxxxxxxxxxxxxxxx"""

TEXT_KEY_VALID = """Ключ действителен!

Организация: {org}
Истекает: {expires}
Лимит сканирований: {scan_limit}

Ознакомьтесь с соглашением и нажмите «Принимаю»."""

TEXT_KEY_ACCEPTED = """Ключ активирован! Добро пожаловать, {org}.

Лицензия до: {expires}
Лимит сканирований в день: {scan_limit}

Нажмите «Сканировать» для запуска."""


def keyboard_inline_row(buttons):
    kbd = VkKeyboard(inline=True)
    for i, (label, color, payload) in enumerate(buttons):
        if i > 0:
            kbd.add_line()
        kbd.add_callback_button(label, color, payload)
    return kbd.get_keyboard()


def keyboard_guest():
    kbd = VkKeyboard(one_time=False)
    kbd.add_button("Ввести ключ", color=VkKeyboardColor.POSITIVE)
    kbd.add_button("Тарифы", color=VkKeyboardColor.PRIMARY)
    kbd.add_line()
    kbd.add_button("Как работать", color=VkKeyboardColor.SECONDARY)
    kbd.add_button("Соглашение", color=VkKeyboardColor.SECONDARY)
    kbd.add_line()
    kbd.add_button("Поддержка", color=VkKeyboardColor.SECONDARY)
    return kbd.get_keyboard()


def keyboard_active():
    kbd = VkKeyboard(one_time=False)
    kbd.add_button("Сканировать", color=VkKeyboardColor.POSITIVE)
    kbd.add_button("Мой профиль", color=VkKeyboardColor.PRIMARY)
    kbd.add_line()
    kbd.add_button("Статистика", color=VkKeyboardColor.PRIMARY)
    kbd.add_button("Тарифы", color=VkKeyboardColor.PRIMARY)
    kbd.add_line()
    kbd.add_button("Как работать", color=VkKeyboardColor.SECONDARY)
    kbd.add_button("Поддержка", color=VkKeyboardColor.SECONDARY)
    return kbd.get_keyboard()


def keyboard_scan():
    kbd = VkKeyboard(one_time=False)
    kbd.add_openlink_button("Открыть сканер", link=VK_MINI_APP_URL)
    kbd.add_line()
    kbd.add_button("Назад", color=VkKeyboardColor.SECONDARY)
    return kbd.get_keyboard()


def keyboard_agreement_accept():
    kbd = VkKeyboard(one_time=True)
    kbd.add_button("Принимаю", color=VkKeyboardColor.POSITIVE)
    kbd.add_button("Отклоняю", color=VkKeyboardColor.NEGATIVE)
    kbd.add_line()
    kbd.add_button("Назад", color=VkKeyboardColor.SECONDARY)
    return kbd.get_keyboard()


def api_validate_key(key, vk_user_id):
    try:
        r = requests.post(f"{BACKEND_URL}/api/validate-key", json={
            "key": key, "vk_user_id": vk_user_id
        }, timeout=5)
        return r.json()
    except Exception as e:
        print(f"API validate error: {e}")
        return {"valid": False, "reason": "API_ERROR"}


def api_activate_key(key, vk_user_id):
    try:
        r = requests.post(f"{BACKEND_URL}/api/activate-key", json={
            "key": key, "vk_user_id": vk_user_id
        }, timeout=5)
        return r.json()
    except Exception as e:
        print(f"API activate error: {e}")
        return {"valid": False, "reason": "API_ERROR"}


def api_get_profile(vk_user_id):
    try:
        r = requests.get(f"{BACKEND_URL}/api/profile/{vk_user_id}", timeout=5)
        if r.status_code == 404:
            return None
        return r.json()
    except Exception as e:
        print(f"API profile error: {e}")
        return None


def api_unbind_key(vk_user_id):
    try:
        r = requests.post(f"{BACKEND_URL}/api/unbind-key", json={
            "vk_user_id": vk_user_id
        }, timeout=5)
        return r.json()
    except Exception as e:
        print(f"API unbind error: {e}")
        return {"ok": False}


def send(vk, user_id, message, keyboard=None):
    vk.messages.send(
        user_id=user_id,
        random_id=get_random_id(),
        message=message,
        keyboard=keyboard
    )


def get_state(user_id):
    if user_id not in user_states:
        profile = api_get_profile(user_id)
        if profile:
            from datetime import datetime, timezone
            expire_dt = datetime.fromisoformat(profile["expires_at"])
            if expire_dt > datetime.now(timezone.utc):
                user_states[user_id] = {
                    "state": "active",
                    "organization": profile["organization_name"],
                    "expires_at": profile["expires_at"],
                    "scan_limit": profile.get("scan_limit"),
                }
                return user_states[user_id]
        user_states[user_id] = {"state": "guest"}
    return user_states[user_id]


def format_scan_limit(limit):
    if limit is None:
        return "Безлимит"
    return f"{limit} сканирований/день"


def handle_start(vk, user_id):
    send(vk, user_id, TEXT_WELCOME, keyboard_guest())


def handle_enter_key(vk, user_id):
    state = get_state(user_id)
    if state["state"] == "active":
        send(vk, user_id, "У вас уже есть активный ключ.", keyboard_active())
        return
    user_states[user_id] = {"state": "awaiting_key"}
    send(vk, user_id, TEXT_ENTER_KEY)


def handle_key_input(vk, user_id, text):
    key = text.strip()
    if not key.startswith("qy-"):
        send(vk, user_id, "Неверный формат ключа. Должен начинаться с 'qy-'. Попробуйте ещё раз:")
        return

    result = api_validate_key(key, user_id)

    if not result["valid"]:
        reasons = {
            "KEY_NOT_FOUND": "Ключ не найден.",
            "KEY_EXPIRED": "Срок действия истёк.",
            "KEY_ALREADY_USED": "Ключ уже активирован.",
            "API_ERROR": "Ошибка соединения."
        }
        msg = reasons.get(result.get("reason"), "Неизвестная ошибка.")
        send(vk, user_id, msg, keyboard_guest())
        return

    org = result["organization_name"]
    expires = result["expires_at"][:10]
    scan_limit = "Безлимит"

    user_states[user_id] = {
        "state": "agreement_pending",
        "key": key, "organization": org,
        "expires_at": result["expires_at"],
        "scan_limit": scan_limit,
    }

    msg = TEXT_KEY_VALID.format(org=org, expires=expires, scan_limit=scan_limit)
    send(vk, user_id, msg, keyboard_agreement_accept())


def handle_accept_agreement(vk, user_id):
    state = user_states.get(user_id, {})
    if state.get("state") != "agreement_pending":
        send(vk, user_id, "Нет ключа для активации.", keyboard_guest())
        return

    result = api_activate_key(state["key"], user_id)
    if not result["valid"]:
        send(vk, user_id, "Ошибка активации.", keyboard_guest())
        return

    user_states[user_id] = {
        "state": "active",
        "organization": result["organization_name"],
        "expires_at": result["expires_at"],
        "scan_limit": state.get("scan_limit"),
    }

    scan_limit = format_scan_limit(state.get("scan_limit"))
    send(vk, user_id, TEXT_KEY_ACCEPTED.format(
        org=result["organization_name"],
        expires=result["expires_at"][:10],
        scan_limit=scan_limit
    ), keyboard_active())


def handle_decline_agreement(vk, user_id):
    user_states.pop(user_id, None)
    send(vk, user_id, "Вы отклонили соглашение. Ключ не активирован.", keyboard_guest())


def handle_profile(vk, user_id):
    state = get_state(user_id)
    if state["state"] != "active":
        send(vk, user_id, "Нет активной лицензии.", keyboard_guest())
        return

    from datetime import datetime, timezone
    profile = api_get_profile(user_id) or state
    expire_dt = datetime.fromisoformat(profile.get("expires_at", state.get("expires_at")))
    days_left = max(0, (expire_dt - datetime.now(timezone.utc)).days)
    org = profile.get("organization_name", state.get("organization"))
    phone = profile.get("phone", "")
    city = profile.get("city", "")
    scan_limit = format_scan_limit(profile.get("scan_limit"))
    today_scans = profile.get("today_scans", 0)

    msg = f"""МОЙ ПРОФИЛЬ — QYOURO

Организация: {org}
Телефон: {phone or '—'}
Город: {city or '—'}
Лимит сканирований: {scan_limit}
Сегодня: {today_scans}
Осталось дней: {days_left}
Истекает: {expire_dt.strftime('%d.%m.%Y')}

Для отвязки нажмите «Отвязать ключ»."""
    send(vk, user_id, msg, keyboard_active())


def handle_stats(vk, user_id):
    state = get_state(user_id)
    if state["state"] != "active":
        send(vk, user_id, "Нет активной лицензии.", keyboard_guest())
        return

    try:
        r = requests.get(f"{BACKEND_URL}/api/scan-stats/{user_id}", timeout=5)
        data = r.json()
        stats = data.get("stats", [])
    except Exception:
        stats = []

    msg = "СТАТИСТИКА СКАНИРОВАНИЙ (30 дн.)\n\n"
    if stats:
        total = sum(s.get("count", 0) for s in stats)
        msg += f"Всего за 30 дней: {total}\n\n"
        for s in stats[:7]:
            msg += f"• {s['date']}: {s['count']} сканирований\n"
    else:
        msg += "Нет данных."

    send(vk, user_id, msg, keyboard_active())


def handle_purchase(vk, user_id):
    TEXT_BUY = """ТАРИФЫ QYOURO

Пробный — 7 дней / Бесплатно
Базовый — 1 месяц / 500 руб.
Профессиональный — 3 месяца / 1 200 руб.
Корпоративный — 12 месяцев / 4 000 руб.

Для приобретения обратитесь к поставщику."""
    send(vk, user_id, TEXT_BUY, keyboard_guest())


def handle_unbind(vk, user_id):
    result = api_unbind_key(user_id)
    user_states.pop(user_id, None)
    if result.get("ok"):
        send(vk, user_id, "Ключ отвязан.", keyboard_guest())
    else:
        send(vk, user_id, "Ошибка отвязки.", keyboard_active())


def handle_back(vk, user_id):
    state = get_state(user_id)
    if state["state"] == "active":
        send(vk, user_id, "Главное меню:", keyboard_active())
    else:
        user_states.pop(user_id, None)
        send(vk, user_id, TEXT_WELCOME, keyboard_guest())


def handle_agreement_show(vk, user_id):
    state = get_state(user_id)
    if state["state"] == "active":
        send(vk, user_id, TEXT_AGREEMENT_FULL, keyboard_active())
    elif state["state"] == "agreement_pending":
        send(vk, user_id, TEXT_AGREEMENT_FULL, keyboard_agreement_accept())
    else:
        send(vk, user_id, TEXT_AGREEMENT_FULL, keyboard_guest())


def run_bot():
    vk_session = vk_api.VkApi(token=VK_BOT_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)

    print("[Qyouro Bot v2] Started")

    for event in longpoll.listen():
        if event.type != VkEventType.MESSAGE_NEW or not event.to_me or not event.text:
            continue

        user_id = event.user_id
        text = event.text.strip()
        state = get_state(user_id)
        current = state["state"]

        if current == "awaiting_key":
            if text in ("Назад", "Отмена"):
                handle_back(vk, user_id)
            else:
                handle_key_input(vk, user_id, text)
            continue

        if current == "agreement_pending":
            if text == "Принимаю":
                handle_accept_agreement(vk, user_id)
            elif text == "Отклоняю":
                handle_decline_agreement(vk, user_id)
            elif text == "Соглашение":
                handle_agreement_show(vk, user_id)
            elif text == "Назад":
                handle_back(vk, user_id)
            else:
                send(vk, user_id, "Примите или отклоните соглашение.", keyboard_agreement_accept())
            continue

        if text.lower() in ("привет", "начать", "start", "меню", "/start", "/menu"):
            handle_start(vk, user_id)
        elif text == "Ввести ключ":
            handle_enter_key(vk, user_id)
        elif text == "Как работать":
            send(vk, user_id, TEXT_HOWTO, keyboard_active() if current == "active" else keyboard_guest())
        elif text == "Соглашение":
            handle_agreement_show(vk, user_id)
        elif text == "Поддержка":
            send(vk, user_id, TEXT_SUPPORT, keyboard_active() if current == "active" else keyboard_guest())
        elif text == "Сканировать":
            if current != "active":
                send(vk, user_id, "Сначала активируйте лицензию.", keyboard_guest())
            else:
                send(vk, user_id, "Нажмите кнопку для запуска сканера:", keyboard_scan())
        elif text == "Мой профиль":
            handle_profile(vk, user_id)
        elif text == "Статистика":
            handle_stats(vk, user_id)
        elif text == "Тарифы":
            handle_purchase(vk, user_id)
        elif text == "Отвязать ключ":
            handle_unbind(vk, user_id)
        elif text == "Назад":
            handle_back(vk, user_id)
        else:
            send(vk, user_id, "Используйте кнопки для навигации.",
                 keyboard_active() if current == "active" else keyboard_guest())


if __name__ == "__main__":
    run_bot()

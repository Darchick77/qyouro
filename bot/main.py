import os
import requests
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# ═══════════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════════

VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN", "vk1.a.XAtzQqIzwir3KAup14kHfScscxpWcPP9fxz0o6YjMyTX9BSwlto2EsDWnUzy5z9ETw9T7pZhEuUOnLGARBRXxi-GxW_3tOMeELhK3yhJKvcrIvobfIN3VQaduQ7MSUZXLFQ9_SL6av07byLTH9uhEbwUujC_9OkHFQCFo42sMdb4BCbJQ-s9izX5n2e1ls0FbX7WA8BATNNeZu1wvcSWlQ")
BACKEND_URL = os.getenv("BACKEND_URL", "https://qyouro-1.onrender.com")
YANDEX_OPROSY_LINK = "https://forms.yandex.ru/u/6a5866a29029022444bb64ce"
VK_MINI_APP_ID = int(os.getenv("VK_MINI_APP_ID", "1234567"))
VK_MINI_APP_URL = f"https://vk.com/app{VK_MINI_APP_ID}"

# ═══════════════════════════════════════════════════════════════════
# СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ
# ═══════════════════════════════════════════════════════════════════

user_states = {}

# ═══════════════════════════════════════════════════════════════════
# ТЕКСТЫ
# ═══════════════════════════════════════════════════════════════════

TEXT_WELCOME = """Добро пожаловать в Qyouro!

Сервис для обнаружения кодов DataMatrix в реальном времени.

Для начала работы получите лицензионный ключ у вашего поставщика и нажмите кнопку [Ввести ключ]."""

TEXT_HOWTO = """КАК РАБОТАТЬ С QYOURO

1. Получите лицензионный ключ у поставщика
2. Нажмите [Ввести ключ] и отправьте его боту
3. Ознакомьтесь с соглашением и примите его
4. Нажмите [Сканировать] для запуска сканера
5. Наведите камеру на DataMatrix-код

СКАНИРОВАНИЕ:
• Расстояние: 15-30 см от кода
• Освещение: равномерное, без бликов
• Ориентация: держите код прямо перед камерой
• Приложение обводит DataMatrix зелёной рамкой в реальном времени
• Работает ТОЛЬКО с DataMatrix (QR и штрихкоды игнорируются)"""

TEXT_SUPPORT = f"""ПОДДЕРЖКА QYOURO

Для вопросов, предложений или сообщений об ошибках заполните форму:

{YANDEX_OPROSY_LINK}"""

TEXT_AGREEMENT_FULL = """ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ QYOURO

1. ОБЩИЕ ПОЛОЖЕНИЯ
1.1. Настоящее Соглашение регулирует использование сервиса Qyouro (далее — «Сервис») через чат-бота и VK Mini App на платформе ВКонтакте.
1.2. Используя Сервис, Пользователь полностью принимает условия Соглашения.
1.3. Доступ к Сервису предоставляется по лицензионному ключу. Один ключ — одно устройство.

2. ПРАВИЛА ИСПОЛЬЗОВАНИЯ
2.1. Пользователь обязуется не передавать лицензионный ключ третьим лицам.
2.2. Пользователь обязуется использовать Сервис только для законных целей.
2.3. Запрещена обратная разработка (reverse engineering) компонентов Сервиса.

3. КОНФИДЕНЦИАЛЬНОСТЬ
3.1. Видеокадры обрабатываются «на лету» в оперативной памяти сервера.
3.2. Изображения НЕ СОХРАНЯЮТСЯ на диске или в базе данных.
3.3. Изображения НЕ ПЕРЕДАЮТСЯ третьим лицам.
3.4. После обработки кадра все данные немедленно удаляются из памяти.
3.5. Единственная цель обработки — обнаружение и отрисовка рамки вокруг DataMatrix-кода.

4. СРОК ДЕЙСТВИЯ
4.1. Лицензия действует в течение срока, указанного при выдаче ключа.
4.2. По истечении срока доступ к сканеру прекращается.
4.3. Для продления обратитесь к поставщику ключа.

5. ОТВЕТСТВЕННОСТЬ
5.1. Сервис предоставляется «как есть» (as is).
5.2. Администрация не гарантирует 100% обнаружения кодов при плохом качестве изображения.
5.3. Администрация не несёт ответственности за убытки, связанные с использованием Сервиса.

6. ИЗМЕНЕНИЯ
6.1. Администрация может изменять Соглашение с уведомлением через бота.
6.2. Продолжение использования означает согласие с изменениями.

Нажимая [Принимаю], вы подтверждаете, что ознакомлены и согласны со всеми пунктами."""

TEXT_AGREEMENT_SHORT = """Для активации ключа необходимо принять Пользовательское соглашение.

Нажмите [Соглашение], чтобы прочитать полный текст. Затем нажмите [Принимаю] для активации."""

TEXT_BUY = """ПРИОБРЕТЕНИЕ ЛИЦЕНЗИИ QYOURO

Выберите подходящий тариф:

 Бесплатный пробный период — 7 дней
   Ознакомьтесь с функционалом сервиса

 Базовый — 1 месяц
   Полный доступ к сканеру DataMatrix

 Профессиональный — 3 месяца
   Расширенная поддержка, приоритетная обработка

 Корпоративный — 12 месяцев
   Для организаций, до 10 устройств

Для приобретения обратитесь к поставщику через [Поддержка].

Ваш ключ будет содержать название организации и срок действия."""

TEXT_ENTER_KEY = """Введите ваш лицензионный ключ в ответном сообщении.

Ключ имеет формат: qy-xxxxxxxxxxxxxxxx"""

TEXT_KEY_VALID = """Ключ действителен!

Организация: {org}
Истекает: {expires}

Ознакомьтесь с Пользовательским соглашением и нажмите [Принимаю] для активации."""

TEXT_KEY_ACCEPTED = """Ключ активирован! Добро пожаловать, {org}.

Лицензия действует до: {expires}

Теперь вам доступен сканер DataMatrix. Нажмите [Сканировать] для запуска."""

# ═══════════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════════

def keyboard_guest():
    kbd = VkKeyboard(one_time=False)
    kbd.add_button("Ввести ключ", color=VkKeyboardColor.POSITIVE)
    kbd.add_button("Купить", color=VkKeyboardColor.PRIMARY)
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
    kbd.add_button("Купить", color=VkKeyboardColor.PRIMARY)
    kbd.add_button("Как работать", color=VkKeyboardColor.SECONDARY)
    kbd.add_line()
    kbd.add_button("Соглашение", color=VkKeyboardColor.SECONDARY)
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


def keyboard_agreement_read():
    kbd = VkKeyboard(one_time=False)
    kbd.add_button("Принимаю", color=VkKeyboardColor.POSITIVE)
    kbd.add_button("Отклоняю", color=VkKeyboardColor.NEGATIVE)
    kbd.add_line()
    kbd.add_button("Назад", color=VkKeyboardColor.SECONDARY)
    return kbd.get_keyboard()


def keyboard_purchase():
    kbd = VkKeyboard(one_time=False)
    kbd.add_button("Пробный (7 дн.)", color=VkKeyboardColor.SECONDARY)
    kbd.add_line()
    kbd.add_button("Базовый (1 мес.)", color=VkKeyboardColor.PRIMARY)
    kbd.add_button("Про (3 мес.)", color=VkKeyboardColor.PRIMARY)
    kbd.add_line()
    kbd.add_button("Корпоративный (12 мес.)", color=VkKeyboardColor.POSITIVE)
    kbd.add_line()
    kbd.add_button("Назад", color=VkKeyboardColor.SECONDARY)
    return kbd.get_keyboard()


def keyboard_unbind_confirm():
    kbd = VkKeyboard(one_time=True)
    kbd.add_button("Подтвердить отвязку", color=VkKeyboardColor.NEGATIVE)
    kbd.add_line()
    kbd.add_button("Отмена", color=VkKeyboardColor.SECONDARY)
    return kbd.get_keyboard()


# ═══════════════════════════════════════════════════════════════════
# API-ЗАПРОСЫ К БЭКЕНДУ
# ═══════════════════════════════════════════════════════════════════

def api_validate_key(key, vk_user_id):
    try:
        r = requests.post(f"{BACKEND_URL}/api/validate-key", json={
            "key": key, "vk_user_id": vk_user_id
        }, verify=False, timeout=5)
        return r.json()
    except Exception as e:
        print(f"API validate error: {e}")
        return {"valid": False, "reason": "API_ERROR"}


def api_activate_key(key, vk_user_id):
    try:
        r = requests.post(f"{BACKEND_URL}/api/activate-key", json={
            "key": key, "vk_user_id": vk_user_id
        }, verify=False, timeout=5)
        return r.json()
    except Exception as e:
        print(f"API activate error: {e}")
        return {"valid": False, "reason": "API_ERROR"}


def api_get_profile(vk_user_id):
    try:
        r = requests.get(f"{BACKEND_URL}/api/profile/{vk_user_id}", verify=False, timeout=5)
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
        }, verify=False, timeout=5)
        return r.json()
    except Exception as e:
        print(f"API unbind error: {e}")
        return {"ok": False}


# ═══════════════════════════════════════════════════════════════════
# ПОМОЩНИКИ
# ═══════════════════════════════════════════════════════════════════

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
                    "expires_at": profile["expires_at"]
                }
                return user_states[user_id]
        user_states[user_id] = {"state": "guest"}
    return user_states[user_id]


# ═══════════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ
# ═══════════════════════════════════════════════════════════════════

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
        send(vk, user_id, "Неверный формат ключа. Ключ должен начинаться с 'qy-'. Попробуйте ещё раз:")
        return

    result = api_validate_key(key, user_id)

    if not result["valid"]:
        reasons = {
            "KEY_NOT_FOUND": "Ключ не найден. Проверьте правильность ввода.",
            "KEY_EXPIRED": "Срок действия ключа истёк. Обратитесь к поставщику.",
            "KEY_ALREADY_USED": "Ключ уже активирован на другом устройстве.",
            "API_ERROR": "Ошибка соединения с сервером. Попробуйте позже."
        }
        msg = reasons.get(result.get("reason"), "Неизвестная ошибка.")
        send(vk, user_id, msg, keyboard_guest())
        return

    org = result["organization_name"]
    expires = result["expires_at"][:10]

    user_states[user_id] = {
        "state": "agreement_pending",
        "key": key,
        "organization": org,
        "expires_at": result["expires_at"]
    }

    msg = TEXT_KEY_VALID.format(org=org, expires=expires)
    send(vk, user_id, msg, keyboard_agreement_accept())


def handle_accept_agreement(vk, user_id):
    state = user_states.get(user_id, {})
    if state.get("state") != "agreement_pending":
        send(vk, user_id, "Нет ключа для активации. Нажмите [Ввести ключ].", keyboard_guest())
        return

    key = state["key"]
    result = api_activate_key(key, user_id)

    if not result["valid"]:
        send(vk, user_id, "Ошибка активации. Попробуйте позже.", keyboard_guest())
        return

    org = result["organization_name"]
    expires = result["expires_at"][:10]

    user_states[user_id] = {
        "state": "active",
        "organization": org,
        "expires_at": result["expires_at"]
    }

    send(vk, user_id, TEXT_KEY_ACCEPTED.format(org=org, expires=expires), keyboard_active())


def handle_decline_agreement(vk, user_id):
    user_states.pop(user_id, None)
    send(vk, user_id, "Вы отклонили соглашение. Ключ не активирован.", keyboard_guest())


def handle_profile(vk, user_id):
    state = get_state(user_id)
    if state["state"] != "active":
        send(vk, user_id, "У вас нет активной лицензии. Нажмите [Ввести ключ] для активации.", keyboard_guest())
        return

    from datetime import datetime, timezone
    profile = api_get_profile(user_id) or state
    expire_dt = datetime.fromisoformat(profile.get("expires_at", state.get("expires_at")))
    days_left = max(0, (expire_dt - datetime.now(timezone.utc)).days)
    org = profile.get("organization_name", state.get("organization"))
    phone = profile.get("phone", "")
    city = profile.get("city", "")
    comment = profile.get("comment", "")

    msg = f"""МОЙ ПРОФИЛЬ — QYOURO

Организация: {org}
Телефон: {phone or '—'}
Город: {city or '—'}
Комментарий: {comment or '—'}
Статус: Активна
Осталось дней: {days_left}
Истекает: {expire_dt.strftime('%d.%m.%Y')}

Для отвязки ключа от аккаунта нажмите [Отвязать ключ]."""
    send(vk, user_id, msg, keyboard_unbind_confirm())


def handle_purchase(vk, user_id):
    send(vk, user_id, TEXT_BUY, keyboard_purchase())


def handle_purchase_option(vk, user_id, option):
    prices = {
        "Пробный (7 дн.)": "Бесплатно",
        "Базовый (1 мес.)": "500 руб.",
        "Про (3 мес.)": "1 200 руб.",
        "Корпоративный (12 мес.)": "4 000 руб."
    }
    price = prices.get(option, "цена по запросу")
    msg = f"""Тариф: {option}
Стоимость: {price}

Для приобретения обратитесь к поставщику через раздел [Поддержка].

После оплаты вы получите лицензионный ключ."""
    send(vk, user_id, msg, keyboard_purchase())


def handle_unbind(vk, user_id):
    result = api_unbind_key(user_id)
    user_states.pop(user_id, None)
    if result.get("ok"):
        send(vk, user_id, "Ключ успешно отвязан от аккаунта. Вы можете активировать новый ключ.", keyboard_guest())
    else:
        send(vk, user_id, "Ошибка отвязки. Попробуйте позже.", keyboard_active())


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
        send(vk, user_id, TEXT_AGREEMENT_FULL, keyboard_agreement_read())
    else:
        send(vk, user_id, TEXT_AGREEMENT_FULL, keyboard_guest())


# ═══════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ЦИКЛ
# ═══════════════════════════════════════════════════════════════════

def run_bot():
    vk_session = vk_api.VkApi(token=VK_BOT_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)

    print("[Qyouro Bot] Started, listening...")

    for event in longpoll.listen():
        if event.type != VkEventType.MESSAGE_NEW or not event.to_me or not event.text:
            continue

        user_id = event.user_id
        text = event.text.strip()

        state = get_state(user_id)
        current = state["state"]

        # --- Состояние: ожидание ввода ключа ---
        if current == "awaiting_key":
            if text in ("Назад", "Отмена"):
                handle_back(vk, user_id)
            else:
                handle_key_input(vk, user_id, text)
            continue

        # --- Состояние: ожидание принятия соглашения ---
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
                send(vk, user_id, "Пожалуйста, примите или отклоните соглашение.", keyboard_agreement_accept())
            continue

        # --- Кнопки для всех ---
        if text in ("привет", "начать", "start", "меню", "/start", "/menu"):
            handle_start(vk, user_id)

        elif text == "Ввести ключ":
            handle_enter_key(vk, user_id)

        elif text == "Как работать":
            send(vk, user_id, TEXT_HOWTO, keyboard_active() if current == "active" else keyboard_guest())

        elif text == "Соглашение":
            handle_agreement_show(vk, user_id)

        elif text == "Поддержка":
            send(vk, user_id, TEXT_SUPPORT, keyboard_active() if current == "active" else keyboard_guest())

        # --- Кнопки для активных ---
        elif text == "Сканировать":
            if current != "active":
                send(vk, user_id, "Сначала активируйте лицензию. Нажмите [Ввести ключ].", keyboard_guest())
            else:
                send(vk, user_id, "Нажмите кнопку ниже для запуска сканера DataMatrix:", keyboard_scan())

        elif text == "Мой профиль":
            handle_profile(vk, user_id)

        elif text == "Подтвердить отвязку":
            if current != "active":
                send(vk, user_id, "У вас нет активной лицензии.", keyboard_guest())
            else:
                handle_unbind(vk, user_id)

        elif text == "Отмена":
            if current == "active":
                send(vk, user_id, "Действие отменено.", keyboard_active())
            else:
                handle_back(vk, user_id)

        # --- Покупка ---
        elif text == "Купить":
            handle_purchase(vk, user_id)

        elif text in ("Пробный (7 дн.)", "Базовый (1 мес.)", "Про (3 мес.)", "Корпоративный (12 мес.)"):
            handle_purchase_option(vk, user_id, text)

        elif text == "Назад":
            handle_back(vk, user_id)

        else:
            send(vk, user_id, "Используйте кнопки клавиатуры для навигации.",
                 keyboard_active() if current == "active" else keyboard_guest())


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    run_bot()

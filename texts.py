"""Все тексты для пользователя — в одном месте, на русском.

Меняйте тексты здесь, чтобы быстро адаптировать бота под конкретный салон.
Функции используются там, где нужна подстановка значений.
"""
from __future__ import annotations

from datetime import datetime

# ----------------------------------------------------------------------------
# Общие
# ----------------------------------------------------------------------------
WEEKDAYS_FULL = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]
WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def fmt_date(dt: datetime) -> str:
    """'13 июня (Пт)'."""
    return f"{dt.day} {MONTHS_GENITIVE[dt.month - 1]} ({WEEKDAYS_SHORT[dt.weekday()]})"


def fmt_dt(dt: datetime) -> str:
    """'13 июня (Пт), 15:30'."""
    return f"{fmt_date(dt)}, {dt:%H:%M}"


def fmt_price(price: int) -> str:
    return f"{price} ₽"


def fmt_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} мин"
    hours, mins = divmod(minutes, 60)
    if mins == 0:
        return f"{hours} ч"
    return f"{hours} ч {mins} мин"


# ----------------------------------------------------------------------------
# Главное меню / клиент
# ----------------------------------------------------------------------------
def greeting(business_name: str) -> str:
    return (
        f"💈 <b>{business_name}</b>\n\n"
        "Добро пожаловать! Я помогу записаться онлайн.\n"
        "Выберите действие в меню ниже 👇"
    )


def contacts(business_name: str, address: str, phone: str) -> str:
    lines = [f"💈 <b>{business_name}</b>", ""]
    if address:
        lines.append(f"📍 Адрес: {address}")
    if phone:
        lines.append(f"📞 Телефон: {phone}")
    if not address and not phone:
        lines.append("Контактная информация скоро появится.")
    return "\n".join(lines)


def contacts_branches(business_name: str, phone: str, branches: list[tuple[str, str]]) -> str:
    lines = [f"💈 <b>{business_name}</b>", ""]
    for name, address in branches:
        lines.append(f"📍 <b>{name}</b>")
        if address:
            lines.append(f"   {address}")
    if phone:
        lines.append("")
        lines.append(f"📞 {phone}")
    return "\n".join(lines)


BTN_BOOK = "📝 Записаться"
BTN_MY_BOOKINGS = "📅 Мои записи"
BTN_WORKS = "🖼 Наши работы"
BTN_CONTACTS = "📍 Адрес и контакты"
BTN_ADMIN = "⚙️ Админ-панель"
BTN_BACK = "⬅️ Назад"
BTN_CANCEL = "❌ Отмена"
BTN_MAIN_MENU = "🏠 Главное меню"

MENU_PROMPT = "Главное меню:"

# ----------------------------------------------------------------------------
# Сценарий записи (FSM)
# ----------------------------------------------------------------------------
CHOOSE_BRANCH = "Выберите филиал:"
NO_BRANCHES = "Сейчас нет доступных филиалов. Загляните позже."
CHOOSE_SERVICE = "Выберите услугу:"
NO_SERVICES = "К сожалению, сейчас нет доступных услуг. Загляните позже."
CHOOSE_MASTER = "Выберите мастера 👇"
NO_MASTERS = "К сожалению, сейчас нет доступных мастеров. Загляните позже."
BTN_CHOOSE_MASTER = "✅ Выбрать"


def master_card(name: str, description: str) -> str:
    cap = f"👤 <b>{name}</b>"
    if description:
        cap += f"\n{description}"
    return cap
CHOOSE_DATE = "Выберите дату:"
NO_DATES = (
    "На ближайшие дни нет доступных дат у этого мастера.\n"
    "Попробуйте выбрать другого мастера или загляните позже."
)
CHOOSE_TIME = "Выберите время:"
NO_SLOTS = (
    "На эту дату свободных слотов не осталось 😔\n"
    "Выберите другую дату."
)

ASK_NAME = "Как вас зовут? Напишите имя или подтвердите текущее."
NAME_TOO_SHORT = "Имя слишком короткое. Введите, пожалуйста, ваше имя:"
BTN_CONFIRM_NAME = "✅ Оставить «{name}»"

ASK_PHONE = (
    "Поделитесь номером телефона — нажмите кнопку ниже "
    "или введите номер вручную сообщением."
)
BTN_SHARE_PHONE = "📱 Отправить номер"
PHONE_INVALID = (
    "Не похоже на телефонный номер. Введите номер в формате "
    "+7XXXXXXXXXX или нажмите кнопку «Отправить номер»."
)


def branch_line(branch_name: str, branch_address: str = "") -> str:
    """Строка с филиалом (для сводок/уведомлений). Пусто, если филиала нет."""
    if not branch_name:
        return ""
    line = f"📍 Филиал: <b>{branch_name}</b>"
    if branch_address:
        line += f" — {branch_address}"
    return line + "\n"


def booking_summary(
    *, service_title: str, master_name: str, start_dt: datetime,
    price: int, duration_min: int, branch_name: str = "", branch_address: str = "",
) -> str:
    return (
        "Проверьте детали записи:\n\n"
        f"{branch_line(branch_name, branch_address)}"
        f"💈 Услуга: <b>{service_title}</b>\n"
        f"👤 Мастер: <b>{master_name}</b>\n"
        f"📅 Дата и время: <b>{fmt_dt(start_dt)}</b>\n"
        f"⏱ Длительность: {fmt_duration(duration_min)}\n"
        f"💰 Стоимость: {fmt_price(price)}\n\n"
        "Всё верно?"
    )


CONFIRM_PROMPT = "Нажмите, чтобы подтвердить запись 👇"
BTN_CONFIRM_BOOKING = "✅ Подтвердить запись"

SLOT_TAKEN = (
    "Упс! Этот слот только что заняли. "
    "Пожалуйста, выберите другое время."
)


def booking_created(
    *, business_name: str, service_title: str, master_name: str,
    start_dt: datetime, price: int, address: str,
    branch_name: str = "", branch_address: str = "",
) -> str:
    lines = [
        "✅ <b>Вы записаны!</b>",
        "",
        f"💈 {business_name}",
        f"Услуга: <b>{service_title}</b>",
        f"Мастер: <b>{master_name}</b>",
        f"Когда: <b>{fmt_dt(start_dt)}</b>",
        f"Стоимость: {fmt_price(price)}",
    ]
    if branch_name:
        loc = branch_name + (f", {branch_address}" if branch_address else "")
        lines.append(f"📍 {loc}")
    elif address:
        lines.append(f"📍 {address}")
    lines.append("")
    lines.append("Мы напомним вам о визите. До встречи! ✨")
    return "\n".join(lines)


BOOKING_CANCELLED_FLOW = "Запись отменена. Возвращаю в главное меню."

# ----------------------------------------------------------------------------
# Мои записи
# ----------------------------------------------------------------------------
MY_BOOKINGS_EMPTY = "У вас пока нет предстоящих записей.\nХотите записаться? 👇"
MY_BOOKINGS_HEADER = "Ваши предстоящие записи:"


def my_booking_line(
    *, service_title: str, master_name: str, start_dt: datetime, price: int,
    branch_name: str = "",
) -> str:
    line = (
        f"📅 <b>{fmt_dt(start_dt)}</b>\n"
        f"💈 {service_title} · 👤 {master_name} · {fmt_price(price)}"
    )
    if branch_name:
        line += f"\n📍 {branch_name}"
    return line


# ----------------------------------------------------------------------------
# Кабинет мастера
# ----------------------------------------------------------------------------
BTN_MASTER_CABINET = "👤 Мои записи (мастер)"
MASTER_CABINET_HEADER = "👤 <b>Ваши предстоящие записи</b>"
MASTER_CABINET_EMPTY = "У вас пока нет предстоящих записей."


def master_booking_line(
    *, start_dt: datetime, service_title: str, client_name: str, client_phone: str,
) -> str:
    return (
        f"🕒 <b>{fmt_dt(start_dt)}</b>\n"
        f"💈 {service_title}\n"
        f"🙋 {client_name} · 📞 {client_phone}"
    )


MASTER_BOOKING_CANCELLED = "Запись отменена, клиент уведомлён."

# --- Профиль мастера (редактирует сам мастер) ---
BTN_MASTER_PROFILE = "✏️ Мой профиль"
BTN_PROF_NAME = "✏️ Имя"
BTN_PROF_DESC = "✏️ Описание"
BTN_PROF_PHOTO = "🖼 Фото"


def master_profile(name: str, description: str, has_photo: bool) -> str:
    lines = [
        "✏️ <b>Мой профиль</b>",
        "",
        f"👤 Имя: <b>{name}</b>",
        f"📝 Описание: {description}" if description else "📝 Описание: —",
        "🖼 Фото: загружено ✅" if has_photo else "🖼 Фото: нет",
        "",
        "Это видят клиенты при выборе мастера.",
    ]
    return "\n".join(lines)


ASK_PROF_NAME = "Введите имя, как его увидят клиенты:"
ASK_PROF_DESC = (
    "Введите короткое описание/специализацию (напр. «фейды, оформление бороды»).\n"
    "Чтобы очистить — отправьте <code>-</code>."
)
ASK_PROF_PHOTO = (
    "Пришлите фото — его увидят клиенты при выборе мастера.\n"
    "Чтобы удалить фото — отправьте <code>-</code>."
)
PROF_NAME_TOO_SHORT = "Имя слишком короткое. Введите ещё раз:"
PROF_PHOTO_EXPECTED = "Это не фото. Пришлите изображение или <code>-</code> для удаления."
MASTER_PROFILE_SAVED = "✅ Профиль обновлён."


def admin_master_cancelled(
    *, master_name: str, service_title: str, start_dt: datetime,
    client_name: str, client_phone: str,
) -> str:
    return (
        "🔴 <b>Мастер отменил запись</b>\n\n"
        f"👤 Мастер: {master_name}\n"
        f"💈 {service_title}\n"
        f"🕒 {fmt_dt(start_dt)}\n"
        f"🙋 Клиент: {client_name}\n"
        f"📞 {client_phone}"
    )


BTN_CANCEL_BOOKING = "❌ Отменить"
BTN_RESCHEDULE = "🔄 Перенести"
BOOKING_CANCELLED_BY_CLIENT = "Запись отменена. Будем рады видеть вас снова!"
RESCHEDULE_PROMPT = "Перенос записи. Выберите новую дату:"
BOOKING_NOT_FOUND = "Запись не найдена или уже отменена."


def _reminder_location(address: str, branch_name: str, branch_address: str) -> str:
    if branch_name:
        return branch_name + (f", {branch_address}" if branch_address else "")
    return address


def booking_reminder_day(
    *, business_name: str, service_title: str, master_name: str,
    start_dt: datetime, address: str, branch_name: str = "", branch_address: str = "",
) -> str:
    lines = [
        "🔔 <b>Напоминание о записи</b>",
        "",
        f"Завтра вы записаны в {business_name}:",
        f"💈 {service_title}",
        f"👤 {master_name}",
        f"🕒 {fmt_dt(start_dt)}",
    ]
    loc = _reminder_location(address, branch_name, branch_address)
    if loc:
        lines.append(f"📍 {loc}")
    lines.append("")
    lines.append("Если планы изменились — отмените запись в разделе «Мои записи».")
    return "\n".join(lines)


def booking_reminder_2h(
    *, business_name: str, service_title: str, master_name: str,
    start_dt: datetime, address: str, branch_name: str = "", branch_address: str = "",
) -> str:
    lines = [
        "🔔 <b>Скоро ваш визит!</b>",
        "",
        f"Через ~2 часа вы записаны в {business_name}:",
        f"💈 {service_title}",
        f"👤 {master_name}",
        f"🕒 {start_dt:%H:%M}",
    ]
    loc = _reminder_location(address, branch_name, branch_address)
    if loc:
        lines.append(f"📍 {loc}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Уведомления администратору
# ----------------------------------------------------------------------------
def admin_new_booking(
    *, service_title: str, master_name: str, start_dt: datetime,
    client_name: str, client_phone: str, branch_name: str = "",
) -> str:
    return (
        "🟢 <b>Новая запись</b>\n\n"
        f"{branch_line(branch_name)}"
        f"💈 {service_title}\n"
        f"👤 Мастер: {master_name}\n"
        f"🕒 {fmt_dt(start_dt)}\n"
        f"🙋 Клиент: {client_name}\n"
        f"📞 {client_phone}"
    )


def admin_client_cancelled(
    *, service_title: str, master_name: str, start_dt: datetime,
    client_name: str, client_phone: str,
) -> str:
    return (
        "🔴 <b>Клиент отменил запись</b>\n\n"
        f"💈 {service_title}\n"
        f"👤 Мастер: {master_name}\n"
        f"🕒 {fmt_dt(start_dt)}\n"
        f"🙋 Клиент: {client_name}\n"
        f"📞 {client_phone}"
    )


def master_new_booking(
    *, service_title: str, start_dt: datetime, client_name: str, client_phone: str,
    branch_name: str = "",
) -> str:
    return (
        "🟢 <b>Новая запись к вам</b>\n\n"
        f"{branch_line(branch_name)}"
        f"💈 {service_title}\n"
        f"🕒 {fmt_dt(start_dt)}\n"
        f"🙋 Клиент: {client_name}\n"
        f"📞 {client_phone}"
    )


def master_booking_cancelled(
    *, service_title: str, start_dt: datetime, client_name: str,
) -> str:
    return (
        "🔴 <b>Запись отменена</b>\n\n"
        f"💈 {service_title}\n"
        f"🕒 {fmt_dt(start_dt)}\n"
        f"🙋 Клиент: {client_name}\n\n"
        "Слот снова свободен."
    )


def client_cancelled_by_admin(
    *, business_name: str, service_title: str, master_name: str, start_dt: datetime,
) -> str:
    return (
        "⚠️ <b>Ваша запись отменена</b>\n\n"
        f"К сожалению, запись в {business_name} отменена:\n"
        f"💈 {service_title}\n"
        f"👤 {master_name}\n"
        f"🕒 {fmt_dt(start_dt)}\n\n"
        "Приносим извинения. Вы можете записаться на другое время."
    )


# ----------------------------------------------------------------------------
# Админ-меню
# ----------------------------------------------------------------------------
ADMIN_ONLY = "Эта команда доступна только администратору."
ADMIN_MENU = "⚙️ <b>Админ-панель</b>\nВыберите раздел:"
ADMIN_BTN_BOOKINGS = "📅 Записи"
ADMIN_BTN_SERVICES = "💈 Услуги"
ADMIN_BTN_MASTERS = "👤 Мастера"
ADMIN_BTN_BRANCHES = "📍 Филиалы"
ADMIN_BTN_BLOCKS = "🚫 Блокировки"

ADMIN_BOOKINGS_PERIOD = "Записи за период:"
ADMIN_BTN_TODAY = "Сегодня"
ADMIN_BTN_TOMORROW = "Завтра"
ADMIN_BTN_WEEK = "Неделя"


def admin_bookings_header(period_label: str, count: int) -> str:
    if count == 0:
        return f"📅 <b>{period_label}</b>: записей нет."
    return f"📅 <b>{period_label}</b>: {count} зап."


def admin_booking_line(
    *, start_dt: datetime, service_title: str, master_name: str,
    client_name: str, client_phone: str,
) -> str:
    return (
        f"🕒 <b>{fmt_dt(start_dt)}</b>\n"
        f"💈 {service_title} · 👤 {master_name}\n"
        f"🙋 {client_name} · 📞 {client_phone}"
    )


ADMIN_BOOKING_CANCELLED = "Запись отменена, клиент уведомлён."

# --- Услуги ---
ADMIN_SERVICES_HEADER = "💈 <b>Услуги</b>"
ADMIN_BTN_ADD_SERVICE = "➕ Добавить услугу"


def admin_service_line(*, title: str, price: int, duration_min: int, is_active: bool) -> str:
    status = "✅" if is_active else "🚫"
    return f"{status} {title} — {fmt_price(price)}, {fmt_duration(duration_min)}"


ADMIN_BTN_EDIT_TITLE = "✏️ Название"
ADMIN_BTN_EDIT_PRICE = "💰 Цена"
ADMIN_BTN_EDIT_DURATION = "⏱ Длительность"
ADMIN_BTN_TOGGLE = "👁 Скрыть/Показать"
ADMIN_BTN_DELETE = "🗑 Удалить"

ASK_SERVICE_TITLE = "Введите название услуги:"
ASK_SERVICE_PRICE = "Введите цену в рублях (целое число), например 1500:"
ASK_SERVICE_DURATION = "Введите длительность в минутах (например 45):"
INVALID_PRICE = "Цена должна быть целым неотрицательным числом. Попробуйте снова:"
INVALID_DURATION = "Длительность должна быть целым числом от 5 до 600 минут. Попробуйте снова:"
SERVICE_SAVED = "✅ Услуга сохранена."
SERVICE_DELETED = "🗑 Услуга удалена."

# --- Мастера ---
ADMIN_MASTERS_HEADER = "👤 <b>Мастера</b>"
ADMIN_BTN_ADD_MASTER = "➕ Добавить мастера"
ADMIN_BTN_SCHEDULE = "🗓 Расписание"


def admin_master_line(*, name: str, is_active: bool) -> str:
    status = "✅" if is_active else "🚫"
    return f"{status} {name}"


ASK_MASTER_NAME = "Введите имя мастера:"
MASTER_SAVED = "✅ Мастер сохранён."
MASTER_DELETED = "🗑 Мастер удалён."
ADMIN_BTN_EDIT_NAME = "✏️ Имя"
ADMIN_BTN_MASTER_TGID = "🔗 Telegram ID"
ASK_MASTER_TGID = (
    "Отправьте <b>Telegram ID</b> мастера (число) — тогда он со своего аккаунта "
    "увидит свои записи.\nID мастер берёт у @userinfobot.\n"
    "Чтобы отвязать аккаунт — отправьте <code>-</code>."
)
INVALID_TGID = (
    "Это не похоже на Telegram ID (нужно целое число). "
    "Попробуйте снова или отправьте <code>-</code> для отвязки:"
)
MASTER_TGID_SAVED = "✅ Аккаунт мастера привязан."
MASTER_TGID_CLEARED = "✅ Привязка аккаунта снята."
ADMIN_BTN_MASTER_INVITE = "🪄 Ссылка для входа"


def master_invite_link(master_name: str, link: str) -> str:
    return (
        f"🪄 <b>Ссылка для входа — {master_name}</b>\n\n"
        "Перешлите её мастеру. Он откроет ссылку — и его аккаунт привяжется "
        "автоматически, без пароля. После этого у него появится раздел "
        "«Мои записи (мастер)».\n\n"
        f"{link}\n\n"
        "Ссылка одноразовая. Если что — создайте новую здесь же."
    )


def master_bound(master_name: str) -> str:
    return (
        f"✅ <b>Готово!</b> Вы вошли как мастер <b>{master_name}</b>.\n"
        "Откройте раздел «👤 Мои записи (мастер)» в меню — там ваши записи."
    )


INVITE_INVALID = (
    "Ссылка недействительна или уже использована. "
    "Попросите владельца создать новую."
)

SCHEDULE_HEADER = "🗓 <b>Расписание мастера {name}</b>\nНажмите на день, чтобы изменить:"


def schedule_day_line(*, weekday: int, start_time: str | None, end_time: str | None) -> str:
    day = WEEKDAYS_FULL[weekday]
    if start_time and end_time:
        return f"{day}: {start_time}–{end_time}"
    return f"{day}: выходной"


ASK_SCHEDULE_TIME = (
    "Введите рабочие часы для дня <b>{day}</b> в формате <code>10:00-20:00</code>.\n"
    "Чтобы сделать день выходным, отправьте <code>выходной</code>."
)
INVALID_SCHEDULE_TIME = (
    "Не понял формат. Введите как <code>10:00-20:00</code> "
    "или слово <code>выходной</code>:"
)
SCHEDULE_SAVED = "✅ Расписание обновлено."

# --- Филиалы ---
ADMIN_BRANCHES_HEADER = "📍 <b>Филиалы</b>"
ADMIN_BTN_ADD_BRANCH = "➕ Добавить филиал"
ADMIN_BTN_EDIT_ADDRESS = "📍 Адрес"
ADMIN_BTN_MASTER_BRANCH = "📍 Филиал"
BTN_BRANCH_NONE = "❌ Без филиала"
ASK_BRANCH_NAME = "Введите название филиала (напр. «На Гагарина»):"
ASK_BRANCH_ADDRESS = "Введите адрес филиала:"
BRANCH_SAVED = "✅ Филиал сохранён."
BRANCH_DELETED = "🗑 Филиал удалён."
MASTER_BRANCH_SAVED = "✅ Филиал мастера обновлён."
ASK_MASTER_BRANCH = "Выберите филиал мастера:"
NO_BRANCHES_ADMIN = "Филиалов пока нет. Добавьте их в разделе «📍 Филиалы»."


def admin_branch_line(*, name: str, address: str, is_active: bool) -> str:
    status = "✅" if is_active else "🚫"
    line = f"{status} {name}"
    if address:
        line += f" — {address}"
    return line


# --- Блокировки ---
ADMIN_BLOCKS_HEADER = "🚫 <b>Блокировки</b> (отпуск, болезнь, перерыв)"
ADMIN_BTN_ADD_BLOCK = "➕ Добавить блокировку"
BLOCKS_EMPTY = "Активных блокировок нет."


def admin_block_line(*, start_dt: datetime, end_dt: datetime, master_name: str, reason: str) -> str:
    scope = master_name if master_name else "весь салон"
    base = f"🚫 {fmt_dt(start_dt)} — {end_dt:%H:%M} · {scope}"
    if reason:
        base += f"\n   ({reason})"
    return base


ASK_BLOCK_MASTER = "Кого заблокировать?"
BTN_BLOCK_WHOLE_SALON = "🏠 Весь салон"
ASK_BLOCK_START = (
    "Введите начало блокировки в формате <code>2026-06-15 10:00</code>:"
)
ASK_BLOCK_END = (
    "Введите конец блокировки в формате <code>2026-06-15 14:00</code>:"
)
ASK_BLOCK_REASON = "Введите причину (или отправьте «-», чтобы пропустить):"
INVALID_DATETIME = (
    "Не понял дату/время. Формат: <code>2026-06-15 10:00</code>. Попробуйте снова:"
)
BLOCK_END_BEFORE_START = "Конец блокировки должен быть позже начала. Введите конец снова:"
BLOCK_SAVED = "✅ Блокировка добавлена."
BLOCK_DELETED = "🗑 Блокировка удалена."


# ----------------------------------------------------------------------------
# Наши работы (портфолио)
# ----------------------------------------------------------------------------
def works_caption(business_name: str) -> str:
    return f"🖼 Примеры наших работ — {business_name}"


WORKS_EMPTY = "Раздел с примерами работ пока пуст. Загляните позже!"
WORKS_BACK = "Понравилось? Запишитесь прямо сейчас 👇"

# ----------------------------------------------------------------------------
# Подписка (приостановка сервиса при неоплате)
# ----------------------------------------------------------------------------
def subscription_expired_client(business_phone: str) -> str:
    base = "🔧 Онлайн-запись временно недоступна."
    if business_phone:
        base += f"\nПожалуйста, позвоните нам: {business_phone}"
    return base


def subscription_expired_admin(provider_contact: str) -> str:
    base = (
        "⚠️ <b>Подписка на бота истекла</b>\n\n"
        "Онлайн-запись приостановлена для клиентов. "
        "Чтобы возобновить работу — продлите оплату."
    )
    if provider_contact:
        base += f"\nСвязаться: {provider_contact}"
    return base


# ----------------------------------------------------------------------------
# Ошибки / служебное
# ----------------------------------------------------------------------------
GENERIC_ERROR = "Что-то пошло не так 😔 Попробуйте ещё раз или начните заново: /start"
SESSION_EXPIRED = "Сессия устарела. Начните заново: /start"
UNKNOWN_INPUT = "Не понял 🤔 Откройте меню командой /menu"
ACTION_DONE = "Готово ✅"
NOTHING_TO_SHOW = "Здесь пока пусто."

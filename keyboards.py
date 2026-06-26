"""Сборка inline/reply клавиатур и фабрики callback-данных."""
from __future__ import annotations

from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import texts
from db.models import Service

# ---------------------------------------------------------------------------
# Фабрики callback-данных
# ---------------------------------------------------------------------------
class MenuCB(CallbackData, prefix="menu"):
    action: str  # book | my | contacts | admin | home


class BranchCB(CallbackData, prefix="bkbr"):
    id: int


class ServiceCB(CallbackData, prefix="bksvc"):
    id: int


class MasterCB(CallbackData, prefix="bkmst"):
    id: int


class DateCB(CallbackData, prefix="bkdate"):
    iso: str  # YYYY-MM-DD


class SlotCB(CallbackData, prefix="bkslot"):
    iso: str  # YYYYMMDDHHMM (local, naive) — без ':' (это разделитель callback-данных)


class FlowCB(CallbackData, prefix="bkflow"):
    action: str  # name_keep | confirm | cancel | back


class MyBookingCB(CallbackData, prefix="my"):
    action: str  # cancel | resched
    id: int


class MasterBookingCB(CallbackData, prefix="mst"):
    action: str  # cancel
    id: int


class MasterProfileCB(CallbackData, prefix="mprof"):
    field: str  # view | name | desc | photo


# --- Админ ---
class AdminCB(CallbackData, prefix="adm"):
    section: str  # home | bookings | services | masters | blocks


class AdminBookingsCB(CallbackData, prefix="admbk"):
    period: str  # today | tomorrow | week


class AdminBookingCancelCB(CallbackData, prefix="admbkc"):
    id: int


class AdminServiceCB(CallbackData, prefix="admsvc"):
    id: int  # 0 = список


class AdminServiceActCB(CallbackData, prefix="admsvca"):
    id: int
    act: str  # title | price | duration | toggle | delete


class AdminServiceAddCB(CallbackData, prefix="admsvcadd"):
    pass


class AdminMasterCB(CallbackData, prefix="admmst"):
    id: int


class AdminMasterActCB(CallbackData, prefix="admmsta"):
    id: int
    act: str  # name | toggle | delete | schedule


class AdminMasterAddCB(CallbackData, prefix="admmstadd"):
    pass


class AdminSchedDayCB(CallbackData, prefix="admsched"):
    master_id: int
    weekday: int


class AdminBranchCB(CallbackData, prefix="admbr"):
    id: int


class AdminBranchActCB(CallbackData, prefix="admbra"):
    id: int
    act: str  # name | address | toggle | delete


class AdminBranchAddCB(CallbackData, prefix="admbradd"):
    pass


class AdminMasterBranchCB(CallbackData, prefix="admmbr"):
    master_id: int
    branch_id: int  # 0 = снять филиал


class AdminBlockCB(CallbackData, prefix="admblk"):
    action: str  # add | del
    id: int  # для del


class AdminBlockMasterCB(CallbackData, prefix="admblkm"):
    master_id: int  # 0 = весь салон


# ---------------------------------------------------------------------------
# Клиентские клавиатуры
# ---------------------------------------------------------------------------
def main_menu(
    is_admin: bool, has_works: bool = False, is_master: bool = False
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BOOK, callback_data=MenuCB(action="book"))
    kb.button(text=texts.BTN_MY_BOOKINGS, callback_data=MenuCB(action="my"))
    if has_works:
        kb.button(text=texts.BTN_WORKS, callback_data=MenuCB(action="works"))
    kb.button(text=texts.BTN_CONTACTS, callback_data=MenuCB(action="contacts"))
    if is_master:
        kb.button(text=texts.BTN_MASTER_CABINET, callback_data=MenuCB(action="master"))
    if is_admin:
        kb.button(text=texts.BTN_ADMIN, callback_data=MenuCB(action="admin"))
    kb.adjust(1)
    return kb.as_markup()


def master_cabinet_kb(bookings) -> InlineKeyboardMarkup:
    """bookings: список BookingView мастера."""
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(
            text=f"❌ Отменить · {texts.fmt_dt(b.start_local)}",
            callback_data=MasterBookingCB(action="cancel", id=b.id),
        )
    kb.button(text=texts.BTN_MASTER_PROFILE, callback_data=MasterProfileCB(field="view"))
    kb.button(text=texts.BTN_MAIN_MENU, callback_data=MenuCB(action="home"))
    kb.adjust(1)
    return kb.as_markup()


def master_profile_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PROF_NAME, callback_data=MasterProfileCB(field="name"))
    kb.button(text=texts.BTN_PROF_DESC, callback_data=MasterProfileCB(field="desc"))
    kb.button(text=texts.BTN_PROF_PHOTO, callback_data=MasterProfileCB(field="photo"))
    kb.button(text=texts.BTN_MASTER_CABINET, callback_data=MenuCB(action="master"))
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_MAIN_MENU, callback_data=MenuCB(action="home"))
    return kb.as_markup()


def branches_kb(branches) -> InlineKeyboardMarkup:
    """branches: список Branch."""
    kb = InlineKeyboardBuilder()
    for b in branches:
        label = f"📍 {b.name}"
        kb.button(text=label, callback_data=BranchCB(id=b.id))
    kb.button(text=texts.BTN_CANCEL, callback_data=FlowCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def services_kb(services: list[Service]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        label = f"{s.title} · {texts.fmt_price(s.price)} · {texts.fmt_duration(s.duration_min)}"
        kb.button(text=label, callback_data=ServiceCB(id=s.id))
    kb.button(text=texts.BTN_CANCEL, callback_data=FlowCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def masters_kb(masters: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for master_id, name in masters:
        kb.button(text=f"👤 {name}", callback_data=MasterCB(id=master_id))
    kb.button(text=texts.BTN_CANCEL, callback_data=FlowCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def master_card_kb(master_id: int) -> InlineKeyboardMarkup:
    """Кнопка «Выбрать» под карточкой мастера (фото + описание)."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CHOOSE_MASTER, callback_data=MasterCB(id=master_id))
    return kb.as_markup()


def cancel_only_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CANCEL, callback_data=FlowCB(action="cancel"))
    return kb.as_markup()


def _cancel_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=texts.BTN_CANCEL, callback_data=FlowCB(action="cancel").pack()
    )


def dates_kb(dates: list[date]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in dates:
        kb.button(text=texts.fmt_date(datetime(d.year, d.month, d.day)),
                  callback_data=DateCB(iso=d.isoformat()))
    kb.adjust(2)
    kb.row(_cancel_button())  # отдельной строкой
    return kb.as_markup()


def slots_kb(slots: list[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in slots:
        kb.button(text=s.strftime("%H:%M"),
                  callback_data=SlotCB(iso=s.strftime("%Y%m%d%H%M")))
    kb.adjust(3)  # времена — по 3 в ряд
    kb.row(_cancel_button())  # кнопка отмены — отдельной строкой
    return kb.as_markup()


def confirm_name_kb(current_name: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if current_name:
        kb.button(text=texts.BTN_CONFIRM_NAME.format(name=current_name),
                  callback_data=FlowCB(action="name_keep"))
    kb.button(text=texts.BTN_CANCEL, callback_data=FlowCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def request_phone_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text=texts.BTN_SHARE_PHONE, request_contact=True))
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def confirm_booking_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CONFIRM_BOOKING, callback_data=FlowCB(action="confirm"))
    kb.button(text=texts.BTN_CANCEL, callback_data=FlowCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def my_bookings_kb(bookings) -> InlineKeyboardMarkup:
    """bookings: список BookingView."""
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(
            text=f"❌ Отменить · {texts.fmt_dt(b.start_local)}",
            callback_data=MyBookingCB(action="cancel", id=b.id),
        )
        kb.button(
            text=f"🔄 Перенести · {texts.fmt_dt(b.start_local)}",
            callback_data=MyBookingCB(action="resched", id=b.id),
        )
    kb.button(text=texts.BTN_MAIN_MENU, callback_data=MenuCB(action="home"))
    kb.adjust(2)
    return kb.as_markup()


# ---------------------------------------------------------------------------
# Админские клавиатуры
# ---------------------------------------------------------------------------
def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.ADMIN_BTN_BOOKINGS, callback_data=AdminCB(section="bookings"))
    kb.button(text=texts.ADMIN_BTN_SERVICES, callback_data=AdminCB(section="services"))
    kb.button(text=texts.ADMIN_BTN_MASTERS, callback_data=AdminCB(section="masters"))
    kb.button(text=texts.ADMIN_BTN_BRANCHES, callback_data=AdminCB(section="branches"))
    kb.button(text=texts.ADMIN_BTN_BLOCKS, callback_data=AdminCB(section="blocks"))
    kb.button(text=texts.BTN_MAIN_MENU, callback_data=MenuCB(action="home"))
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def admin_branches_kb(branches) -> InlineKeyboardMarkup:
    """branches: список Branch."""
    kb = InlineKeyboardBuilder()
    for b in branches:
        mark = "✅" if b.is_active else "🚫"
        kb.button(text=f"{mark} {b.name}", callback_data=AdminBranchCB(id=b.id))
    kb.button(text=texts.ADMIN_BTN_ADD_BRANCH, callback_data=AdminBranchAddCB())
    kb.button(text=texts.BTN_BACK, callback_data=MenuCB(action="admin"))
    kb.adjust(1)
    return kb.as_markup()


def admin_branch_detail_kb(branch_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.ADMIN_BTN_EDIT_NAME, callback_data=AdminBranchActCB(id=branch_id, act="name"))
    kb.button(text=texts.ADMIN_BTN_EDIT_ADDRESS, callback_data=AdminBranchActCB(id=branch_id, act="address"))
    kb.button(text=texts.ADMIN_BTN_TOGGLE, callback_data=AdminBranchActCB(id=branch_id, act="toggle"))
    kb.button(text=texts.ADMIN_BTN_DELETE, callback_data=AdminBranchActCB(id=branch_id, act="delete"))
    kb.button(text=texts.BTN_BACK, callback_data=AdminCB(section="branches"))
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def admin_master_branch_kb(master_id: int, branches) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in branches:
        kb.button(text=f"📍 {b.name}", callback_data=AdminMasterBranchCB(master_id=master_id, branch_id=b.id))
    kb.button(text=texts.BTN_BRANCH_NONE, callback_data=AdminMasterBranchCB(master_id=master_id, branch_id=0))
    kb.button(text=texts.BTN_BACK, callback_data=AdminMasterCB(id=master_id))
    kb.adjust(1)
    return kb.as_markup()


def admin_back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BACK, callback_data=MenuCB(action="admin"))
    return kb.as_markup()


def admin_bookings_periods() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.ADMIN_BTN_TODAY, callback_data=AdminBookingsCB(period="today"))
    kb.button(text=texts.ADMIN_BTN_TOMORROW, callback_data=AdminBookingsCB(period="tomorrow"))
    kb.button(text=texts.ADMIN_BTN_WEEK, callback_data=AdminBookingsCB(period="week"))
    kb.button(text=texts.BTN_BACK, callback_data=MenuCB(action="admin"))
    kb.adjust(3, 1)
    return kb.as_markup()


def admin_bookings_list_kb(period: str, bookings) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(
            text=f"❌ {texts.fmt_dt(b.start_local)} · {b.client_name}",
            callback_data=AdminBookingCancelCB(id=b.id),
        )
    kb.button(text=texts.BTN_BACK, callback_data=AdminCB(section="bookings"))
    kb.adjust(1)
    return kb.as_markup()


def admin_services_kb(services: list[Service]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        mark = "✅" if s.is_active else "🚫"
        kb.button(text=f"{mark} {s.title}", callback_data=AdminServiceCB(id=s.id))
    kb.button(text=texts.ADMIN_BTN_ADD_SERVICE, callback_data=AdminServiceAddCB())
    kb.button(text=texts.BTN_BACK, callback_data=MenuCB(action="admin"))
    kb.adjust(1)
    return kb.as_markup()


def admin_service_detail_kb(service_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.ADMIN_BTN_EDIT_TITLE, callback_data=AdminServiceActCB(id=service_id, act="title"))
    kb.button(text=texts.ADMIN_BTN_EDIT_PRICE, callback_data=AdminServiceActCB(id=service_id, act="price"))
    kb.button(text=texts.ADMIN_BTN_EDIT_DURATION, callback_data=AdminServiceActCB(id=service_id, act="duration"))
    kb.button(text=texts.ADMIN_BTN_TOGGLE, callback_data=AdminServiceActCB(id=service_id, act="toggle"))
    kb.button(text=texts.ADMIN_BTN_DELETE, callback_data=AdminServiceActCB(id=service_id, act="delete"))
    kb.button(text=texts.BTN_BACK, callback_data=AdminCB(section="services"))
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def admin_masters_kb(masters) -> InlineKeyboardMarkup:
    """masters: список Master."""
    kb = InlineKeyboardBuilder()
    for m in masters:
        mark = "✅" if m.is_active else "🚫"
        kb.button(text=f"{mark} {m.name}", callback_data=AdminMasterCB(id=m.id))
    kb.button(text=texts.ADMIN_BTN_ADD_MASTER, callback_data=AdminMasterAddCB())
    kb.button(text=texts.BTN_BACK, callback_data=MenuCB(action="admin"))
    kb.adjust(1)
    return kb.as_markup()


def admin_master_detail_kb(master_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.ADMIN_BTN_EDIT_NAME, callback_data=AdminMasterActCB(id=master_id, act="name"))
    kb.button(text=texts.ADMIN_BTN_SCHEDULE, callback_data=AdminMasterActCB(id=master_id, act="schedule"))
    kb.button(text=texts.ADMIN_BTN_MASTER_BRANCH, callback_data=AdminMasterActCB(id=master_id, act="branch"))
    kb.button(text=texts.ADMIN_BTN_MASTER_INVITE, callback_data=AdminMasterActCB(id=master_id, act="invite"))
    kb.button(text=texts.ADMIN_BTN_MASTER_TGID, callback_data=AdminMasterActCB(id=master_id, act="tgid"))
    kb.button(text=texts.ADMIN_BTN_TOGGLE, callback_data=AdminMasterActCB(id=master_id, act="toggle"))
    kb.button(text=texts.ADMIN_BTN_DELETE, callback_data=AdminMasterActCB(id=master_id, act="delete"))
    kb.button(text=texts.BTN_BACK, callback_data=AdminCB(section="masters"))
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()


def admin_back_to_master(master_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BACK, callback_data=AdminMasterCB(id=master_id))
    return kb.as_markup()


def admin_schedule_kb(master_id: int, schedule_by_day: dict[int, tuple[str, str] | None]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for weekday in range(7):
        rng = schedule_by_day.get(weekday)
        if rng:
            label = f"{texts.WEEKDAYS_SHORT[weekday]}: {rng[0]}–{rng[1]}"
        else:
            label = f"{texts.WEEKDAYS_SHORT[weekday]}: выходной"
        kb.button(text=label, callback_data=AdminSchedDayCB(master_id=master_id, weekday=weekday))
    kb.button(text=texts.BTN_BACK, callback_data=AdminMasterCB(id=master_id))
    kb.adjust(1)
    return kb.as_markup()


def admin_blocks_kb(blocks) -> InlineKeyboardMarkup:
    """blocks: список (id, label)."""
    kb = InlineKeyboardBuilder()
    for block_id, label in blocks:
        kb.button(text=f"🗑 {label}", callback_data=AdminBlockCB(action="del", id=block_id))
    kb.button(text=texts.ADMIN_BTN_ADD_BLOCK, callback_data=AdminBlockCB(action="add", id=0))
    kb.button(text=texts.BTN_BACK, callback_data=MenuCB(action="admin"))
    kb.adjust(1)
    return kb.as_markup()


def admin_block_master_kb(masters) -> InlineKeyboardMarkup:
    """masters: список Master."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BLOCK_WHOLE_SALON, callback_data=AdminBlockMasterCB(master_id=0))
    for m in masters:
        kb.button(text=f"👤 {m.name}", callback_data=AdminBlockMasterCB(master_id=m.id))
    kb.button(text=texts.BTN_BACK, callback_data=AdminCB(section="blocks"))
    kb.adjust(1)
    return kb.as_markup()


def cancel_inline_kb() -> InlineKeyboardMarkup:
    """Универсальная кнопка отмены ввода в админ-FSM."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CANCEL, callback_data=MenuCB(action="admin"))
    return kb.as_markup()

"""FSM сценария записи: услуга → мастер → дата → слот → имя → телефон → подтверждение.

Этот же роутер обслуживает перенос записи (reschedule): услуга и мастер берутся
из старой брони, выбирается только новый слот; при подтверждении старая бронь
отменяется, создаётся новая.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Contact, Message
from sqlalchemy import select

import keyboards as kb
import texts
from config import get_settings
from db.engine import async_session
from db.models import Booking, Branch, Master, Service
from handlers.client import show_main_menu
from services.bookings import (
    BookingView,
    SlotTakenError,
    cancel_booking,
    create_booking,
    get_active_branches,
    get_booking_view,
)
from services.notify import notify_admins_new_booking, notify_master_new_booking
from services.slots import get_available_dates, get_available_slots

logger = logging.getLogger(__name__)
settings = get_settings()
router = Router(name="booking")

PHONE_RE = re.compile(r"^\+?\d[\d\s\-()]{8,17}\d$")


class BookingStates(StatesGroup):
    branch = State()
    service = State()
    master = State()
    date = State()
    time = State()
    name = State()
    phone = State()
    confirm = State()


# ---------------------------------------------------------------------------
# Вспомогательные запросы
# ---------------------------------------------------------------------------
async def _active_services(session) -> list[Service]:
    return list(
        (await session.scalars(select(Service).where(Service.is_active.is_(True)).order_by(Service.id))).all()
    )


async def _active_masters(session, branch_id: int | None = None) -> list[Master]:
    query = select(Master).where(Master.is_active.is_(True))
    if branch_id is not None:
        query = query.where(Master.branch_id == branch_id)
    return list((await session.scalars(query.order_by(Master.id))).all())


def _slot_from_iso(iso: str) -> datetime:
    """'YYYYMMDDHHMM' (local naive) → aware datetime в таймзоне конфига."""
    return datetime.strptime(iso, "%Y%m%d%H%M").replace(tzinfo=settings.tz)


# ---------------------------------------------------------------------------
# Старт записи
# ---------------------------------------------------------------------------
@router.callback_query(kb.MenuCB.filter(F.action == "book"))
async def start_booking(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        branches = await get_active_branches(session)

    # 2+ филиалов → сначала выбор филиала; 1 или 0 → пропускаем
    if len(branches) >= 2:
        await state.set_state(BookingStates.branch)
        if isinstance(call.message, Message):
            await call.message.edit_text(texts.CHOOSE_BRANCH, reply_markup=kb.branches_kb(branches))
        await call.answer()
        return

    await state.update_data(branch_id=branches[0].id if branches else None)
    await _show_services(call, state)
    await call.answer()


async def _show_services(call: CallbackQuery, state: FSMContext) -> None:
    async with async_session() as session:
        services = await _active_services(session)
    if not isinstance(call.message, Message):
        return
    if not services:
        await call.message.edit_text(texts.NO_SERVICES, reply_markup=kb.back_to_menu())
        await state.clear()
        return
    await state.set_state(BookingStates.service)
    await call.message.edit_text(texts.CHOOSE_SERVICE, reply_markup=kb.services_kb(services))


@router.callback_query(BookingStates.branch, kb.BranchCB.filter())
async def choose_branch(
    call: CallbackQuery, callback_data: kb.BranchCB, state: FSMContext
) -> None:
    await state.update_data(branch_id=callback_data.id)
    await _show_services(call, state)
    await call.answer()


# ---------------------------------------------------------------------------
# Отмена сценария
# ---------------------------------------------------------------------------
@router.callback_query(kb.FlowCB.filter(F.action == "cancel"))
async def cancel_flow(call: CallbackQuery, state: FSMContext) -> None:
    # убираем висящие карточки мастеров, если отменили на шаге выбора
    await _delete_master_cards(call, state)
    await state.clear()
    if isinstance(call.message, Message):
        await show_main_menu(call.message, edit=True)
    await call.answer(texts.BOOKING_CANCELLED_FLOW)


# ---------------------------------------------------------------------------
# Шаг: услуга → мастер
# ---------------------------------------------------------------------------
@router.callback_query(BookingStates.service, kb.ServiceCB.filter())
async def choose_service(
    call: CallbackQuery, callback_data: kb.ServiceCB, state: FSMContext
) -> None:
    data = await state.get_data()
    async with async_session() as session:
        service = await session.get(Service, callback_data.id)
        if service is None or not service.is_active:
            await call.answer(texts.NO_SERVICES, show_alert=True)
            return
        await state.update_data(service_id=service.id)
        masters = await _active_masters(session, data.get("branch_id"))

    if not masters:
        if isinstance(call.message, Message):
            await call.message.edit_text(texts.NO_MASTERS, reply_markup=kb.back_to_menu())
        await state.clear()
        await call.answer()
        return

    if len(masters) == 1:
        # один мастер — шаг пропускается
        await state.update_data(master_id=masters[0].id)
        await _show_dates(call, state, masters[0].id, service.duration_min)
        await call.answer()
        return

    await state.set_state(BookingStates.master)
    if isinstance(call.message, Message):
        await _send_master_cards(call.message, masters, state)
    await call.answer()


async def _send_master_cards(message: Message, masters, state: FSMContext) -> None:
    """Показать мастеров карточками (фото + имя + описание), у каждой — «Выбрать»."""
    await message.edit_text(texts.CHOOSE_MASTER, reply_markup=kb.cancel_only_kb())
    card_ids: list[int] = []
    for m in masters:
        caption = texts.master_card(m.name, m.description)
        if m.photo_file_id:
            sent = await message.answer_photo(
                m.photo_file_id, caption=caption, reply_markup=kb.master_card_kb(m.id)
            )
        else:
            sent = await message.answer(caption, reply_markup=kb.master_card_kb(m.id))
        card_ids.append(sent.message_id)
    await state.update_data(master_card_ids=card_ids)


async def _delete_master_cards(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ids = data.get("master_card_ids", [])
    if not ids or not isinstance(call.message, Message):
        return
    chat_id = call.message.chat.id
    for mid in ids:
        try:
            await call.bot.delete_message(chat_id, mid)
        except Exception:  # noqa: BLE001 - карточку могли уже удалить/она устарела
            pass
    await state.update_data(master_card_ids=[])


# ---------------------------------------------------------------------------
# Шаг: мастер → дата
# ---------------------------------------------------------------------------
@router.callback_query(BookingStates.master, kb.MasterCB.filter())
async def choose_master(
    call: CallbackQuery, callback_data: kb.MasterCB, state: FSMContext
) -> None:
    data = await state.get_data()
    async with async_session() as session:
        master = await session.get(Master, callback_data.id)
        service = await session.get(Service, data["service_id"])
        if master is None or not master.is_active or service is None:
            await call.answer(texts.NO_MASTERS, show_alert=True)
            return
    await state.update_data(master_id=master.id)
    # убираем карточки мастеров и продолжаем новым сообщением
    await _delete_master_cards(call, state)
    await _show_dates(call, state, master.id, service.duration_min, send_new=True)
    await call.answer()


async def _show_dates(
    call: CallbackQuery,
    state: FSMContext,
    master_id: int,
    duration_min: int,
    prompt: str = texts.CHOOSE_DATE,
    send_new: bool = False,
) -> None:
    async with async_session() as session:
        dates = await get_available_dates(session, master_id=master_id, duration_min=duration_min)

    if not isinstance(call.message, Message):
        return

    if not dates:
        if send_new:
            await call.message.answer(texts.NO_DATES, reply_markup=kb.back_to_menu())
        else:
            await call.message.edit_text(texts.NO_DATES, reply_markup=kb.back_to_menu())
        await state.clear()
        return

    await state.set_state(BookingStates.date)
    if send_new:
        await call.message.answer(prompt, reply_markup=kb.dates_kb(dates))
    else:
        await call.message.edit_text(prompt, reply_markup=kb.dates_kb(dates))


# ---------------------------------------------------------------------------
# Шаг: дата → слот
# ---------------------------------------------------------------------------
@router.callback_query(BookingStates.date, kb.DateCB.filter())
async def choose_date(
    call: CallbackQuery, callback_data: kb.DateCB, state: FSMContext
) -> None:
    data = await state.get_data()
    day = date.fromisoformat(callback_data.iso)
    await state.update_data(date_iso=callback_data.iso)
    await _show_slots(call, state, data["master_id"], data["service_id"], day)
    await call.answer()


async def _show_slots(
    call: CallbackQuery, state: FSMContext, master_id: int, service_id: int, day: date
) -> None:
    async with async_session() as session:
        service = await session.get(Service, service_id)
        slots = await get_available_slots(
            session, master_id=master_id, duration_min=service.duration_min, day=day
        )

    if not slots:
        if isinstance(call.message, Message):
            await call.message.edit_text(texts.NO_SLOTS, reply_markup=kb.back_to_menu())
        return

    await state.set_state(BookingStates.time)
    if isinstance(call.message, Message):
        await call.message.edit_text(texts.CHOOSE_TIME, reply_markup=kb.slots_kb(slots))


# ---------------------------------------------------------------------------
# Шаг: слот → имя
# ---------------------------------------------------------------------------
@router.callback_query(BookingStates.time, kb.SlotCB.filter())
async def choose_slot(
    call: CallbackQuery, callback_data: kb.SlotCB, state: FSMContext
) -> None:
    await state.update_data(start_iso=callback_data.iso)
    await state.set_state(BookingStates.name)

    # подставляем имя: из профиля Telegram (или ранее сохранённого клиента)
    current_name = call.from_user.full_name or ""
    await state.update_data(prefill_name=current_name)

    if isinstance(call.message, Message):
        await call.message.edit_text(
            texts.ASK_NAME, reply_markup=kb.confirm_name_kb(current_name)
        )
    await call.answer()


@router.callback_query(BookingStates.name, kb.FlowCB.filter(F.action == "name_keep"))
async def keep_name(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    name = (data.get("prefill_name") or "").strip()
    if len(name) < 2:
        await call.answer(texts.NAME_TOO_SHORT, show_alert=True)
        return
    await state.update_data(name=name)
    await _ask_phone(call.message, state)
    await call.answer()


@router.message(BookingStates.name, F.text)
async def enter_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(texts.NAME_TOO_SHORT)
        return
    await state.update_data(name=name)
    await _ask_phone(message, state)


async def _ask_phone(message: Message | None, state: FSMContext) -> None:
    await state.set_state(BookingStates.phone)
    if isinstance(message, Message):
        await message.answer(texts.ASK_PHONE, reply_markup=kb.request_phone_kb())


# ---------------------------------------------------------------------------
# Шаг: телефон → подтверждение
# ---------------------------------------------------------------------------
@router.message(BookingStates.phone, F.contact)
async def enter_phone_contact(message: Message, state: FSMContext) -> None:
    contact: Contact = message.contact
    await state.update_data(phone=contact.phone_number)
    await _show_summary(message, state)


@router.message(BookingStates.phone, F.text)
async def enter_phone_text(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if not PHONE_RE.match(phone):
        await message.answer(texts.PHONE_INVALID)
        return
    await state.update_data(phone=phone)
    await _show_summary(message, state)


async def _show_summary(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    start_dt = _slot_from_iso(data["start_iso"])
    async with async_session() as session:
        service = await session.get(Service, data["service_id"])
        master = await session.get(Master, data["master_id"])
        branch = await session.get(Branch, master.branch_id) if master.branch_id else None

    summary = texts.booking_summary(
        service_title=service.title,
        master_name=master.name,
        start_dt=start_dt,
        price=service.price,
        duration_min=service.duration_min,
        branch_name=branch.name if branch else "",
        branch_address=branch.address if branch else "",
    )
    await state.set_state(BookingStates.confirm)
    # убираем reply-клавиатуру и показываем сводку с inline-подтверждением
    await message.answer(summary, reply_markup=kb.remove_kb())
    await message.answer(texts.CONFIRM_PROMPT, reply_markup=kb.confirm_booking_kb())


# ---------------------------------------------------------------------------
# Подтверждение → сохранение
# ---------------------------------------------------------------------------
@router.callback_query(BookingStates.confirm, kb.FlowCB.filter(F.action == "confirm"))
async def confirm_booking(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    start_dt = _slot_from_iso(data["start_iso"])
    reschedule_from_id = data.get("reschedule_from_id")

    try:
        async with async_session() as session:
            # перенос: гасим старую бронь в той же транзакции
            if reschedule_from_id:
                await cancel_booking(
                    session,
                    booking_id=reschedule_from_id,
                    by_telegram_id=call.from_user.id,
                )
            view = await create_booking(
                session,
                telegram_id=call.from_user.id,
                service_id=data["service_id"],
                master_id=data["master_id"],
                start_dt=start_dt,
                client_name=data.get("name", ""),
                client_phone=data.get("phone", ""),
            )
            await session.commit()
    except SlotTakenError:
        await call.answer(texts.SLOT_TAKEN, show_alert=True)
        # вернём на выбор слота этой же даты
        day = start_dt.date()
        await _show_slots(call, state, data["master_id"], data["service_id"], day)
        return

    await state.clear()

    text = texts.booking_created(
        business_name=settings.business_name,
        service_title=view.service_title,
        master_name=view.master_name,
        start_dt=view.start_local,
        price=view.service_price,
        address=settings.business_address,
        branch_name=view.branch_name,
        branch_address=view.branch_address,
    )
    if isinstance(call.message, Message):
        await call.message.edit_text(text, reply_markup=kb.back_to_menu())
    await call.answer()

    await notify_admins_new_booking(bot, view)
    await notify_master_new_booking(bot, view)


# ---------------------------------------------------------------------------
# Перенос записи (вход из «Мои записи»)
# ---------------------------------------------------------------------------
@router.callback_query(kb.MyBookingCB.filter(F.action == "resched"))
async def start_reschedule(
    call: CallbackQuery, callback_data: kb.MyBookingCB, state: FSMContext
) -> None:
    async with async_session() as session:
        view: BookingView | None = await get_booking_view(session, callback_data.id)

    if view is None or view.client_telegram_id != call.from_user.id:
        await call.answer(texts.BOOKING_NOT_FOUND, show_alert=True)
        return

    await state.clear()
    async with async_session() as session:
        booking = await session.get(Booking, callback_data.id)
        service_id = booking.service_id
        master_id = booking.master_id
        svc = await session.get(Service, service_id)
        duration_min = svc.duration_min

    await state.update_data(
        service_id=service_id,
        master_id=master_id,
        reschedule_from_id=callback_data.id,
    )
    # сразу к выбору даты (услуга и мастер унаследованы от старой брони)
    await _show_dates(call, state, master_id, duration_min, prompt=texts.RESCHEDULE_PROMPT)
    await call.answer()

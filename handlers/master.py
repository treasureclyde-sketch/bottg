"""Кабинет мастера: барбер со своего аккаунта видит свои записи и может отменить.

Роль определяется по masters.telegram_id (привязывает владелец в админке).
Мастер видит только свои записи; услуги/расписание менять не может.
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import keyboards as kb
import texts
from db.engine import async_session
from db.models import Master
from services.bookings import (
    cancel_booking,
    get_future_bookings_for_master,
    get_master_by_telegram,
)
from services.notify import (
    notify_admins_master_cancelled,
    notify_client_cancelled_by_admin,
)

logger = logging.getLogger(__name__)
router = Router(name="master")


class MasterStates(StatesGroup):
    prof_name = State()
    prof_desc = State()
    prof_photo = State()


async def _render_cabinet(call: CallbackQuery) -> None:
    if not isinstance(call.message, Message):
        return
    async with async_session() as session:
        master = await get_master_by_telegram(session, call.from_user.id)
        if master is None:
            await call.message.edit_text(texts.GENERIC_ERROR, reply_markup=kb.back_to_menu())
            return
        bookings = await get_future_bookings_for_master(session, master.id)

    if not bookings:
        await call.message.edit_text(
            texts.MASTER_CABINET_EMPTY, reply_markup=kb.master_cabinet_kb([])
        )
        return

    lines = [texts.MASTER_CABINET_HEADER, ""]
    for b in bookings:
        lines.append(
            texts.master_booking_line(
                start_dt=b.start_local,
                service_title=b.service_title,
                client_name=b.client_name,
                client_phone=b.client_phone or "—",
            )
        )
        lines.append("")
    await call.message.edit_text(
        "\n".join(lines).strip(), reply_markup=kb.master_cabinet_kb(bookings)
    )


@router.callback_query(kb.MenuCB.filter(F.action == "master"))
async def cb_master_cabinet(call: CallbackQuery) -> None:
    await _render_cabinet(call)
    await call.answer()


@router.callback_query(kb.MasterBookingCB.filter(F.action == "cancel"))
async def cb_master_cancel(
    call: CallbackQuery, callback_data: kb.MasterBookingCB, bot: Bot
) -> None:
    async with async_session() as session:
        master = await get_master_by_telegram(session, call.from_user.id)
        if master is None:
            await call.answer(texts.GENERIC_ERROR, show_alert=True)
            return
        view = await cancel_booking(
            session, booking_id=callback_data.id, by_master_id=master.id
        )
        await session.commit()

    if view is None:
        await call.answer(texts.BOOKING_NOT_FOUND, show_alert=True)
        await _render_cabinet(call)
        return

    # уведомляем клиента и владельца салона
    await notify_client_cancelled_by_admin(bot, view)
    await notify_admins_master_cancelled(bot, view)
    await call.answer(texts.MASTER_BOOKING_CANCELLED, show_alert=True)
    await _render_cabinet(call)


# ---------------------------------------------------------------------------
# Профиль мастера (редактирует сам мастер)
# ---------------------------------------------------------------------------
async def _current_master(telegram_id: int) -> Master | None:
    async with async_session() as session:
        return await get_master_by_telegram(session, telegram_id)


async def _render_profile(message: Message, telegram_id: int, *, edit: bool) -> None:
    master = await _current_master(telegram_id)
    if master is None:
        return
    text = texts.master_profile(master.name, master.description, bool(master.photo_file_id))
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb.master_profile_kb())
            return
        except Exception:  # noqa: BLE001 - предыдущее сообщение могло быть фото
            pass
    await message.answer(text, reply_markup=kb.master_profile_kb())


@router.callback_query(kb.MasterProfileCB.filter(F.field == "view"))
async def cb_profile_view(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    master = await _current_master(call.from_user.id)
    if master is None or not isinstance(call.message, Message):
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        return
    await _render_profile(call.message, call.from_user.id, edit=True)
    await call.answer()


@router.callback_query(kb.MasterProfileCB.filter(F.field != "view"))
async def cb_profile_edit(
    call: CallbackQuery, callback_data: kb.MasterProfileCB, state: FSMContext
) -> None:
    if await _current_master(call.from_user.id) is None:
        await call.answer(texts.GENERIC_ERROR, show_alert=True)
        return
    field = callback_data.field
    prompt, st = {
        "name": (texts.ASK_PROF_NAME, MasterStates.prof_name),
        "desc": (texts.ASK_PROF_DESC, MasterStates.prof_desc),
        "photo": (texts.ASK_PROF_PHOTO, MasterStates.prof_photo),
    }[field]
    await state.set_state(st)
    if isinstance(call.message, Message):
        try:
            await call.message.edit_text(prompt)
        except Exception:  # noqa: BLE001
            await call.message.answer(prompt)
    await call.answer()


async def _save_profile(telegram_id: int, **fields) -> bool:
    async with async_session() as session:
        master = await get_master_by_telegram(session, telegram_id)
        if master is None:
            return False
        for key, value in fields.items():
            setattr(master, key, value)
        await session.commit()
    return True


@router.message(MasterStates.prof_name, F.text)
async def prof_set_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(texts.PROF_NAME_TOO_SHORT)
        return
    await _save_profile(message.from_user.id, name=name)
    await state.clear()
    await message.answer(texts.MASTER_PROFILE_SAVED)
    await _render_profile(message, message.from_user.id, edit=False)


@router.message(MasterStates.prof_desc, F.text)
async def prof_set_desc(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if desc == "-":
        desc = ""
    await _save_profile(message.from_user.id, description=desc[:255])
    await state.clear()
    await message.answer(texts.MASTER_PROFILE_SAVED)
    await _render_profile(message, message.from_user.id, edit=False)


@router.message(MasterStates.prof_photo, F.photo)
async def prof_set_photo(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id  # самое крупное превью
    await _save_profile(message.from_user.id, photo_file_id=file_id)
    await state.clear()
    await message.answer(texts.MASTER_PROFILE_SAVED)
    await _render_profile(message, message.from_user.id, edit=False)


@router.message(MasterStates.prof_photo, F.text)
async def prof_clear_photo(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == "-":
        await _save_profile(message.from_user.id, photo_file_id=None)
        await state.clear()
        await message.answer(texts.MASTER_PROFILE_SAVED)
        await _render_profile(message, message.from_user.id, edit=False)
    else:
        await message.answer(texts.PROF_PHOTO_EXPECTED)

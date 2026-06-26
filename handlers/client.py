"""Клиентские хендлеры: /start, главное меню, контакты, мои записи."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

import keyboards as kb
import texts
from config import get_settings
from db.engine import async_session
from services.bookings import (
    cancel_booking,
    get_active_branches,
    get_future_bookings_for_client,
    get_master_by_telegram,
)
from services.invites import JOIN_PREFIX, redeem_invite
from services.notify import notify_admins_client_cancelled, notify_master_booking_cancelled
from services.works import has_works, list_work_photos
from handlers.filters import IsAdmin

logger = logging.getLogger(__name__)
settings = get_settings()
router = Router(name="client")


async def show_main_menu(message: Message, *, edit: bool = False) -> None:
    is_admin = settings.is_admin(message.chat.id)
    async with async_session() as session:
        is_master = await get_master_by_telegram(session, message.chat.id) is not None
    text = texts.greeting(settings.business_name)
    markup = kb.main_menu(is_admin, has_works=has_works(), is_master=is_master)
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            if "not modified" in str(exc).lower():
                return
            # иначе сообщение нельзя редактировать — отправим новым
    await message.answer(text, reply_markup=markup)


@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(
    message: Message, command: CommandObject, state: FSMContext
) -> None:
    """`/start join_<token>` — мастер привязывает свой аккаунт по ссылке-приглашению."""
    await state.clear()
    payload = command.args or ""
    if payload.startswith(JOIN_PREFIX):
        token = payload[len(JOIN_PREFIX):]
        async with async_session() as session:
            master = await redeem_invite(session, token, message.from_user.id)
            await session.commit()
        await message.answer(
            texts.master_bound(master.name) if master else texts.INVITE_INVALID
        )
    await show_main_menu(message)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_main_menu(message)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_main_menu(message)


@router.message(Command("admin"), ~IsAdmin())
async def cmd_admin_denied(message: Message) -> None:
    await message.answer(texts.ADMIN_ONLY)


@router.callback_query(kb.MenuCB.filter(F.action == "home"))
async def cb_home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await show_main_menu(call.message, edit=True)
    await call.answer()


@router.callback_query(kb.MenuCB.filter(F.action == "contacts"))
async def cb_contacts(call: CallbackQuery) -> None:
    async with async_session() as session:
        branches = await get_active_branches(session)
    if branches:
        text = texts.contacts_branches(
            settings.business_name, settings.business_phone,
            [(b.name, b.address) for b in branches],
        )
    else:
        text = texts.contacts(
            settings.business_name, settings.business_address, settings.business_phone
        )
    if isinstance(call.message, Message):
        await call.message.edit_text(text, reply_markup=kb.back_to_menu())
    await call.answer()


@router.callback_query(kb.MenuCB.filter(F.action == "works"))
async def cb_works(call: CallbackQuery) -> None:
    photos = list_work_photos()
    if not photos or not isinstance(call.message, Message):
        await call.answer(texts.WORKS_EMPTY, show_alert=True)
        return

    caption = texts.works_caption(settings.business_name)
    media = [
        InputMediaPhoto(media=FSInputFile(str(p)), caption=caption if i == 0 else None)
        for i, p in enumerate(photos)
    ]
    try:
        await call.message.answer_media_group(media)
    except Exception:  # noqa: BLE001 - битое фото не должно ронять бота
        logger.exception("Не удалось отправить альбом «Наши работы»")
        await call.answer(texts.WORKS_EMPTY, show_alert=True)
        return
    await call.message.answer(texts.WORKS_BACK, reply_markup=kb.back_to_menu())
    await call.answer()


@router.callback_query(kb.MenuCB.filter(F.action == "my"))
async def cb_my_bookings(call: CallbackQuery) -> None:
    await _render_my_bookings(call)
    await call.answer()


async def _render_my_bookings(call: CallbackQuery) -> None:
    async with async_session() as session:
        bookings = await get_future_bookings_for_client(session, call.from_user.id)

    if not isinstance(call.message, Message):
        return

    if not bookings:
        await call.message.edit_text(
            texts.MY_BOOKINGS_EMPTY, reply_markup=kb.back_to_menu()
        )
        return

    lines = [texts.MY_BOOKINGS_HEADER, ""]
    for b in bookings:
        lines.append(
            texts.my_booking_line(
                service_title=b.service_title,
                master_name=b.master_name,
                start_dt=b.start_local,
                price=b.service_price,
                branch_name=b.branch_name,
            )
        )
        lines.append("")
    await call.message.edit_text(
        "\n".join(lines).strip(), reply_markup=kb.my_bookings_kb(bookings)
    )


@router.callback_query(kb.MyBookingCB.filter(F.action == "cancel"))
async def cb_cancel_my_booking(
    call: CallbackQuery, callback_data: kb.MyBookingCB, bot: Bot
) -> None:
    async with async_session() as session:
        view = await cancel_booking(
            session, booking_id=callback_data.id, by_telegram_id=call.from_user.id
        )
        await session.commit()

    if view is None:
        await call.answer(texts.BOOKING_NOT_FOUND, show_alert=True)
        await _render_my_bookings(call)
        return

    await notify_admins_client_cancelled(bot, view)
    await notify_master_booking_cancelled(bot, view)
    await call.answer(texts.BOOKING_CANCELLED_BY_CLIENT, show_alert=True)
    await _render_my_bookings(call)

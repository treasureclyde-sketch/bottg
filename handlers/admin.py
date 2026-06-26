"""Админ-меню: записи, услуги, мастера + расписание, блокировки.

Весь раздел доступен только администраторам (фильтр IsAdmin на роутере).
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import delete, select

import keyboards as kb
import texts
from config import get_settings
from db.engine import async_session
from db.models import BlockedSlot, Branch, Master, MasterSchedule, Service
from handlers.filters import IsAdmin
from services.bookings import cancel_booking, get_active_branches, get_bookings_between
from services.invites import build_deep_link, create_invite
from services.notify import notify_client_cancelled_by_admin, notify_master_booking_cancelled

logger = logging.getLogger(__name__)
settings = get_settings()

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class AdminStates(StatesGroup):
    svc_add_title = State()
    svc_add_price = State()
    svc_add_duration = State()
    svc_edit_value = State()  # data: edit_service_id, edit_field
    mst_add_name = State()
    mst_edit_name = State()  # data: edit_master_id
    mst_edit_tgid = State()  # data: edit_master_id
    sched_time = State()  # data: sched_master_id, sched_weekday
    br_add_name = State()
    br_add_address = State()  # data: new_branch_name
    br_edit_value = State()  # data: edit_branch_id, edit_field
    blk_start = State()  # data: blk_master_id
    blk_end = State()  # data: blk_start_iso
    blk_reason = State()  # data: blk_end_iso


# ---------------------------------------------------------------------------
# Утилиты вывода (edit для callback, answer для команд/после ввода)
# ---------------------------------------------------------------------------
async def _show(message: Message, text: str, markup, edit: bool) -> None:
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            # тот же текст/разметка — Telegram отвечает "message is not modified"
            if "not modified" in str(exc).lower():
                return
            # иначе (например, сообщение нельзя редактировать) — отправим новым
    await message.answer(text, reply_markup=markup)


def _parse_local_dt(value: str) -> datetime | None:
    try:
        naive = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return naive.replace(tzinfo=settings.tz)


# ---------------------------------------------------------------------------
# Вход в админку
# ---------------------------------------------------------------------------
async def render_admin_menu(message: Message, edit: bool) -> None:
    await _show(message, texts.ADMIN_MENU, kb.admin_menu(), edit)


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await render_admin_menu(message, edit=False)


@router.callback_query(kb.MenuCB.filter(F.action == "admin"))
async def cb_admin(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await render_admin_menu(call.message, edit=True)
    await call.answer()


# ===========================================================================
# РАЗДЕЛ: ЗАПИСИ
# ===========================================================================
@router.callback_query(kb.AdminCB.filter(F.section == "bookings"))
async def cb_bookings_root(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(admin_bk_period=None)
    if isinstance(call.message, Message):
        await _show(call.message, texts.ADMIN_BOOKINGS_PERIOD, kb.admin_bookings_periods(), edit=True)
    await call.answer()


def _period_range(period: str) -> tuple[datetime, datetime, str]:
    tz = settings.tz
    today0 = datetime.combine(datetime.now(tz).date(), time.min, tzinfo=tz)
    if period == "today":
        return today0, today0 + timedelta(days=1), "Сегодня"
    if period == "tomorrow":
        return today0 + timedelta(days=1), today0 + timedelta(days=2), "Завтра"
    # week
    return today0, today0 + timedelta(days=7), "Неделя"


async def render_admin_bookings(message: Message, period: str, edit: bool) -> None:
    start, end, label = _period_range(period)
    async with async_session() as session:
        bookings = await get_bookings_between(session, start=start, end=end)

    lines = [texts.admin_bookings_header(label, len(bookings))]
    for b in bookings:
        lines.append("")
        lines.append(
            texts.admin_booking_line(
                start_dt=b.start_local,
                service_title=b.service_title,
                master_name=b.master_name,
                client_name=b.client_name,
                client_phone=b.client_phone or "—",
            )
        )
    await _show(message, "\n".join(lines), kb.admin_bookings_list_kb(period, bookings), edit)


@router.callback_query(kb.AdminBookingsCB.filter())
async def cb_bookings_period(
    call: CallbackQuery, callback_data: kb.AdminBookingsCB, state: FSMContext
) -> None:
    await state.update_data(admin_bk_period=callback_data.period)
    if isinstance(call.message, Message):
        await render_admin_bookings(call.message, callback_data.period, edit=True)
    await call.answer()


@router.callback_query(kb.AdminBookingCancelCB.filter())
async def cb_booking_cancel(
    call: CallbackQuery, callback_data: kb.AdminBookingCancelCB, state: FSMContext, bot: Bot
) -> None:
    async with async_session() as session:
        view = await cancel_booking(session, booking_id=callback_data.id)
        await session.commit()

    if view is None:
        await call.answer(texts.BOOKING_NOT_FOUND, show_alert=True)
    else:
        await notify_client_cancelled_by_admin(bot, view)
        await notify_master_booking_cancelled(bot, view)
        await call.answer(texts.ADMIN_BOOKING_CANCELLED, show_alert=True)

    data = await state.get_data()
    period = data.get("admin_bk_period") or "today"
    if isinstance(call.message, Message):
        await render_admin_bookings(call.message, period, edit=True)


# ===========================================================================
# РАЗДЕЛ: УСЛУГИ
# ===========================================================================
async def render_services(message: Message, edit: bool) -> None:
    async with async_session() as session:
        services = list((await session.scalars(select(Service).order_by(Service.id))).all())
    lines = [texts.ADMIN_SERVICES_HEADER, ""]
    if services:
        for s in services:
            lines.append(
                texts.admin_service_line(
                    title=s.title, price=s.price, duration_min=s.duration_min, is_active=s.is_active
                )
            )
    else:
        lines.append(texts.NOTHING_TO_SHOW)
    await _show(message, "\n".join(lines), kb.admin_services_kb(services), edit)


@router.callback_query(kb.AdminCB.filter(F.section == "services"))
async def cb_services(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await render_services(call.message, edit=True)
    await call.answer()


async def render_service_detail(message: Message, service_id: int, edit: bool) -> None:
    async with async_session() as session:
        s = await session.get(Service, service_id)
    if s is None:
        await _show(message, texts.SERVICE_DELETED, kb.admin_back(), edit)
        return
    text = "💈 <b>{title}</b>\nЦена: {price}\nДлительность: {dur}\nСтатус: {st}".format(
        title=s.title,
        price=texts.fmt_price(s.price),
        dur=texts.fmt_duration(s.duration_min),
        st="✅ показана" if s.is_active else "🚫 скрыта",
    )
    await _show(message, text, kb.admin_service_detail_kb(s.id), edit)


@router.callback_query(kb.AdminServiceCB.filter())
async def cb_service_detail(call: CallbackQuery, callback_data: kb.AdminServiceCB) -> None:
    if isinstance(call.message, Message):
        await render_service_detail(call.message, callback_data.id, edit=True)
    await call.answer()


@router.callback_query(kb.AdminServiceAddCB.filter())
async def cb_service_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.svc_add_title)
    if isinstance(call.message, Message):
        await _show(call.message, texts.ASK_SERVICE_TITLE, kb.cancel_inline_kb(), edit=True)
    await call.answer()


@router.message(AdminStates.svc_add_title, F.text)
async def svc_add_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer(texts.ASK_SERVICE_TITLE)
        return
    await state.update_data(new_title=title)
    await state.set_state(AdminStates.svc_add_price)
    await message.answer(texts.ASK_SERVICE_PRICE)


@router.message(AdminStates.svc_add_price, F.text)
async def svc_add_price(message: Message, state: FSMContext) -> None:
    price = _parse_int(message.text, low=0, high=1_000_000)
    if price is None:
        await message.answer(texts.INVALID_PRICE)
        return
    await state.update_data(new_price=price)
    await state.set_state(AdminStates.svc_add_duration)
    await message.answer(texts.ASK_SERVICE_DURATION)


@router.message(AdminStates.svc_add_duration, F.text)
async def svc_add_duration(message: Message, state: FSMContext) -> None:
    duration = _parse_int(message.text, low=5, high=600)
    if duration is None:
        await message.answer(texts.INVALID_DURATION)
        return
    data = await state.get_data()
    async with async_session() as session:
        session.add(
            Service(
                title=data["new_title"],
                price=data["new_price"],
                duration_min=duration,
                is_active=True,
            )
        )
        await session.commit()
    await state.clear()
    await message.answer(texts.SERVICE_SAVED)
    await render_services(message, edit=False)


@router.callback_query(kb.AdminServiceActCB.filter())
async def cb_service_action(
    call: CallbackQuery, callback_data: kb.AdminServiceActCB, state: FSMContext
) -> None:
    act = callback_data.act
    sid = callback_data.id

    if act == "toggle":
        async with async_session() as session:
            s = await session.get(Service, sid)
            if s:
                s.is_active = not s.is_active
                await session.commit()
        if isinstance(call.message, Message):
            await render_service_detail(call.message, sid, edit=True)
        await call.answer(texts.ACTION_DONE)
        return

    if act == "delete":
        async with async_session() as session:
            s = await session.get(Service, sid)
            if s:
                await session.delete(s)
                await session.commit()
        if isinstance(call.message, Message):
            await render_services(call.message, edit=True)
        await call.answer(texts.SERVICE_DELETED)
        return

    # title / price / duration → запросить новое значение
    await state.set_state(AdminStates.svc_edit_value)
    await state.update_data(edit_service_id=sid, edit_field=act)
    prompt = {
        "title": texts.ASK_SERVICE_TITLE,
        "price": texts.ASK_SERVICE_PRICE,
        "duration": texts.ASK_SERVICE_DURATION,
    }[act]
    if isinstance(call.message, Message):
        await _show(call.message, prompt, kb.cancel_inline_kb(), edit=True)
    await call.answer()


@router.message(AdminStates.svc_edit_value, F.text)
async def svc_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data["edit_field"]
    sid = data["edit_service_id"]
    raw = (message.text or "").strip()

    if field == "title":
        if len(raw) < 2:
            await message.answer(texts.ASK_SERVICE_TITLE)
            return
        value = raw
    elif field == "price":
        value = _parse_int(raw, low=0, high=1_000_000)
        if value is None:
            await message.answer(texts.INVALID_PRICE)
            return
    else:  # duration
        value = _parse_int(raw, low=5, high=600)
        if value is None:
            await message.answer(texts.INVALID_DURATION)
            return

    async with async_session() as session:
        s = await session.get(Service, sid)
        if s:
            if field == "title":
                s.title = value
            elif field == "price":
                s.price = value
            else:
                s.duration_min = value
            await session.commit()
    await state.clear()
    await message.answer(texts.SERVICE_SAVED)
    await render_service_detail(message, sid, edit=False)


# ===========================================================================
# РАЗДЕЛ: МАСТЕРА
# ===========================================================================
async def render_masters(message: Message, edit: bool) -> None:
    async with async_session() as session:
        masters = list((await session.scalars(select(Master).order_by(Master.id))).all())
    lines = [texts.ADMIN_MASTERS_HEADER, ""]
    if masters:
        for m in masters:
            lines.append(texts.admin_master_line(name=m.name, is_active=m.is_active))
    else:
        lines.append(texts.NOTHING_TO_SHOW)
    await _show(message, "\n".join(lines), kb.admin_masters_kb(masters), edit)


@router.callback_query(kb.AdminCB.filter(F.section == "masters"))
async def cb_masters(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await render_masters(call.message, edit=True)
    await call.answer()


async def render_master_detail(message: Message, master_id: int, edit: bool) -> None:
    async with async_session() as session:
        m = await session.get(Master, master_id)
        if m is None:
            await _show(message, texts.MASTER_DELETED, kb.admin_back(), edit)
            return
        branch_txt = "📍 Филиал: —"
        if m.branch_id:
            br = await session.get(Branch, m.branch_id)
            if br:
                branch_txt = f"📍 Филиал: {br.name}"
    tg = f"🔗 Telegram: <code>{m.telegram_id}</code>" if m.telegram_id else "🔗 аккаунт не привязан"
    text = "👤 <b>{name}</b>\nСтатус: {st}\n{branch}\n{tg}".format(
        name=m.name, st="✅ активен" if m.is_active else "🚫 скрыт", branch=branch_txt, tg=tg
    )
    await _show(message, text, kb.admin_master_detail_kb(m.id), edit)


@router.callback_query(kb.AdminMasterCB.filter())
async def cb_master_detail(call: CallbackQuery, callback_data: kb.AdminMasterCB) -> None:
    if isinstance(call.message, Message):
        await render_master_detail(call.message, callback_data.id, edit=True)
    await call.answer()


@router.callback_query(kb.AdminMasterAddCB.filter())
async def cb_master_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.mst_add_name)
    if isinstance(call.message, Message):
        await _show(call.message, texts.ASK_MASTER_NAME, kb.cancel_inline_kb(), edit=True)
    await call.answer()


@router.message(AdminStates.mst_add_name, F.text)
async def mst_add_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(texts.ASK_MASTER_NAME)
        return
    async with async_session() as session:
        session.add(Master(name=name, is_active=True))
        await session.commit()
    await state.clear()
    await message.answer(texts.MASTER_SAVED)
    await render_masters(message, edit=False)


@router.callback_query(kb.AdminMasterActCB.filter())
async def cb_master_action(
    call: CallbackQuery, callback_data: kb.AdminMasterActCB, state: FSMContext, bot: Bot
) -> None:
    act = callback_data.act
    mid = callback_data.id

    if act == "toggle":
        async with async_session() as session:
            m = await session.get(Master, mid)
            if m:
                m.is_active = not m.is_active
                await session.commit()
        if isinstance(call.message, Message):
            await render_master_detail(call.message, mid, edit=True)
        await call.answer(texts.ACTION_DONE)
        return

    if act == "delete":
        async with async_session() as session:
            m = await session.get(Master, mid)
            if m:
                await session.delete(m)
                await session.commit()
        if isinstance(call.message, Message):
            await render_masters(call.message, edit=True)
        await call.answer(texts.MASTER_DELETED)
        return

    if act == "name":
        await state.set_state(AdminStates.mst_edit_name)
        await state.update_data(edit_master_id=mid)
        if isinstance(call.message, Message):
            await _show(call.message, texts.ASK_MASTER_NAME, kb.cancel_inline_kb(), edit=True)
        await call.answer()
        return

    if act == "tgid":
        await state.set_state(AdminStates.mst_edit_tgid)
        await state.update_data(edit_master_id=mid)
        if isinstance(call.message, Message):
            await _show(call.message, texts.ASK_MASTER_TGID, kb.cancel_inline_kb(), edit=True)
        await call.answer()
        return

    if act == "invite":
        async with async_session() as session:
            master = await session.get(Master, mid)
            if master is None:
                await call.answer(texts.MASTER_DELETED, show_alert=True)
                return
            token = await create_invite(session, mid)
            await session.commit()
            name = master.name
        me = await bot.me()
        link = build_deep_link(me.username, token)
        if isinstance(call.message, Message):
            await _show(
                call.message,
                texts.master_invite_link(name, link),
                kb.admin_back_to_master(mid),
                edit=True,
            )
        await call.answer()
        return

    if act == "branch":
        async with async_session() as session:
            branches = await get_active_branches(session)
        if not branches:
            await call.answer(texts.NO_BRANCHES_ADMIN, show_alert=True)
            return
        if isinstance(call.message, Message):
            await _show(call.message, texts.ASK_MASTER_BRANCH,
                        kb.admin_master_branch_kb(mid, branches), edit=True)
        await call.answer()
        return

    if act == "schedule":
        if isinstance(call.message, Message):
            await render_schedule(call.message, mid, edit=True)
        await call.answer()


@router.callback_query(kb.AdminMasterBranchCB.filter())
async def cb_master_branch(
    call: CallbackQuery, callback_data: kb.AdminMasterBranchCB
) -> None:
    async with async_session() as session:
        m = await session.get(Master, callback_data.master_id)
        if m:
            m.branch_id = callback_data.branch_id or None
            await session.commit()
    await call.answer(texts.MASTER_BRANCH_SAVED)
    if isinstance(call.message, Message):
        await render_master_detail(call.message, callback_data.master_id, edit=True)


@router.message(AdminStates.mst_edit_name, F.text)
async def mst_edit_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(texts.ASK_MASTER_NAME)
        return
    data = await state.get_data()
    mid = data["edit_master_id"]
    async with async_session() as session:
        m = await session.get(Master, mid)
        if m:
            m.name = name
            await session.commit()
    await state.clear()
    await message.answer(texts.MASTER_SAVED)
    await render_master_detail(message, mid, edit=False)


@router.message(AdminStates.mst_edit_tgid, F.text)
async def mst_edit_tgid(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    data = await state.get_data()
    mid = data["edit_master_id"]

    if raw == "-":
        new_tgid = None
    else:
        tgid = _parse_int(raw, low=1, high=10**15)
        if tgid is None:
            await message.answer(texts.INVALID_TGID)
            return
        new_tgid = tgid

    async with async_session() as session:
        m = await session.get(Master, mid)
        if m:
            m.telegram_id = new_tgid
            await session.commit()
    await state.clear()
    await message.answer(texts.MASTER_TGID_CLEARED if new_tgid is None else texts.MASTER_TGID_SAVED)
    await render_master_detail(message, mid, edit=False)


# --- Расписание ---
async def _schedule_by_day(master_id: int) -> dict[int, tuple[str, str]]:
    async with async_session() as session:
        rows = (
            await session.scalars(
                select(MasterSchedule).where(MasterSchedule.master_id == master_id)
            )
        ).all()
    return {r.weekday: (r.start_time, r.end_time) for r in rows}


async def render_schedule(message: Message, master_id: int, edit: bool) -> None:
    async with async_session() as session:
        m = await session.get(Master, master_id)
    if m is None:
        await _show(message, texts.MASTER_DELETED, kb.admin_back(), edit)
        return
    by_day = await _schedule_by_day(master_id)
    text = texts.SCHEDULE_HEADER.format(name=m.name)
    await _show(message, text, kb.admin_schedule_kb(master_id, by_day), edit)


@router.callback_query(kb.AdminSchedDayCB.filter())
async def cb_schedule_day(
    call: CallbackQuery, callback_data: kb.AdminSchedDayCB, state: FSMContext
) -> None:
    await state.set_state(AdminStates.sched_time)
    await state.update_data(
        sched_master_id=callback_data.master_id, sched_weekday=callback_data.weekday
    )
    day_name = texts.WEEKDAYS_FULL[callback_data.weekday]
    if isinstance(call.message, Message):
        await _show(
            call.message,
            texts.ASK_SCHEDULE_TIME.format(day=day_name),
            kb.cancel_inline_kb(),
            edit=True,
        )
    await call.answer()


@router.message(AdminStates.sched_time, F.text)
async def sched_time(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    master_id = data["sched_master_id"]
    weekday = data["sched_weekday"]
    raw = (message.text or "").strip().lower()

    parsed: tuple[str, str] | None
    if raw in {"выходной", "выходной.", "-", "нет"}:
        parsed = None
    else:
        parsed = _parse_time_range(raw)
        if parsed is None:
            await message.answer(texts.INVALID_SCHEDULE_TIME)
            return

    async with async_session() as session:
        await session.execute(
            delete(MasterSchedule).where(
                MasterSchedule.master_id == master_id,
                MasterSchedule.weekday == weekday,
            )
        )
        if parsed is not None:
            session.add(
                MasterSchedule(
                    master_id=master_id,
                    weekday=weekday,
                    start_time=parsed[0],
                    end_time=parsed[1],
                )
            )
        await session.commit()
    await state.clear()
    await message.answer(texts.SCHEDULE_SAVED)
    await render_schedule(message, master_id, edit=False)


# ===========================================================================
# РАЗДЕЛ: ФИЛИАЛЫ
# ===========================================================================
async def render_branches(message: Message, edit: bool) -> None:
    async with async_session() as session:
        branches = list((await session.scalars(select(Branch).order_by(Branch.id))).all())
    lines = [texts.ADMIN_BRANCHES_HEADER, ""]
    if branches:
        for b in branches:
            lines.append(texts.admin_branch_line(name=b.name, address=b.address, is_active=b.is_active))
    else:
        lines.append("Филиалов нет. Для одиночного салона они не нужны.")
    await _show(message, "\n".join(lines), kb.admin_branches_kb(branches), edit)


@router.callback_query(kb.AdminCB.filter(F.section == "branches"))
async def cb_branches(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await render_branches(call.message, edit=True)
    await call.answer()


async def render_branch_detail(message: Message, branch_id: int, edit: bool) -> None:
    async with async_session() as session:
        b = await session.get(Branch, branch_id)
    if b is None:
        await _show(message, texts.BRANCH_DELETED, kb.admin_back(), edit)
        return
    text = "📍 <b>{name}</b>\nАдрес: {addr}\nСтатус: {st}".format(
        name=b.name, addr=b.address or "—",
        st="✅ показан" if b.is_active else "🚫 скрыт",
    )
    await _show(message, text, kb.admin_branch_detail_kb(b.id), edit)


@router.callback_query(kb.AdminBranchCB.filter())
async def cb_branch_detail(call: CallbackQuery, callback_data: kb.AdminBranchCB) -> None:
    if isinstance(call.message, Message):
        await render_branch_detail(call.message, callback_data.id, edit=True)
    await call.answer()


@router.callback_query(kb.AdminBranchAddCB.filter())
async def cb_branch_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.br_add_name)
    if isinstance(call.message, Message):
        await _show(call.message, texts.ASK_BRANCH_NAME, kb.cancel_inline_kb(), edit=True)
    await call.answer()


@router.message(AdminStates.br_add_name, F.text)
async def br_add_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(texts.ASK_BRANCH_NAME)
        return
    await state.update_data(new_branch_name=name)
    await state.set_state(AdminStates.br_add_address)
    await message.answer(texts.ASK_BRANCH_ADDRESS)


@router.message(AdminStates.br_add_address, F.text)
async def br_add_address(message: Message, state: FSMContext) -> None:
    address = (message.text or "").strip()
    data = await state.get_data()
    async with async_session() as session:
        session.add(Branch(name=data["new_branch_name"], address=address, is_active=True))
        await session.commit()
    await state.clear()
    await message.answer(texts.BRANCH_SAVED)
    await render_branches(message, edit=False)


@router.callback_query(kb.AdminBranchActCB.filter())
async def cb_branch_action(
    call: CallbackQuery, callback_data: kb.AdminBranchActCB, state: FSMContext
) -> None:
    act, bid = callback_data.act, callback_data.id

    if act == "toggle":
        async with async_session() as session:
            b = await session.get(Branch, bid)
            if b:
                b.is_active = not b.is_active
                await session.commit()
        if isinstance(call.message, Message):
            await render_branch_detail(call.message, bid, edit=True)
        await call.answer(texts.ACTION_DONE)
        return

    if act == "delete":
        async with async_session() as session:
            b = await session.get(Branch, bid)
            if b:
                # снимаем филиал с мастеров, чтобы не осталось висячих ссылок
                await session.execute(
                    Master.__table__.update().where(Master.branch_id == bid).values(branch_id=None)
                )
                await session.delete(b)
                await session.commit()
        if isinstance(call.message, Message):
            await render_branches(call.message, edit=True)
        await call.answer(texts.BRANCH_DELETED)
        return

    # name / address → запросить значение
    await state.set_state(AdminStates.br_edit_value)
    await state.update_data(edit_branch_id=bid, edit_field=act)
    prompt = texts.ASK_BRANCH_NAME if act == "name" else texts.ASK_BRANCH_ADDRESS
    if isinstance(call.message, Message):
        await _show(call.message, prompt, kb.cancel_inline_kb(), edit=True)
    await call.answer()


@router.message(AdminStates.br_edit_value, F.text)
async def br_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field, bid = data["edit_field"], data["edit_branch_id"]
    raw = (message.text or "").strip()
    if field == "name" and len(raw) < 2:
        await message.answer(texts.ASK_BRANCH_NAME)
        return
    async with async_session() as session:
        b = await session.get(Branch, bid)
        if b:
            if field == "name":
                b.name = raw
            else:
                b.address = raw
            await session.commit()
    await state.clear()
    await message.answer(texts.BRANCH_SAVED)
    await render_branch_detail(message, bid, edit=False)


# ===========================================================================
# РАЗДЕЛ: БЛОКИРОВКИ
# ===========================================================================
async def render_blocks(message: Message, edit: bool) -> None:
    now = datetime.now(settings.tz)
    async with async_session() as session:
        rows = (
            await session.scalars(
                select(BlockedSlot)
                .where(BlockedSlot.end_dt >= now)
                .order_by(BlockedSlot.start_dt)
            )
        ).all()
        # подгрузим имена мастеров
        masters = {m.id: m.name for m in (await session.scalars(select(Master))).all()}

    lines = [texts.ADMIN_BLOCKS_HEADER, ""]
    ui_blocks: list[tuple[int, str]] = []
    if rows:
        for b in rows:
            master_name = masters.get(b.master_id, "") if b.master_id else ""
            line = texts.admin_block_line(
                start_dt=b.start_dt.astimezone(settings.tz),
                end_dt=b.end_dt.astimezone(settings.tz),
                master_name=master_name,
                reason=b.reason,
            )
            lines.append(line)
            short = f"{b.start_dt.astimezone(settings.tz):%d.%m %H:%M}"
            ui_blocks.append((b.id, short))
    else:
        lines.append(texts.BLOCKS_EMPTY)

    await _show(message, "\n".join(lines), kb.admin_blocks_kb(ui_blocks), edit)


@router.callback_query(kb.AdminCB.filter(F.section == "blocks"))
async def cb_blocks(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(call.message, Message):
        await render_blocks(call.message, edit=True)
    await call.answer()


@router.callback_query(kb.AdminBlockCB.filter(F.action == "del"))
async def cb_block_delete(call: CallbackQuery, callback_data: kb.AdminBlockCB) -> None:
    async with async_session() as session:
        b = await session.get(BlockedSlot, callback_data.id)
        if b:
            await session.delete(b)
            await session.commit()
    if isinstance(call.message, Message):
        await render_blocks(call.message, edit=True)
    await call.answer(texts.BLOCK_DELETED)


@router.callback_query(kb.AdminBlockCB.filter(F.action == "add"))
async def cb_block_add(call: CallbackQuery, state: FSMContext) -> None:
    async with async_session() as session:
        masters = list((await session.scalars(select(Master).order_by(Master.id))).all())
    if isinstance(call.message, Message):
        await _show(call.message, texts.ASK_BLOCK_MASTER, kb.admin_block_master_kb(masters), edit=True)
    await call.answer()


@router.callback_query(kb.AdminBlockMasterCB.filter())
async def cb_block_master(
    call: CallbackQuery, callback_data: kb.AdminBlockMasterCB, state: FSMContext
) -> None:
    master_id = callback_data.master_id or None  # 0 → весь салон
    await state.set_state(AdminStates.blk_start)
    await state.update_data(blk_master_id=master_id)
    if isinstance(call.message, Message):
        await _show(call.message, texts.ASK_BLOCK_START, kb.cancel_inline_kb(), edit=True)
    await call.answer()


@router.message(AdminStates.blk_start, F.text)
async def blk_start(message: Message, state: FSMContext) -> None:
    dt = _parse_local_dt(message.text or "")
    if dt is None:
        await message.answer(texts.INVALID_DATETIME)
        return
    await state.update_data(blk_start_iso=dt.isoformat())
    await state.set_state(AdminStates.blk_end)
    await message.answer(texts.ASK_BLOCK_END)


@router.message(AdminStates.blk_end, F.text)
async def blk_end(message: Message, state: FSMContext) -> None:
    dt = _parse_local_dt(message.text or "")
    if dt is None:
        await message.answer(texts.INVALID_DATETIME)
        return
    data = await state.get_data()
    start_dt = datetime.fromisoformat(data["blk_start_iso"])
    if dt <= start_dt:
        await message.answer(texts.BLOCK_END_BEFORE_START)
        return
    await state.update_data(blk_end_iso=dt.isoformat())
    await state.set_state(AdminStates.blk_reason)
    await message.answer(texts.ASK_BLOCK_REASON)


@router.message(AdminStates.blk_reason, F.text)
async def blk_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    if reason == "-":
        reason = ""
    data = await state.get_data()
    async with async_session() as session:
        session.add(
            BlockedSlot(
                master_id=data.get("blk_master_id"),
                start_dt=datetime.fromisoformat(data["blk_start_iso"]),
                end_dt=datetime.fromisoformat(data["blk_end_iso"]),
                reason=reason,
            )
        )
        await session.commit()
    await state.clear()
    await message.answer(texts.BLOCK_SAVED)
    await render_blocks(message, edit=False)


# ---------------------------------------------------------------------------
# Парсеры
# ---------------------------------------------------------------------------
def _parse_int(value: str | None, *, low: int, high: int) -> int | None:
    if value is None:
        return None
    raw = value.strip().replace(" ", "")
    if not raw.lstrip("-").isdigit():
        return None
    num = int(raw)
    if num < low or num > high:
        return None
    return num


def _parse_time_range(value: str) -> tuple[str, str] | None:
    """'10:00-20:00' → ('10:00', '20:00') с валидацией."""
    sep = "-" if "-" in value else ("–" if "–" in value else None)
    if sep is None:
        return None
    parts = value.split(sep)
    if len(parts) != 2:
        return None
    start, end = parts[0].strip(), parts[1].strip()
    if not _valid_hhmm(start) or not _valid_hhmm(end):
        return None
    if _hhmm_to_min(start) >= _hhmm_to_min(end):
        return None
    return _norm_hhmm(start), _norm_hhmm(end)


def _valid_hhmm(value: str) -> bool:
    try:
        hh, mm = value.split(":")
        h, m = int(hh), int(mm)
    except (ValueError, AttributeError):
        return False
    return 0 <= h <= 23 and 0 <= m <= 59


def _norm_hhmm(value: str) -> str:
    hh, mm = value.split(":")
    return f"{int(hh):02d}:{int(mm):02d}"


def _hhmm_to_min(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)

"""
FSM /diary — Consensus Sleep Diary.

Пошагово собирает CSD-поля, валидирует, пересчитывает метрики
через services.metrics, сохраняет через repositories.

Заметки НЕ логируются (этика): только длина в debug-логе.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db.database import session_scope
from bot.db import repositories as repo
from bot.fsm.diary_helpers import (
    format_summary,
    parse_int,
    parse_time_hhmm,
    validate_time_order,
)
from bot.keyboards.diary import (
    activity_kb,
    cancel_kb,
    confirm_kb,
    scale_1_5_kb,
    sol_kb,
    skip_cancel_kb,
    waso_kb,
    yes_no_kb,
)
from bot.schemas.diary import CSDEntryInput
from bot.services.metrics import compute_metrics
from bot.states import DiaryStates
from bot.utils.tz import today_local

logger = logging.getLogger(__name__)
router = Router(name="diary")


# ============================================================================
# Вход в сценарий
# ============================================================================

@router.message(Command("diary"))
async def cmd_diary(message: Message, state: FSMContext, user_tg_id: int, user_tz: str) -> None:
    await state.clear()

    async with session_scope() as s:
        existing = await repo.get_entry_by_date(s, user_id=user_tg_id, entry_date=today_local(user_tz))
    if existing is not None:
        await message.answer(
            "Запись за сегодня уже есть. Используйте /stats или дождитесь завтра.",
        )
        return

    await state.update_data(entry_date=today_local(user_tz).isoformat())
    await state.set_state(DiaryStates.lights_out)
    await message.answer(
        "Дневник сна (CSD). Шаг 1/9.\n\n"
        "Во сколько вы легли в постель (lights out)?\n"
        "Формат: <b>HH:MM</b>, например <code>23:30</code>.",
        reply_markup=cancel_kb(),
    )


# ============================================================================
# 1. lights_out
# ============================================================================

@router.message(DiaryStates.lights_out, F.text)
async def on_lights_out(message: Message, state: FSMContext) -> None:
    try:
        t = parse_time_hhmm(message.text or "")
    except ValueError:
        await message.answer("Не понял время. Введите в формате HH:MM, например 23:30.")
        return
    await state.update_data(lights_out=t)
    await state.set_state(DiaryStates.try_sleep)
    await message.answer(
        "Шаг 2/9. Во сколько вы <b>попытались</b> заснуть?\n"
        "Формат: <b>HH:MM</b>. Обычно совпадает с lights out или чуть позже.",
        reply_markup=cancel_kb(),
    )


# ============================================================================
# 2. try_sleep
# ============================================================================

@router.message(DiaryStates.try_sleep, F.text)
async def on_try_sleep(message: Message, state: FSMContext) -> None:
    try:
        t = parse_time_hhmm(message.text or "")
    except ValueError:
        await message.answer("Не понял время. Введите в формате HH:MM.")
        return
    data = await state.get_data()
    if not validate_time_order(data["lights_out"], t, allow_equal=True):
        await message.answer(
            f"Время попытки заснуть ({t}) не может быть раньше lights out ({data['lights_out']}). "
            "Попробуйте снова."
        )
        return
    await state.update_data(try_sleep=t)
    await state.set_state(DiaryStates.final_wake)
    await message.answer(
        "Шаг 3/9. Во сколько вы <b>окончательно</b> встали?\n"
        "Формат: <b>HH:MM</b>. Если подъём на следующий день — это нормально.",
        reply_markup=cancel_kb(),
    )


# ============================================================================
# 3. final_wake
# ============================================================================

@router.message(DiaryStates.final_wake, F.text)
async def on_final_wake(message: Message, state: FSMContext) -> None:
    try:
        t = parse_time_hhmm(message.text or "")
    except ValueError:
        await message.answer("Не понял время. Введите в формате HH:MM.")
        return
    data = await state.get_data()
    # final_wake может быть как в тот же день, так и на следующий —
    # разрешаем любое, compute_tib сам обработает переход через полночь.
    await state.update_data(final_wake=t)
    await state.set_state(DiaryStates.sol)
    await message.answer(
        "Шаг 4/9. Сколько минут вы засыпали (SOL)?\n"
        "Можно выбрать из кнопок или ввести число.",
        reply_markup=sol_kb(),
    )


# ============================================================================
# 4. SOL
# ============================================================================

@router.callback_query(DiaryStates.sol, F.data.startswith("diary:sol:"))
async def on_sol_cb(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[2]
    if value == "manual":
        await cb.message.edit_text(
            "Введите SOL в минутах (0–600):", reply_markup=cancel_kb()
        )
        await cb.answer()
        return
    try:
        sol = parse_int(value, lo=0, hi=600)
    except ValueError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await _set_sol_and_next(cb.message, state, sol)
    await cb.answer()


@router.message(DiaryStates.sol, F.text)
async def on_sol_manual(message: Message, state: FSMContext) -> None:
    try:
        sol = parse_int(message.text or "", lo=0, hi=600)
    except ValueError as e:
        await message.answer(str(e))
        return
    await _set_sol_and_next(message, state, sol)


async def _set_sol_and_next(msg: Message, state: FSMContext, sol: int) -> None:
    await state.update_data(sol_min=sol)
    await state.set_state(DiaryStates.waso)
    await msg.answer(
        "Шаг 5/9. Суммарно сколько минут вы бодрствовали <b>после</b> засыпания (WASO)?\n"
        "Если не просыпались — выберите 0.",
        reply_markup=waso_kb(),
    )


# ============================================================================
# 5. WASO
# ============================================================================

@router.callback_query(DiaryStates.waso, F.data.startswith("diary:waso:"))
async def on_waso_cb(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[2]
    if value == "manual":
        await cb.message.edit_text(
            "Введите WASO в минутах (0–600):", reply_markup=cancel_kb()
        )
        await cb.answer()
        return
    try:
        waso = parse_int(value, lo=0, hi=600)
    except ValueError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await _set_waso_and_next(cb.message, state, waso)
    await cb.answer()


@router.message(DiaryStates.waso, F.text)
async def on_waso_manual(message: Message, state: FSMContext) -> None:
    try:
        waso = parse_int(message.text or "", lo=0, hi=600)
    except ValueError as e:
        await message.answer(str(e))
        return
    await _set_waso_and_next(message, state, waso)


async def _set_waso_and_next(msg: Message, state: FSMContext, waso: int) -> None:
    await state.update_data(waso_min=waso)
    await state.set_state(DiaryStates.awakenings)
    await msg.answer(
        "Шаг 6/9. Сколько раз вы просыпались ночью? (0–50)\n"
        "Если не просыпались — 0.",
        reply_markup=cancel_kb(),
    )


# ============================================================================
# 6. awakenings
# ============================================================================

@router.message(DiaryStates.awakenings, F.text)
async def on_awakenings(message: Message, state: FSMContext) -> None:
    try:
        n = parse_int(message.text or "", lo=0, hi=50)
    except ValueError as e:
        await message.answer(str(e))
        return
    await state.update_data(awakenings_count=n)
    await state.set_state(DiaryStates.quality)
    await message.answer(
        "Шаг 7/9. Оцените субъективное качество сна от 1 (очень плохо) до 5 (отлично):",
        reply_markup=scale_1_5_kb("diary:quality"),
    )


# ============================================================================
# 7. quality
# ============================================================================

@router.callback_query(DiaryStates.quality, F.data.startswith("diary:quality:"))
async def on_quality(cb: CallbackQuery, state: FSMContext) -> None:
    try:
        q = parse_int(cb.data.split(":")[2], lo=1, hi=5)
    except ValueError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await state.update_data(quality=q)
    await state.set_state(DiaryStates.factors_caffeine)
    await cb.message.edit_text(
        "Шаг 8/9. Факторы.\n\n"
        "Кофеин после 16:00 (кофе, чай, кола, энергетики)?",
        reply_markup=yes_no_kb("diary:caffeine"),
    )
    await cb.answer()


# ============================================================================
# 8. Факторы
# ============================================================================

@router.callback_query(DiaryStates.factors_caffeine, F.data.startswith("diary:caffeine:"))
async def on_caffeine(cb: CallbackQuery, state: FSMContext) -> None:
    val = cb.data.split(":")[2] == "yes"
    await state.update_data(caffeine_after_16=val)
    await state.set_state(DiaryStates.factors_alcohol)
    await cb.message.edit_text(
        "Алкоголь вечером?", reply_markup=yes_no_kb("diary:alcohol")
    )
    await cb.answer()


@router.callback_query(DiaryStates.factors_alcohol, F.data.startswith("diary:alcohol:"))
async def on_alcohol(cb: CallbackQuery, state: FSMContext) -> None:
    val = cb.data.split(":")[2] == "yes"
    await state.update_data(alcohol_evening=val)
    await state.set_state(DiaryStates.factors_screen)
    await cb.message.edit_text(
        "Экран за 1 ч до сна (телефон/ТВ/ноутбук)?",
        reply_markup=yes_no_kb("diary:screen"),
    )
    await cb.answer()


@router.callback_query(DiaryStates.factors_screen, F.data.startswith("diary:screen:"))
async def on_screen(cb: CallbackQuery, state: FSMContext) -> None:
    val = cb.data.split(":")[2] == "yes"
    await state.update_data(screen_before_bed=val)
    await state.set_state(DiaryStates.factors_activity)
    await cb.message.edit_text(
        "Физическая активность днём:", reply_markup=activity_kb()
    )
    await cb.answer()


@router.callback_query(DiaryStates.factors_activity, F.data.startswith("diary:activity:"))
async def on_activity(cb: CallbackQuery, state: FSMContext) -> None:
    try:
        val = parse_int(cb.data.split(":")[2], lo=0, hi=2)
    except ValueError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await state.update_data(activity_level=val)
    await state.set_state(DiaryStates.factors_stress)
    await cb.message.edit_text(
        "Уровень стресса за день (1–5):",
        reply_markup=scale_1_5_kb("diary:stress"),
    )
    await cb.answer()


@router.callback_query(DiaryStates.factors_stress, F.data.startswith("diary:stress:"))
async def on_stress(cb: CallbackQuery, state: FSMContext) -> None:
    try:
        val = parse_int(cb.data.split(":")[2], lo=1, hi=5)
    except ValueError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await state.update_data(stress_level=val)
    await state.set_state(DiaryStates.notes)
    await cb.message.edit_text(
        "Шаг 9/9. Заметки (необязательно).\n"
        "Что важно отметить: храп, остановки дыхания, яркие сны, пробуждения и т.п.\n"
        "Отправьте «-», чтобы пропустить.",
        reply_markup=skip_cancel_kb(),
    )
    await cb.answer()


# ============================================================================
# 9. notes
# ============================================================================

@router.message(DiaryStates.notes, F.text)
async def on_notes(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    notes = None if text in {"-", "—", "."} else text[:2000]
    await state.update_data(notes=notes)
    await _show_confirm(message, state)


@router.callback_query(DiaryStates.notes, F.data == "diary:skip")
async def on_notes_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(notes=None)
    await _show_confirm(cb.message, state)
    await cb.answer()


# ============================================================================
# Подтверждение
# ============================================================================

async def _show_confirm(msg: Message, state: FSMContext) -> None:
    await state.set_state(DiaryStates.confirm)
    data = await state.get_data()
    try:
        entry = _build_entry(data)
    except ValueError as e:
        await msg.answer(f"Ошибка в данных: {e}. Начните заново: /diary")
        await state.clear()
        return

    metrics = compute_metrics(
        lights_out=entry.lights_out,
        final_wake=entry.final_wake,
        sol_min=entry.sol_min,
        waso_min=entry.waso_min,
    )
    await msg.answer(
        format_summary(entry, metrics),
        reply_markup=confirm_kb(),
    )


def _build_entry(data: dict[str, Any]) -> CSDEntryInput:
    return CSDEntryInput(
        entry_date=date.fromisoformat(data["entry_date"]),
        lights_out=data["lights_out"],
        try_sleep=data["try_sleep"],
        final_wake=data["final_wake"],
        sol_min=data["sol_min"],
        waso_min=data["waso_min"],
        awakenings_count=data.get("awakenings_count", 0),
        quality=data["quality"],
        notes=data.get("notes"),
        caffeine_after_16=data.get("caffeine_after_16", False),
        alcohol_evening=data.get("alcohol_evening", False),
        screen_before_bed=data.get("screen_before_bed", False),
        activity_level=data.get("activity_level", 1),
        stress_level=data.get("stress_level", 3),
    )


@router.callback_query(DiaryStates.confirm, F.data == "diary:save")
async def on_save(cb: CallbackQuery, state: FSMContext, user_tg_id: int) -> None:
    data = await state.get_data()
    try:
        entry = _build_entry(data)
    except ValueError as e:
        await cb.message.edit_text(f"Ошибка в данных: {e}. Начните заново: /diary")
        await state.clear()
        await cb.answer()
        return

    metrics = compute_metrics(
        lights_out=entry.lights_out,
        final_wake=entry.final_wake,
        sol_min=entry.sol_min,
        waso_min=entry.waso_min,
    )

    async with session_scope() as s:
        await repo.add_sleep_entry(
            s,
            user_id=user_tg_id,
            payload={
                "entry_date": entry.entry_date,
                "lights_out": entry.lights_out,
                "try_sleep": entry.try_sleep,
                "final_wake": entry.final_wake,
                "sol_min": entry.sol_min,
                "waso_min": entry.waso_min,
                "awakenings_count": entry.awakenings_count,
                "quality": entry.quality,
                "notes": entry.notes,
                "tib_min": metrics.tib_min,
                "tst_min": metrics.tst_min,
                "se_percent": metrics.se_percent,
                "caffeine_after_16": entry.caffeine_after_16,
                "alcohol_evening": entry.alcohol_evening,
                "screen_before_bed": entry.screen_before_bed,
                "activity_level": entry.activity_level,
                "stress_level": entry.stress_level,
            },
        )

    await cb.message.edit_text(
        "Запись сохранена.\n\n"
        f"TIB: {metrics.tib_min} мин\n"
        f"TST: {metrics.tst_min} мин\n"
        f"SE: {metrics.se_percent:.1f}%\n\n"
        "См. /stats для динамики, /advice для рекомендаций.",
    )
    await state.clear()
    await cb.answer("Сохранено")


@router.callback_query(F.data == "diary:cancel")
async def on_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text("Отменено. Начать заново: /diary")
    await cb.answer()
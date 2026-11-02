"""
FSM для ISI, ESS, STOP-BANG, PSQI.

Каждый опросник — отдельный сценарий, но логика похожа:
- последовательность вопросов (индекс в state)
- инлайн-кнопки для ответов
- по завершении — подсчёт через services.questionnaires + сохранение

Общие callback'и:
    q:cancel — отмена
    q:save   — сохранение (после confirm)
"""
from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db.database import session_scope
from bot.db import repositories as repo
from bot.keyboards.questionnaires import (
    cancel_kb,
    confirm_kb,
    psqi_scale_kb,
    scale_0_3_kb,
    scale_0_4_kb,
    yes_no_kb,
)
from bot.services.questionnaires import (
    ESS_QUESTIONS,
    ISI_QUESTIONS,
    PSQIInput,
    STOPBANG_QUESTIONS,
    ScoreResult,
    score_ess,
    score_isi,
    score_psqi,
    score_stopbang,
)
from bot.states import ESSStates, ISIStates, PSQIStates, StopBangStates

logger = logging.getLogger(__name__)
router = Router(name="questionnaires")


# ============================================================================
# Общие
# ============================================================================

@router.callback_query(F.data == "q:cancel")
async def on_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text("Отменено.")
    await cb.answer()


async def _save_and_finish(
    cb: CallbackQuery, state: FSMContext, qtype: str, result: ScoreResult, answers: dict[str, Any], user_id: int
) -> None:
    async with session_scope() as s:
        await repo.add_questionnaire(
            s,
            user_id=user_id,
            qtype=qtype,
            answers=answers,
            score=result.score,
            interpretation=result.interpretation,
        )
    await cb.message.edit_text(
        f"{qtype}: {result.score}\n\n{result.label}\n\n{result.explanation}\n\n"
        f"Источник: {result.source}",
    )
    await state.clear()
    await cb.answer("Сохранено")


# ============================================================================
# ISI
# ============================================================================

@router.message(Command("isi"))
async def cmd_isi(message: Message, state: FSMContext, user_id: int, user_tz: str) -> None:
    await state.clear()
    async with session_scope() as s:
        recent = await repo.has_questionnaire_within(s, user_id=user_id, qtype="ISI", days=14)
    if recent:
        await message.answer(
            "ISI уже пройден за последние 14 дней. "
            "Если хотите пройти заново — /isi_force.",
        )
        return
    await state.update_data(answers=[], idx=0)
    await state.set_state(ISIStates.question)
    await _ask_isi(message, state)


@router.message(Command("isi_force"))
async def cmd_isi_force(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(answers=[], idx=0)
    await state.set_state(ISIStates.question)
    await _ask_isi(message, state)


async def _ask_isi(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    idx: int = data["idx"]
    if idx >= len(ISI_QUESTIONS):
        await _finish_isi(target, state)
        return
    await target.answer(
        f"ISI, вопрос {idx + 1}/7:\n{ISI_QUESTIONS[idx]}\n\n"
        "0 — нет, 4 — очень выражено.",
        reply_markup=scale_0_4_kb(f"isi:{idx}"),
    )


@router.callback_query(ISIStates.question, F.data.startswith("isi:"))
async def on_isi_answer(cb: CallbackQuery, state: FSMContext) -> None:
    _, idx_s, val_s = cb.data.split(":")
    idx = int(idx_s)
    val = int(val_s)
    data = await state.get_data()
    answers: list[int] = data["answers"]
    if idx != len(answers):
        await cb.answer("Порядок вопросов нарушен, начните заново: /isi", show_alert=True)
        await state.clear()
        return
    answers.append(val)
    await state.update_data(answers=answers, idx=idx + 1)
    await cb.message.edit_text(
        f"Ответ: {val}. Далее…"
    )
    await cb.answer()
    await _ask_isi(cb.message, state)


async def _finish_isi(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    answers: list[int] = data["answers"]
    result = score_isi(answers)
    await state.update_data(pending={"type": "ISI", "answers": {"items": answers}, "result": result})
    await state.set_state(ISIStates.confirm)
    await target.answer(
        f"ISI: {result.score}/28\n\n{result.label}\n\n{result.explanation}\n\n"
        f"Источник: {result.source}",
        reply_markup=confirm_kb(),
    )


@router.callback_query(ISIStates.confirm, F.data == "q:save")
async def on_isi_save(cb: CallbackQuery, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    pending = data["pending"]
    await _save_and_finish(cb, state, "ISI", pending["result"], pending["answers"], user_id)


# ============================================================================
# ESS
# ============================================================================

@router.message(Command("ess"))
async def cmd_ess(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(answers=[], idx=0)
    await state.set_state(ESSStates.question)
    await _ask_ess(message, state)


async def _ask_ess(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    idx: int = data["idx"]
    if idx >= len(ESS_QUESTIONS):
        await _finish_ess(target, state)
        return
    await target.answer(
        f"ESS, ситуация {idx + 1}/8:\n{ESS_QUESTIONS[idx]}\n\n"
        "0 — не задремлю, 3 — большая вероятность.",
        reply_markup=scale_0_3_kb(f"ess:{idx}"),
    )


@router.callback_query(ESSStates.question, F.data.startswith("ess:"))
async def on_ess_answer(cb: CallbackQuery, state: FSMContext) -> None:
    _, idx_s, val_s = cb.data.split(":")
    idx = int(idx_s)
    val = int(val_s)
    data = await state.get_data()
    answers: list[int] = data["answers"]
    if idx != len(answers):
        await cb.answer("Порядок нарушен, начните заново: /ess", show_alert=True)
        await state.clear()
        return
    answers.append(val)
    await state.update_data(answers=answers, idx=idx + 1)
    await cb.message.edit_text(f"Ответ: {val}. Далее…")
    await cb.answer()
    await _ask_ess(cb.message, state)


async def _finish_ess(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    answers: list[int] = data["answers"]
    result = score_ess(answers)
    await state.update_data(pending={"type": "ESS", "answers": {"items": answers}, "result": result})
    await state.set_state(ESSStates.confirm)
    await target.answer(
        f"ESS: {result.score}/24\n\n{result.label}\n\n{result.explanation}\n\n"
        f"Источник: {result.source}",
        reply_markup=confirm_kb(),
    )


@router.callback_query(ESSStates.confirm, F.data == "q:save")
async def on_ess_save(cb: CallbackQuery, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    pending = data["pending"]
    await _save_and_finish(cb, state, "ESS", pending["result"], pending["answers"], user_id)


# ============================================================================
# STOP-BANG
# ============================================================================

@router.message(Command("stopbang"))
async def cmd_stopbang(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(answers=[], idx=0)
    await state.set_state(StopBangStates.question)
    await _ask_stopbang(message, state)


async def _ask_stopbang(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    idx: int = data["idx"]
    if idx >= len(STOPBANG_QUESTIONS):
        await _finish_stopbang(target, state)
        return
    await target.answer(
        f"STOP-BANG, вопрос {idx + 1}/8:\n{STOPBANG_QUESTIONS[idx]}",
        reply_markup=yes_no_kb(f"sb:{idx}"),
    )


@router.callback_query(StopBangStates.question, F.data.startswith("sb:"))
async def on_sb_answer(cb: CallbackQuery, state: FSMContext) -> None:
    _, idx_s, val_s = cb.data.split(":")
    idx = int(idx_s)
    val = val_s == "yes"
    data = await state.get_data()
    answers: list[bool] = data["answers"]
    if idx != len(answers):
        await cb.answer("Порядок нарушен, начните заново: /stopbang", show_alert=True)
        await state.clear()
        return
    answers.append(val)
    await state.update_data(answers=answers, idx=idx + 1)
    await cb.message.edit_text(f"Ответ: {'да' if val else 'нет'}. Далее…")
    await cb.answer()
    await _ask_stopbang(cb.message, state)


async def _finish_stopbang(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    answers: list[bool] = data["answers"]
    result = score_stopbang(answers)
    await state.update_data(pending={"type": "STOPBANG", "answers": {"items": answers}, "result": result})
    await state.set_state(StopBangStates.confirm)
    await target.answer(
        f"STOP-BANG: {result.score}/8\n\n{result.label}\n\n{result.explanation}\n\n"
        f"Источник: {result.source}",
        reply_markup=confirm_kb(),
    )


@router.callback_query(StopBangStates.confirm, F.data == "q:save")
async def on_sb_save(cb: CallbackQuery, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    pending = data["pending"]
    await _save_and_finish(cb, state, "STOPBANG", pending["result"], pending["answers"], user_id)


# ============================================================================
# PSQI (упрощённый, 5 компонентов)
# ============================================================================

PSQI_STEPS: list[tuple[str, str]] = [
    ("c1_quality", "Как бы вы оценили качество своего сна в целом? (0 — очень хорошее, 3 — очень плохое)"),
    ("c2_latency", "Насколько трудно вам было заснуть? (0 — легко, 3 — очень трудно)"),
    ("c3_duration", "Сколько часов вы спали? (0 — ≥7 ч, 1 — 6–7, 2 — 5–6, 3 — <5)"),
    ("c4_efficiency", "Доля времени сна в постели? (0 — ≥85%, 1 — 75–85%, 2 — 65–75%, 3 — <65%)"),
    ("c5_disturbances", "Как часто вы просыпались ночью? (0 — редко, 3 — очень часто)"),
]


@router.message(Command("psqi"))
async def cmd_psqi(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(answers={}, idx=0)
    await state.set_state(PSQIStates.c1_quality)
    await _ask_psqi(message, state)


async def _ask_psqi(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    idx: int = data["idx"]
    if idx >= len(PSQI_STEPS):
        await _finish_psqi(target, state)
        return
    key, text = PSQI_STEPS[idx]
    await target.answer(
        f"PSQI, вопрос {idx + 1}/5:\n{text}",
        reply_markup=psqi_scale_kb(f"psqi:{idx}"),
    )


@router.callback_query(F.data.startswith("psqi:"))
async def on_psqi_answer(cb: CallbackQuery, state: FSMContext) -> None:
    _, idx_s, val_s = cb.data.split(":")
    idx = int(idx_s)
    val = int(val_s)
    data = await state.get_data()
    answers: dict[str, int] = data["answers"]
    if idx != data["idx"]:
        await cb.answer("Порядок нарушен, начните заново: /psqi", show_alert=True)
        await state.clear()
        return
    key, _ = PSQI_STEPS[idx]
    answers[key] = val
    await state.update_data(answers=answers, idx=idx + 1)
    await cb.message.edit_text(f"Ответ: {val}. Далее…")
    await cb.answer()
    await _ask_psqi(cb.message, state)


async def _finish_psqi(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    answers: dict[str, int] = data["answers"]
    inp = PSQIInput(
        c1_quality=answers["c1_quality"],
        c2_latency=answers["c2_latency"],
        c3_duration=answers["c3_duration"],
        c4_efficiency=answers["c4_efficiency"],
        c5_disturbances=answers["c5_disturbances"],
    )
    result = score_psqi(inp)
    await state.update_data(pending={"type": "PSQI", "answers": answers, "result": result})
    await state.set_state(PSQIStates.confirm)
    await target.answer(
        f"PSQI (упрощ.): {result.score}/21\n\n{result.label}\n\n{result.explanation}\n\n"
        f"Источник: {result.source}",
        reply_markup=confirm_kb(),
    )


@router.callback_query(PSQIStates.confirm, F.data == "q:save")
async def on_psqi_save(cb: CallbackQuery, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    pending = data["pending"]
    await _save_and_finish(cb, state, "PSQI", pending["result"], pending["answers"], user_id)
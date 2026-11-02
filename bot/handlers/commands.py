"""/start /help /about /delete_me + обработка кнопок главного меню."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.database import session_scope
from bot.db import repositories as repo
from bot.keyboards.main_menu import get_main_menu_kb, get_questionnaires_kb

router = Router(name="commands")

START_TEXT = (
    "<b>Добро пожаловать в Дневник Сна</b> 🩺\n\n"
    "Этот бот помогает вести дневник по стандарту <b>Consensus Sleep Diary</b>, "
    "считать клинические метрики (SE, TST, SOL) и находить паттерны.\n\n"
    "⚠️ <b>Важно:</b> бот не ставит диагнозов и не назначает лечение. "
    "Все выводы — это гипотезы для обсуждения с врачом.\n\n"
    "Выберите действие на клавиатуре ниже или используйте меню слева."
)

ABOUT_TEXT = (
    "<b>Методология и источники</b>\n\n"
    "• <b>CSD</b> — Carney et al., Sleep 2012 (PMID 22294820)\n"
    "• <b>ISI</b> — Bastien et al., Sleep Med 2001 (PMID 11438246)\n"
    "• <b>PSQI</b> — Buysse et al., Psychiatry Res 1989 (PMID 2748771), упрощ. версия\n"
    "• <b>ESS</b> — Johns, Sleep 1991 (PMID 1798888)\n"
    "• <b>STOP-BANG</b> — Chung et al., Chest 2016 (PMID 26378880)\n"
    "• <b>Пороги SE/SOL/WASO</b> — Riemann et al., J Sleep Res 2017 (PMID 28875581)\n"
    "• <b>TST 7–9 ч</b> — Watson et al., Sleep 2015 (PMID 26039963)\n"
    "• <b>CBT-I</b> — ACP 2016 (PMID 27136449)\n\n"
    "<i>Это не диагноз. Обсудите результаты с врачом.</i>"
)

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(START_TEXT, reply_markup=get_main_menu_kb())

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(START_TEXT, reply_markup=get_main_menu_kb())

@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    await message.answer(ABOUT_TEXT)

@router.message(Command("delete_me"))
async def cmd_delete_me(message: Message) -> None:
    b = InlineKeyboardBuilder()
    b.button(text="Да, удалить всё", callback_data="delete_me:confirm")
    b.button(text="Отмена", callback_data="delete_me:cancel")
    b.adjust(1)
    await message.answer(
        "Удалить все данные (дневник, опросники, напоминания)? Действие необратимо.",
        reply_markup=b.as_markup(),
    )

@router.callback_query(F.data == "delete_me:confirm")
async def on_delete_confirm(cb: CallbackQuery, user_id: int) -> None:
    async with session_scope() as s:
        await repo.delete_user_data(s, user_id=user_id)
    await cb.message.edit_text("Все данные удалены.")
    await cb.answer()

@router.callback_query(F.data == "delete_me:cancel")
async def on_delete_cancel(cb: CallbackQuery) -> None:
    await cb.message.edit_text("Отменено.")
    await cb.answer()


# ===========================================================================
# Обработчики нижней клавиатуры (Reply-кнопки)
# Прямо вызываем нужные функции из других модулей.
# ===========================================================================

# Импортируем хэндлеры из других файлов, чтобы вызывать их напрямую
from bot.fsm.diary import cmd_diary
from bot.handlers.stats import cmd_stats
from bot.handlers.advice import cmd_advice
from bot.handlers.report import cmd_report
from bot.fsm.questionnaires import cmd_isi, cmd_ess, cmd_stopbang, cmd_psqi

@router.message(F.text == "📝 Дневник")
async def btn_diary(message: Message, state: FSMContext, user_id: int, user_tz: str):
    await cmd_diary(message, state, user_id, user_tz)

@router.message(F.text == "📊 Статистика")
async def btn_stats(message: Message, user_id: int, user_tz: str):
    # У CommandObject есть атрибут args. Для кнопки мы его эмулируем (None)
    class DummyCommand:
        args = None
    await cmd_stats(message, DummyCommand(), user_id, user_tz)

@router.message(F.text == "💡 Рекомендации")
async def btn_advice(message: Message, user_id: int, user_tz: str):
    await cmd_advice(message, user_id, user_tz)

@router.message(F.text == "📋 Отчёт врачу")
async def btn_report(message: Message, user_id: int, user_tz: str):
    class DummyCommand:
        args = None
    await cmd_report(message, DummyCommand(), user_id, user_tz)

@router.message(F.text == "ℹ️ О боте")
async def btn_about(message: Message):
    await cmd_about(message)

@router.message(F.text == "📑 Опросники")
async def btn_questionnaires(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите опросник:", reply_markup=get_questionnaires_kb())

@router.message(F.text == "⬅️ Назад в меню")
async def btn_back_to_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu_kb())


# ===========================================================================
# Обработчики кнопок внутри раздела "Опросники"
# ===========================================================================

@router.message(F.text == "ISI (Инсомния)")
async def btn_isi(message: Message, state: FSMContext, user_id: int, user_tz: str):
    await cmd_isi(message, state, user_id, user_tz)

@router.message(F.text == "ESS (Сонливость)")
async def btn_ess(message: Message, state: FSMContext):
    await cmd_ess(message, state)

@router.message(F.text == "STOP-BANG (Апноэ)")
async def btn_stopbang(message: Message, state: FSMContext):
    await cmd_stopbang(message, state)

@router.message(F.text == "PSQI (Качество)")
async def btn_psqi(message: Message, state: FSMContext):
    await cmd_psqi(message, state)
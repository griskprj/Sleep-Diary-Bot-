"""Инлайн-клавиатуры для /diary."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import SOL_ELEVATED_MIN, WASO_ELEVATED_MIN


def skip_cancel_kb() -> InlineKeyboardMarkup:
    """Кнопки «Пропустить» (где допустимо) и «Отмена»."""
    b = InlineKeyboardBuilder()
    b.button(text="Пропустить", callback_data="diary:skip")
    b.button(text="Отмена", callback_data="diary:cancel")
    b.adjust(2)
    return b.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Отмена", callback_data="diary:cancel")
    return b.as_markup()


def sol_kb() -> InlineKeyboardMarkup:
    """Быстрые пресеты для SOL + «ввести вручную»."""
    b = InlineKeyboardBuilder()
    for v in (0, 10, 20, 30, 45, 60, 90, 120):
        label = f"{v} мин" + (" ⚠" if v > SOL_ELEVATED_MIN else "")
        b.button(text=label, callback_data=f"diary:sol:{v}")
    b.button(text="Ввести вручную", callback_data="diary:sol:manual")
    b.button(text="Отмена", callback_data="diary:cancel")
    b.adjust(4, 4, 1, 1)
    return b.as_markup()


def waso_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for v in (0, 10, 20, 30, 45, 60, 90, 120):
        label = f"{v} мин" + (" ⚠" if v > WASO_ELEVATED_MIN else "")
        b.button(text=label, callback_data=f"diary:waso:{v}")
    b.button(text="Ввести вручную", callback_data="diary:waso:manual")
    b.button(text="Отмена", callback_data="diary:cancel")
    b.adjust(4, 4, 1, 1)
    return b.as_markup()


def scale_1_5_kb(prefix: str) -> InlineKeyboardMarkup:
    """Шкала 1–5 (качество сна, стресс)."""
    b = InlineKeyboardBuilder()
    for v in range(1, 6):
        b.button(text=str(v), callback_data=f"{prefix}:{v}")
    b.button(text="Отмена", callback_data="diary:cancel")
    b.adjust(5, 1)
    return b.as_markup()


def yes_no_kb(prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Да", callback_data=f"{prefix}:yes")
    b.button(text="Нет", callback_data=f"{prefix}:no")
    b.button(text="Отмена", callback_data="diary:cancel")
    b.adjust(2, 1)
    return b.as_markup()


def activity_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Нет", callback_data="diary:activity:0")
    b.button(text="Умеренная", callback_data="diary:activity:1")
    b.button(text="Интенсивная", callback_data="diary:activity:2")
    b.button(text="Отмена", callback_data="diary:cancel")
    b.adjust(3, 1)
    return b.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Сохранить", callback_data="diary:save")
    b.button(text="Отмена", callback_data="diary:cancel")
    b.adjust(2)
    return b.as_markup()
"""Инлайн-клавиатуры для опросников."""
from __future__ import annotations

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def scale_0_4_kb(prefix: str) -> InlineKeyboardMarkup:
    """Шкала 0–4 (ISI)."""
    b = InlineKeyboardBuilder()
    for v in range(5):
        b.button(text=str(v), callback_data=f"{prefix}:{v}")
    b.button(text="Отмена", callback_data="q:cancel")
    b.adjust(5, 1)
    return b.as_markup()


def scale_0_3_kb(prefix: str) -> InlineKeyboardMarkup:
    """Шкала 0–3 (ESS)."""
    b = InlineKeyboardBuilder()
    for v in range(4):
        b.button(text=str(v), callback_data=f"{prefix}:{v}")
    b.button(text="Отмена", callback_data="q:cancel")
    b.adjust(4, 1)
    return b.as_markup()


def yes_no_kb(prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Да", callback_data=f"{prefix}:yes")
    b.button(text="Нет", callback_data=f"{prefix}:no")
    b.button(text="Отмена", callback_data="q:cancel")
    b.adjust(2, 1)
    return b.as_markup()


def psqi_scale_kb(prefix: str) -> InlineKeyboardMarkup:
    """PSQI: каждый компонент 0–3."""
    b = InlineKeyboardBuilder()
    for v in range(4):
        b.button(text=str(v), callback_data=f"{prefix}:{v}")
    b.button(text="Отмена", callback_data="q:cancel")
    b.adjust(4, 1)
    return b.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Сохранить", callback_data="q:save")
    b.button(text="Отмена", callback_data="q:cancel")
    b.adjust(2)
    return b.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Отмена", callback_data="q:cancel")
    return b.as_markup()
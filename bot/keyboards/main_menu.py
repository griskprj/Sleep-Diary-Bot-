"""Главное меню (Reply-клавиатура)."""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu_kb() -> ReplyKeyboardMarkup:
    """Нижняя клавиатура с основными действиями."""
    kb = [
        [
            KeyboardButton(text="📝 Дневник"),
            KeyboardButton(text="📊 Статистика"),
        ],
        [
            KeyboardButton(text="💡 Рекомендации"),
            KeyboardButton(text="📋 Отчёт врачу"),
        ],
        [
            KeyboardButton(text="📑 Опросники"),
            KeyboardButton(text="ℹ️ О боте"),
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или введите команду..."
    )

def get_questionnaires_kb() -> ReplyKeyboardMarkup:
    """Клавиатура для раздела опросников."""
    kb = [
        [
            KeyboardButton(text="ISI (Инсомния)"),
            KeyboardButton(text="ESS (Сонливость)"),
        ],
        [
            KeyboardButton(text="STOP-BANG (Апноэ)"),
            KeyboardButton(text="PSQI (Качество)"),
        ],
        [
            KeyboardButton(text="⬅️ Назад в меню"),
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
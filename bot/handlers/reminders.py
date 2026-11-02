"""/remind HH:MM — ежедневное напоминание об /diary."""
from __future__ import annotations

import re
from datetime import time as dt_time

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.services.scheduler import add_daily_reminder, remove_user_reminders

router = Router(name="reminders")

_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


@router.message(Command("remind"))
async def cmd_remind(
    message: Message,
    command: CommandObject,
    user_id: int,
    user_tz: str,
) -> None:
    args = (command.args or "").strip().lower()

    if args in {"off", "stop", "none"}:
        await remove_user_reminders(user_id)
        await message.answer("Напоминание отключено.")
        return

    if not args:
        await message.answer(
            "Использование:\n"
            "  /remind 08:30 — ежедневное напоминание в 08:30 (по вашему TZ)\n"
            "  /remind off — отключить",
        )
        return

    m = _HHMM_RE.match(args)
    if not m:
        await message.answer("Формат: HH:MM (00:00–23:59). Например: /remind 08:30")
        return

    t = dt_time(hour=int(m.group(1)), minute=int(m.group(2)))
    await add_daily_reminder(
        bot=message.bot, user_id=user_id, tg_id=message.from_user.id, tz_name=user_tz, t=t
    )
    await message.answer(
        f"Напоминание установлено: ежедневно в {t.strftime('%H:%M')} ({user_tz}).\n"
        "Отключить: /remind off"
    )
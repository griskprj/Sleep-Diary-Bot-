"""/export — выгрузка CSV дневника + CSV опросников."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy import select

from bot.db.database import session_scope
from bot.db import repositories as repo
from bot.db.models import Questionnaire
from bot.utils.csv_export import entries_to_csv, questionnaires_to_csv
from bot.utils.tz import today_local

router = Router(name="export")


@router.message(Command("export"))
async def cmd_export(message: Message, user_id: int, user_tz: str) -> None:
    async with session_scope() as s:
        entries = await repo.get_sleep_entries(s, user_id=user_id)
        qs = (
            await s.execute(
                select(Questionnaire)
                .where(Questionnaire.user_id == user_id)
                .order_by(Questionnaire.created_at.asc())
            )
        ).scalars().all()

    if not entries and not qs:
        await message.answer("Нет данных для выгрузки. Начните с /diary.")
        return

    today = today_local(user_tz).isoformat()
    if entries:
        await message.answer_document(
            BufferedInputFile(entries_to_csv(entries), filename=f"sleep_entries_{today}.csv"),
            caption=f"Дневник: {len(entries)} ночей.",
        )
    if qs:
        await message.answer_document(
            BufferedInputFile(questionnaires_to_csv(qs), filename=f"questionnaires_{today}.csv"),
            caption=f"Опросники: {len(qs)} записей.",
        )
    await message.answer(
        "Заметки (свободный текст) не выгружаются в CSV — из соображений "
        "приватности. Если нужны — обсудите с врачом напрямую."
    )
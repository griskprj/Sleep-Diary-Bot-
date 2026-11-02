"""/report — текстовый отчёт для врача + CSV-вложение."""
from __future__ import annotations

from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from bot.config import settings
from bot.db.database import session_scope
from bot.db import repositories as repo
from bot.services.analysis import analyze
from bot.services.metrics import aggregate
from bot.services.report import build_doctor_report, format_factors_summary
from bot.utils.csv_export import entries_to_csv
from bot.utils.orm_mapping import questionnaire_to_score_result
from bot.utils.period import entries_to_dated, entries_to_factors, metrics_only
from bot.utils.tz import today_local

router = Router(name="report")


@router.message(Command("report"))
async def cmd_report(
    message: Message,
    command: CommandObject,
    user_id: int,
    user_tz: str,
) -> None:
    days = _parse_days(command.args, settings.report_days_default)
    if days is None:
        await message.answer("Использование: /report [N], N — 7–90 дней. Например: /report 14")
        return

    today = today_local(user_tz)
    since = today - timedelta(days=days - 1)

    async with session_scope() as s:
        rows = await repo.get_sleep_entries(s, user_id=user_id, since=since, until=today)
        questionnaires = {
            "ISI": await repo.get_latest_questionnaire(s, user_id=user_id, qtype="ISI"),
            "PSQI": await repo.get_latest_questionnaire(s, user_id=user_id, qtype="PSQI"),
            "ESS": await repo.get_latest_questionnaire(s, user_id=user_id, qtype="ESS"),
            "STOPBANG": await repo.get_latest_questionnaire(s, user_id=user_id, qtype="STOPBANG"),
        }

    dated = entries_to_dated(rows)
    factors = entries_to_factors(rows) if rows else None
    stats = aggregate(metrics_only(dated))

    analysis = analyze(
        entries=dated, factors=factors,
        isi=questionnaire_to_score_result(questionnaires["ISI"]),
        psqi=questionnaire_to_score_result(questionnaires["PSQI"]),
        ess=questionnaire_to_score_result(questionnaires["ESS"]),
        stopbang=questionnaire_to_score_result(questionnaires["STOPBANG"]),
        today=today,
    )

    report_text = build_doctor_report(
        rows=rows,
        stats=stats,
        metrics_list=metrics_only(dated),
        analysis=analysis,
        questionnaires=questionnaires,
        days=days,
        today=today,
        factors_summary=format_factors_summary(rows) if rows else None,
    )

    # Telegram лимит 4096 — разбиваем, если нужно
    for chunk in _split_message(report_text, 4000):
        await message.answer(chunk)

    if rows:
        csv_bytes = entries_to_csv(rows)
        await message.answer_document(
            BufferedInputFile(csv_bytes, filename=f"sleep_diary_{today.isoformat()}.csv"),
            caption="CSV с метриками — для врача.",
        )
    else:
        await message.answer(
            "Нет данных за период. Заполните /diary хотя бы несколько ночей, "
            "чтобы отчёт был информативным."
        )


def _parse_days(args: str | None, default: int) -> int | None:
    if not args:
        return default
    try:
        n = int(args.strip())
    except ValueError:
        return None
    if not 7 <= n <= 90:
        return None
    return n


def _split_message(text: str, limit: int) -> list[str]:
    """Разбивает по абзацам, не разрывая теги (грубо, но для наших текстов ок)."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for line in text.split("\n"):
        if cur_len + len(line) + 1 > limit and cur:
            chunks.append("\n".join(cur))
            cur, cur_len = [], 0
        cur.append(line)
        cur_len += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks
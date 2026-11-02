"""/advice — персональные рекомендации по CBT-I и гигиене сна."""
from __future__ import annotations

from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.db.database import session_scope
from bot.db import repositories as repo
from bot.services.analysis import analyze
from bot.services.metrics import aggregate
from bot.services.presentation import format_advice
from bot.services.recommendations import build_advice
from bot.utils.period import entries_to_dated, entries_to_factors, metrics_only
from bot.utils.tz import today_local

router = Router(name="advice")


@router.message(Command("advice"))
async def cmd_advice(message: Message, user_id: int, user_tz: str) -> None:
    today = today_local(user_tz)
    days = settings.report_days_default  # 14 по умолчанию
    since = today - timedelta(days=days - 1)

    async with session_scope() as s:
        rows = await repo.get_sleep_entries(s, user_id=user_id, since=since, until=today)
        isi_row = await repo.get_latest_questionnaire(s, user_id=user_id, qtype="ISI")
        psqi_row = await repo.get_latest_questionnaire(s, user_id=user_id, qtype="PSQI")
        ess_row = await repo.get_latest_questionnaire(s, user_id=user_id, qtype="ESS")
        sb_row = await repo.get_latest_questionnaire(s, user_id=user_id, qtype="STOPBANG")

    if not rows and isi_row is None and psqi_row is None and ess_row is None and sb_row is None:
        await message.answer(
            "Пока нет данных для персональных рекомендаций.\n\n"
            "Заполните /diary хотя бы 3 ночи и пройдите /isi — тогда /advice "
            "будет привязан к вашим метрикам, а не общим.",
        )
        return

    dated = entries_to_dated(rows)
    factors = entries_to_factors(rows) if rows else None
    stats = aggregate(metrics_only(dated))

    isi = _to_score_result(isi_row)
    psqi = _to_score_result(psqi_row)
    ess = _to_score_result(ess_row)
    sb = _to_score_result(sb_row)

    analysis = analyze(
        entries=dated,
        factors=factors,
        isi=isi,
        psqi=psqi,
        ess=ess,
        stopbang=sb,
        today=today,
    )

    advice = build_advice(
        analysis=analysis,
        stats=stats,
        factors=factors,
        isi=isi,
        psqi=psqi,
        ess=ess,
        stopbang=sb,
    )

    await message.answer(format_advice(advice))

from bot.handlers.stats import _to_score_result  # noqa: E402
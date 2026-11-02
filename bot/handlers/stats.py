"""/stats [N] — сводная статистика за N дней (по умолчанию 14)."""
from __future__ import annotations

from datetime import timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import settings
from bot.db.database import session_scope
from bot.db import repositories as repo
from bot.services.analysis import analyze
from bot.services.metrics import aggregate
from bot.services.presentation import (
    format_hypotheses,
    format_period_stats,
    format_questionnaire_snapshot,
)
from bot.utils.period import entries_to_dated, entries_to_factors, metrics_only
from bot.utils.tz import today_local

router = Router(name="stats")


@router.message(Command("stats"))
async def cmd_stats(
    message: Message,
    command: CommandObject,
    user_id: int,
    user_tz: str,
) -> None:
    days = _parse_days(command.args)
    if days is None:
        await message.answer(
            "Использование: /stats [N], где N — число дней (1–365).\n"
            "Например: /stats 14",
        )
        return

    today = today_local(user_tz)
    since = today - timedelta(days=days - 1)

    async with session_scope() as s:
        rows = await repo.get_sleep_entries(s, user_id=user_id, since=since, until=today)
        isi = await repo.get_latest_questionnaire(s, user_id=user_id, qtype="ISI")
        psqi = await repo.get_latest_questionnaire(s, user_id=user_id, qtype="PSQI")
        ess = await repo.get_latest_questionnaire(s, user_id=user_id, qtype="ESS")
        stopbang = await repo.get_latest_questionnaire(s, user_id=user_id, qtype="STOPBANG")

    dated = entries_to_dated(rows)
    factors = entries_to_factors(rows) if rows else None
    stats = aggregate(metrics_only(dated))

    analysis = analyze(
        entries=dated,
        factors=factors,
        isi=_to_score_result(isi),
        psqi=_to_score_result(psqi),
        ess=_to_score_result(ess),
        stopbang=_to_score_result(stopbang),
        today=today,
    )

    # 1. Сводка метрик
    await message.answer(format_period_stats(stats, days=days, today=today, metrics_list=metrics_only(dated)))

    # 2. Опросники
    snap = format_questionnaire_snapshot(
        _to_score_result(isi),
        _to_score_result(psqi),
        _to_score_result(ess),
        _to_score_result(stopbang),
    )
    if snap:
        await message.answer(snap)

    # 3. Гипотезы
    await message.answer(format_hypotheses(analysis))


def _parse_days(args: str | None) -> int | None:
    if not args:
        return settings.report_days_default
    try:
        n = int(args.strip())
    except ValueError:
        return None
    if not 1 <= n <= 365:
        return None
    return n


def _to_score_result(row) -> ScoreResult | None:
    """ORM Questionnaire → ScoreResult. None, если записи нет."""
    if row is None:
        return None
    from bot.services.questionnaires import ScoreResult
    return ScoreResult(
        score=row.score,
        interpretation=row.interpretation,
        label=_label_for(row.type, row.interpretation),
        explanation="",
        flags=(),
        source="",
    )


_LABELS = {
    "ISI": {
        "none": "нет клинически значимой инсомнии",
        "subclinical": "субклиническая инсомния",
        "moderate": "клиническая инсомния (умеренная)",
        "severe": "тяжёлая клиническая инсомния",
    },
    "PSQI": {
        "good": "хорошее качество сна",
        "poor": "плохое качество сна",
    },
    "ESS": {
        "normal": "норма",
        "borderline": "пограничная сонливость",
        "excessive": "избыточная сонливость",
    },
    "STOPBANG": {
        "low": "низкий риск ОАС",
        "intermediate": "промежуточный риск ОАС",
        "high": "высокий риск ОАС",
    },
}


def _label_for(qtype: str, interpretation: str) -> str:
    return _LABELS.get(qtype, {}).get(interpretation, interpretation)
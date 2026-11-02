"""
Планировщик (apscheduler): ежедневные напоминания + недельный дайджест.

Жизненный цикл:
- start_scheduler(bot) при старте бота; init_db + восстановление jobs из БД.
- add_daily_reminder(user_id, tg_id, tz, time) — /remind.
- remove_user_reminders(user_id) — при /remind off или /delete_me.
- shutdown_scheduler() при остановке.
"""
from __future__ import annotations

import logging
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import settings
from bot.db.database import session_scope
from bot.db import repositories as repo

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def start_scheduler(bot: Bot) -> None:
    """Запускает планировщик и восстанавливает активные напоминания из БД."""
    sched = get_scheduler()
    if sched.running:
        return
    sched.start()

    async with session_scope() as s:
        reminders = await repo.get_active_reminders(s)

    for r in reminders:
        # Нужен tg_id и tz — подгружаем через user
        async with session_scope() as s:
            user = await s.get(__import__("bot.db.models", fromlist=["User"]).User, r.user_id)
        if user is None:
            continue
        _schedule_daily(bot, user.id, user.tg_id, user.tz, r.time)
    logger.info("Scheduler started; restored %d reminders", len(reminders))

    # Недельный дайджест — одна job на всех (рассылка по всем user)
    sched.add_job(
        _weekly_digest_job,
        CronTrigger(
            day_of_week=settings.weekly_digest_weekday,
            hour=settings.weekly_digest_hour,
            minute=0,
        ),
        args=[bot],
        id="weekly_digest",
        replace_existing=True,
    )


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def _schedule_daily(bot: Bot, user_id: int, tg_id: int, tz_name: str, t: dt_time) -> None:
    """Регистрирует ежедневную job для одного пользователя."""
    job_id = f"remind:{user_id}"
    tz = ZoneInfo(tz_name)
    get_scheduler().add_job(
        _send_daily_reminder,
        CronTrigger(hour=t.hour, minute=t.minute, timezone=tz),
        args=[bot, tg_id],
        id=job_id,
        replace_existing=True,
    )


async def _send_daily_reminder(bot: Bot, tg_id: int) -> None:
    try:
        await bot.send_message(
            tg_id,
            "Напоминание: заполните /diary (дневник сна).\n"
            "Это займёт ~1 минуту и нужно для динамики.",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to send reminder to %s: %s", tg_id, e)


async def add_daily_reminder(
    bot: Bot, *, user_id: int, tg_id: int, tz_name: str, t: dt_time
) -> None:
    """Устанавливает напоминание (или перезаписывает)."""
    _schedule_daily(bot, user_id, tg_id, tz_name, t)
    async with session_scope() as s:
        await repo.upsert_reminder(s, user_id=user_id, reminder_time=t, job_id=f"remind:{user_id}")


async def remove_user_reminders(user_id: int) -> None:
    job_id = f"remind:{user_id}"
    sched = get_scheduler()
    if sched.get_job(job_id):
        sched.remove_job(job_id)
    async with session_scope() as s:
        await repo.deactivate_reminders(s, user_id=user_id)


# ---------------------------------------------------------------------------
# Недельный дайджест
# ---------------------------------------------------------------------------

async def _weekly_digest_job(bot: Bot) -> None:
    """
    Раз в неделю — краткий дайджест по каждому пользователю с данными.

    Что показываем: изменение SE/TST за неделю vs предыдущая, какие
    гипотезы подтверждаются/снимаются, что улучшилось/ухудшилось.
    """
    from datetime import timedelta
    from bot.services.analysis import analyze
    from bot.services.metrics import aggregate
    from bot.services.presentation import format_hypotheses
    from bot.utils.period import entries_to_dated, entries_to_factors, metrics_only
    from bot.utils.tz import today_local

    async with session_scope() as s:
        # Все пользователи с записями
        from sqlalchemy import select
        from bot.db.models import User
        users = (await s.execute(select(User))).scalars().all()

    for user in users:
        try:
            today = today_local(user.tz)
            since = today - timedelta(days=6)
            prev_since = since - timedelta(days=7)

            async with session_scope() as s:
                this_week = await repo.get_sleep_entries(
                    s, user_id=user.id, since=since, until=today
                )
                prev_week = await repo.get_sleep_entries(
                    s, user_id=user.id, since=prev_since, until=since - timedelta(days=1)
                )
                isi_row = await repo.get_latest_questionnaire(s, user_id=user.id, qtype="ISI")
                ess_row = await repo.get_latest_questionnaire(s, user_id=user.id, qtype="ESS")
                sb_row = await repo.get_latest_questionnaire(s, user_id=user.id, qtype="STOPBANG")

            if not this_week:
                continue

            dated = entries_to_dated(this_week)
            factors = entries_to_factors(this_week)
            stats = aggregate(metrics_only(dated))

            from bot.utils.orm_mapping import questionnaire_to_score_result
            analysis = analyze(
                entries=dated, factors=factors,
                isi=questionnaire_to_score_result(isi_row),
                ess=questionnaire_to_score_result(ess_row),
                stopbang=questionnaire_to_score_result(sb_row),
                today=today,
            )

            prev_stats = None
            if prev_week:
                prev_stats = aggregate(metrics_only(entries_to_dated(prev_week)))

            text = _format_digest(stats, prev_stats, analysis)
            await bot.send_message(user.tg_id, text)
        except Exception as e:  # noqa: BLE001
            logger.warning("Weekly digest failed for user %s: %s", user.id, e)


def _format_digest(stats, prev_stats, analysis) -> str:
    from bot.services.presentation import format_hypotheses

    lines = ["<b>Недельный дайджест</b>", ""]
    if stats.n_nights == 0:
        return "На этой неделе нет записей. Попробуйте /diary — даже 3 ночи дадут картину."

    lines.append(f"Ночей: {stats.n_nights} · SE {stats.avg_se_percent:.1f}% · TST {stats.avg_tst_min/60:.1f} ч")

    if prev_stats and prev_stats.n_nights > 0:
        d_se = stats.avg_se_percent - prev_stats.avg_se_percent
        d_tst = (stats.avg_tst_min - prev_stats.avg_tst_min) / 60
        arrow = lambda x: "↑" if x > 0.3 else ("↓" if x < -0.3 else "→")
        lines.append(f"vs прошлая неделя: SE {arrow(d_se)} {d_se:+.1f}%, TST {arrow(d_tst)} {d_tst:+.1f} ч")
    lines.append("")

    if analysis.hypotheses:
        lines.append("Активные гипотезы:")
        for h in analysis.hypotheses[:3]:
            lines.append(f"• {h.title}")
    else:
        lines.append("Значимых гипотез нет.")

    lines.append("")
    lines.append("Подробнее: /stats 14 · /advice")
    return "\n".join(lines)
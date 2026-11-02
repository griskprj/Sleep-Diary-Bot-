"""
Репозитории — слой доступа к данным.

Все функции async, принимают AsyncSession. Хэндлеры не работают с ORM напрямую.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Questionnaire, Reminder, SleepEntry, User


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def get_or_create_user(
    session: AsyncSession, tg_id: int, tz: str
) -> User:
    stmt = select(User).where(User.tg_id == tg_id)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        user = User(tg_id=tg_id, tz=tz)
        session.add(user)
        await session.flush()
    return user


async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    stmt = select(User).where(User.tg_id == tg_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_user_reminder_time(
    session: AsyncSession, user_id: int, reminder_time: time | None
) -> None:
    user = await session.get(User, user_id)
    if user is not None:
        user.reminder_time = reminder_time


async def delete_user_data(session: AsyncSession, user_id: int) -> None:
    """
    Полное удаление всех данных пользователя (каскадно через ORM/ondelete).
    Удаляем запись пользователя — sleep_entries/questionnaires/reminders
    удалятся каскадно.
    """
    await session.execute(delete(User).where(User.id == user_id))


# ---------------------------------------------------------------------------
# Sleep entries
# ---------------------------------------------------------------------------

async def add_sleep_entry(
    session: AsyncSession, user_id: int, payload: dict[str, Any]
) -> SleepEntry:
    entry = SleepEntry(user_id=user_id, **payload)
    session.add(entry)
    await session.flush()
    return entry


async def get_sleep_entries(
    session: AsyncSession,
    user_id: int,
    *,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
) -> Sequence[SleepEntry]:
    stmt = select(SleepEntry).where(SleepEntry.user_id == user_id)
    if since is not None:
        stmt = stmt.where(SleepEntry.entry_date >= since)
    if until is not None:
        stmt = stmt.where(SleepEntry.entry_date <= until)
    stmt = stmt.order_by(SleepEntry.entry_date.asc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await session.execute(stmt)).scalars().all()


async def get_last_n_entries(
    session: AsyncSession, user_id: int, n: int
) -> list[SleepEntry]:
    stmt = (
        select(SleepEntry)
        .where(SleepEntry.user_id == user_id)
        .order_by(SleepEntry.entry_date.desc())
        .limit(n)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(reversed(rows))


async def get_entry_by_date(
    session: AsyncSession, user_id: int, entry_date: date
) -> SleepEntry | None:
    stmt = select(SleepEntry).where(
        SleepEntry.user_id == user_id, SleepEntry.entry_date == entry_date
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Questionnaires
# ---------------------------------------------------------------------------

async def add_questionnaire(
    session: AsyncSession,
    user_id: int,
    qtype: str,
    answers: dict[str, Any],
    score: int,
    interpretation: str,
) -> Questionnaire:
    q = Questionnaire(
        user_id=user_id,
        type=qtype,
        answers_json=answers,
        score=score,
        interpretation=interpretation,
    )
    session.add(q)
    await session.flush()
    return q


async def get_latest_questionnaire(
    session: AsyncSession, user_id: int, qtype: str
) -> Questionnaire | None:
    stmt = (
        select(Questionnaire)
        .where(Questionnaire.user_id == user_id, Questionnaire.type == qtype)
        .order_by(Questionnaire.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_questionnaires_since(
    session: AsyncSession, user_id: int, qtype: str, since: datetime
) -> Sequence[Questionnaire]:
    stmt = (
        select(Questionnaire)
        .where(
            Questionnaire.user_id == user_id,
            Questionnaire.type == qtype,
            Questionnaire.created_at >= since,
        )
        .order_by(Questionnaire.created_at.asc())
    )
    return (await session.execute(stmt)).scalars().all()


async def has_questionnaire_within(
    session: AsyncSession, user_id: int, qtype: str, days: int
) -> bool:
    """True, если опросник проходился за последние `days` дней."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(Questionnaire.id)
        .where(
            Questionnaire.user_id == user_id,
            Questionnaire.type == qtype,
            Questionnaire.created_at >= cutoff,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

async def upsert_reminder(
    session: AsyncSession, user_id: int, reminder_time: time, job_id: str
) -> Reminder:
    stmt = select(Reminder).where(Reminder.user_id == user_id)
    reminder = (await session.execute(stmt)).scalar_one_or_none()
    if reminder is None:
        reminder = Reminder(user_id=user_id, time=reminder_time, active=True, job_id=job_id)
        session.add(reminder)
    else:
        reminder.time = reminder_time
        reminder.active = True
        reminder.job_id = job_id
    await session.flush()
    return reminder


async def deactivate_reminders(session: AsyncSession, user_id: int) -> list[Reminder]:
    stmt = select(Reminder).where(Reminder.user_id == user_id, Reminder.active.is_(True))
    reminders = list((await session.execute(stmt)).scalars().all())
    for r in reminders:
        r.active = False
    return reminders


async def get_active_reminders(session: AsyncSession) -> Sequence[Reminder]:
    stmt = select(Reminder).where(Reminder.active.is_(True))
    return (await session.execute(stmt)).scalars().all()
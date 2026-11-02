"""
SQLAlchemy ORM-модели.

Схема:
- users            — пользователи, tz, время напоминания
- sleep_entries    — записи CSD + факторы
- questionnaires   — результаты ISI/PSQI/ESS/STOP-BANG (история)
- reminders        — активные напоминания (apscheduler job_id для синхронизации)
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    tz: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)
    reminder_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sleep_entries: Mapped[list["SleepEntry"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    questionnaires: Mapped[list["Questionnaire"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SleepEntry(Base):
    """
    Запись Consensus Sleep Diary (CSD) + факторы.

    Времена хранятся как строки 'HH:MM' — так проще валидировать и
    отображать; расчёт метрик выполняет services/metrics.py.
    """
    __tablename__ = "sleep_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "entry_date", name="uq_sleep_entry_user_date"),
        Index("ix_sleep_entries_user_date", "user_id", "entry_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # Дата, к которой относится ночь (дата подъёма)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)

    # CSD-поля
    lights_out: Mapped[str] = mapped_column(String(5), nullable=False)     # HH:MM
    try_sleep: Mapped[str] = mapped_column(String(5), nullable=False)      # HH:MM
    final_wake: Mapped[str] = mapped_column(String(5), nullable=False)     # HH:MM
    sol_min: Mapped[int] = mapped_column(Integer, nullable=False)          # минуты
    waso_min: Mapped[int] = mapped_column(Integer, nullable=False)         # суммарно минут
    awakenings_count: Mapped[int] = mapped_column(Integer, default=0)
    quality: Mapped[int] = mapped_column(Integer, nullable=False)          # 1–5
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Вычисляемые метрики (кэш; пересчитываются при сохранении)
    tib_min: Mapped[int] = mapped_column(Integer, nullable=False)
    tst_min: Mapped[int] = mapped_column(Integer, nullable=False)
    se_percent: Mapped[float] = mapped_column(Float, nullable=False)

    # Факторы (0/1/2 или bool)
    caffeine_after_16: Mapped[bool] = mapped_column(Boolean, default=False)
    alcohol_evening: Mapped[bool] = mapped_column(Boolean, default=False)
    screen_before_bed: Mapped[bool] = mapped_column(Boolean, default=False)
    activity_level: Mapped[int] = mapped_column(Integer, default=1)  # 0/1/2
    stress_level: Mapped[int] = mapped_column(Integer, default=3)    # 1–5

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="sleep_entries")


class Questionnaire(Base):
    """Результат любого скринингового опросника."""
    __tablename__ = "questionnaires"
    __table_args__ = (
        Index("ix_questionnaires_user_type_date", "user_id", "type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # ISI/PSQI/ESS/STOPBANG
    answers_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    interpretation: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="questionnaires")


class Reminder(Base):
    """Активное ежедневное напоминание."""
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    time: Mapped[time] = mapped_column(Time, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="reminders")
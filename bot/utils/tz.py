"""
Конвертация времени: UTC ↔ локальное (IANA).

В БД `created_at` — UTC (server_default=now). Для пользователя — его tz.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def now_local(tz_name: str) -> datetime:
    """Текущее время в tz пользователя."""
    return datetime.now(ZoneInfo(tz_name))


def today_local(tz_name: str) -> date:
    """Сегодняшняя дата в tz пользователя (для entry_date)."""
    return now_local(tz_name).date()


def to_local(dt_utc: datetime, tz_name: str) -> datetime:
    """UTC → локальное. Если dt naive — считаем UTC."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
    return dt_utc.astimezone(ZoneInfo(tz_name))
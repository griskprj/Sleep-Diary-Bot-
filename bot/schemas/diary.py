"""
Pydantic-модели для CSD-записи.

Валидируют пользовательский ввод ДО записи в БД. Метрики здесь НЕ считаются —
это делает services/metrics.py, чтобы формулы были покрыты отдельными тестами.
"""
from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field, field_validator

from bot.constants import SOL_ELEVATED_MIN, WASO_ELEVATED_MIN

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class CSDEntryInput(BaseModel):
    """Полный ввод пользователя по Consensus Sleep Diary."""

    entry_date: date
    lights_out: str = Field(..., description="Время лечь в постель, HH:MM")
    try_sleep: str = Field(..., description="Время попытки заснуть, HH:MM")
    final_wake: str = Field(..., description="Время окончательного подъёма, HH:MM")

    sol_min: int = Field(..., ge=0, le=600, description="Минуты до засыпания")
    waso_min: int = Field(..., ge=0, le=600, description="Суммарные минуты бодрствования ночью")
    awakenings_count: int = Field(default=0, ge=0, le=50)
    quality: int = Field(..., ge=1, le=5, description="Субъективное качество 1–5")
    notes: str | None = Field(default=None, max_length=2000)

    caffeine_after_16: bool = False
    alcohol_evening: bool = False
    screen_before_bed: bool = False
    activity_level: int = Field(default=1, ge=0, le=2)
    stress_level: int = Field(default=3, ge=1, le=5)

    @field_validator("lights_out", "try_sleep", "final_wake")
    @classmethod
    def _check_hhmm(cls, v: str) -> str:
        if not _HHMM_RE.match(v):
            raise ValueError("Время должно быть в формате HH:MM (00:00–23:59)")
        return v

    @field_validator("waso_min")
    @classmethod
    def _waso_warn(cls, v: int) -> int:
        # Не ошибка — просто фиксируем, что значение клинически значимо.
        return v

    def sanity_notes(self) -> list[str]:
        """Мягкие предупреждения (не ошибки) для показа пользователю."""
        warnings: list[str] = []
        if self.sol_min > SOL_ELEVATED_MIN:
            warnings.append(f"SOL {self.sol_min} мин > {SOL_ELEVATED_MIN} мин — удлинённая латентность.")
        if self.waso_min > WASO_ELEVATED_MIN:
            warnings.append(f"WASO {self.waso_min} мин > {WASO_ELEVATED_MIN} мин — значимые пробуждения.")
        return warnings
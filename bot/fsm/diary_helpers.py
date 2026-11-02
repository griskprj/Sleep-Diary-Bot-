"""Хелперы для /diary: парсинг, валидация, форматирование сводки."""
from __future__ import annotations

import re

from bot.schemas.diary import CSDEntryInput
from bot.services.metrics import SleepMetrics

_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_time_hhmm(value: str) -> str:
    """Возвращает нормализованный 'HH:MM' или ValueError."""
    v = value.strip()
    if not _HHMM_RE.match(v):
        raise ValueError("Формат времени: HH:MM (00:00–23:59)")
    h, m = v.split(":")
    return f"{int(h):02d}:{m}"


def parse_int(value: str, *, lo: int, hi: int) -> int:
    try:
        n = int(value.strip())
    except (TypeError, ValueError):
        raise ValueError(f"Введите целое число от {lo} до {hi}.")
    if not lo <= n <= hi:
        raise ValueError(f"Значение должно быть от {lo} до {hi}.")
    return n


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def validate_time_order(a: str, b: str, *, allow_equal: bool) -> bool:
    """True, если b не раньше a (или равен, если allow_equal)."""
    ma, mb = _to_min(a), _to_min(b)
    return mb >= ma if allow_equal else mb > ma


def format_summary(entry: CSDEntryInput, m: SleepMetrics) -> str:
    """Краткая сводка перед сохранением."""
    lines = [
        "Проверьте данные:",
        f"Дата: {entry.entry_date.isoformat()}",
        f"Lights out: {entry.lights_out} → подъём: {entry.final_wake}",
        f"SOL: {entry.sol_min} мин, WASO: {entry.waso_min} мин, пробуждений: {entry.awakenings_count}",
        f"Качество: {entry.quality}/5",
        "",
        f"TIB: {m.tib_min} мин ({m.tib_hours:.1f} ч)",
        f"TST: {m.tst_min} мин ({m.tst_hours:.1f} ч)",
        f"SE: {m.se_percent:.1f}%",
    ]
    warnings = entry.sanity_notes()
    if warnings:
        lines.append("")
        lines.extend(f"⚠ {w}" for w in warnings)
    return "\n".join(lines)
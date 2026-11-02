"""CSV-экспорт данных дневника и опросников."""
from __future__ import annotations

import csv
import io
from typing import Sequence

from bot.db.models import Questionnaire, SleepEntry


SLEEP_CSV_HEADER = [
    "entry_date", "lights_out", "try_sleep", "final_wake",
    "tib_min", "sol_min", "waso_min", "tst_min", "se_percent",
    "awakenings_count", "quality", "notes",
    "caffeine_after_16", "alcohol_evening", "screen_before_bed",
    "activity_level", "stress_level",
]


def entries_to_csv(rows: Sequence[SleepEntry]) -> bytes:
    """SleepEntry[] → CSV (UTF-8 с BOM — Excel корректно откроет)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(SLEEP_CSV_HEADER)
    for r in rows:
        writer.writerow([
            r.entry_date.isoformat(),
            r.lights_out, r.try_sleep, r.final_wake,
            r.tib_min, r.sol_min, r.waso_min, r.tst_min, r.se_percent,
            r.awakenings_count, r.quality,
            # Заметки НЕ выгружаем в CSV: содержат свободный текст, могут
            # содержать лишнее. В отчёт врача — по запросу, в /export — нет.
            "",
            int(r.caffeine_after_16), int(r.alcohol_evening), int(r.screen_before_bed),
            r.activity_level, r.stress_level,
        ])
    return buf.getvalue().encode("utf-8-sig")


def questionnaires_to_csv(rows: Sequence[Questionnaire]) -> bytes:
    """Questionnaire[] → CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["created_at", "type", "score", "interpretation"])
    for r in rows:
        writer.writerow([r.created_at.isoformat(), r.type, r.score, r.interpretation])
    return buf.getvalue().encode("utf-8-sig")
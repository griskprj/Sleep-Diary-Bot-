"""
Конфигурация приложения. Читает переменные окружения через pydantic-settings.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки бота. Значения по умолчанию — безопасные для dev."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str = Field(..., alias="BOT_TOKEN")

    # Пути
    base_dir: Path = Field(default=Path(__file__).resolve().parent.parent)
    db_path: Path = Field(default=Path("data/sleep_diary.sqlite3"))

    # Часовой пояс по умолчанию (IANA). Пользователь может переопределить.
    default_tz: str = Field(default="Europe/Moscow")

    # Логирование
    log_level: str = Field(default="INFO")

    # Расписание
    weekly_digest_weekday: int = Field(default=0)
    weekly_digest_hour: int = Field(default=9)

    # Отчёты
    report_days_default: int = Field(default=14)

    @property
    def db_url(self) -> str:
        """SQLAlchemy URL для aiosqlite."""
        path = self.base_dir / self.db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{path}"


settings = Settings()  # type: ignore[call-arg]
# Sleep Diary Bot

Telegram-бот для ведения дневника сна по **Consensus Sleep Diary (CSD)** с
клинически осмысленной аналитикой. Собирает данные по валидированным шкалам
(CSD, ISI, PSQI, ESS, STOP-BANG), считает метрики, формирует **гипотезы**
(не диагнозы) и доказательные рекомендации по **CBT-I**.

**Бот не ставит диагнозов и не назначает препараты.** Все выводы — «обратите
внимание», сопровождаются источником (PMID/DOI) и дисклеймером.

---

## Возможности

| Команда | Что делает |
|---|---|
| `/start` | Приветствие, дисклеймер, список команд |
| `/diary` | Утренний опрос по Consensus Sleep Diary (9 шагов + факторы) |
| `/isi` | Insomnia Severity Index (7 пунктов, 0–28) |
| `/psqi` | Pittsburgh Sleep Quality Index (упрощённый, 5 компонентов) |
| `/ess` | Epworth Sleepiness Scale (8 ситуаций, 0–24) |
| `/stopbang` | Скрининг апноэ сна (8 да/нет) |
| `/stats [N]` | Статистика за N дней (по умолчанию 14): метрики, тренды, гипотезы |
| `/advice` | Персональные CBT-I рекомендации, привязанные к вашим данным |
| `/report [N]` | Отчёт для врача (текст + CSV) |
| `/export` | CSV с дневником и опросниками |
| `/remind HH:MM` | Ежедневное напоминание об `/diary` |
| `/remind off` | Отключить напоминание |
| `/about` | Методология и источники |
| `/delete_me` | Удалить все данные (необратимо) |

Дополнительно:
- **Недельный дайджест** — раз в неделю в понедельник 09:00 (настраивается в `.env`):
  SE/TST за неделю vs прошлая + активные гипотезы.
- **Заметки** в дневнике **не выгружаются** в CSV и **не логируются** — этика/приватность.

---

## Установка

### Требования
- Python **3.11+** (рекомендуется 3.12; на 3.13/3.14 нужны C++ Build Tools для
  сборки `aiohttp`/`pydantic-core`, если нет готовых wheel).
- Windows: если `pip install` падает на `aiohttp`/`pydantic-core` — установите
  [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
  с workload **«Разработка классических приложений на C++»**.

### Шаги

```powershell
# 1. Клонировать / распаковать проект
cd SleepGPT

# 2. Создать виртуальное окружение
python -m venv venv
.\venv\Scripts\Activate.ps1        # Windows PowerShell
# source venv/bin/activate          # Linux/Mac

# 3. Установить зависимости
pip install --upgrade pip
pip install -r requirements.txt

# 4. Настроить .env
copy .env.example .env
# отредактировать .env: вписать BOT_TOKEN от @BotFather

# 5. Запустить
python -m bot.main
import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


def parse_time(value: str) -> time:
    hours, minutes = value.strip().split(":")
    return time(int(hours), int(minutes))


def parse_breaks(value: str) -> tuple[tuple[time, time], ...]:
    result = []
    for chunk in filter(None, (c.strip() for c in value.split(","))):
        start, end = chunk.split("-")
        result.append((parse_time(start), parse_time(end)))
    return tuple(result)


def parse_ints(value: str) -> frozenset[int]:
    return frozenset(int(v) for v in value.replace(" ", "").split(",") if v)


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    db_path: str
    tz: ZoneInfo
    currency: str
    work_start: time
    work_end: time
    breaks: tuple[tuple[time, time], ...]
    work_days: frozenset[int]
    slot_step: int
    days_ahead: int
    min_lead: int
    remind_before: int
    max_active_per_user: int
    demo_mode: bool = False


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан (см. .env.example)")

    cfg = Config(
        bot_token=token,
        admin_ids=parse_ints(os.getenv("ADMIN_IDS", "")),
        db_path=os.getenv("DB_PATH", "data/bot.db"),
        tz=ZoneInfo(os.getenv("TIMEZONE", "Asia/Almaty")),
        currency=os.getenv("CURRENCY", "₸"),
        work_start=parse_time(os.getenv("WORK_START", "10:00")),
        work_end=parse_time(os.getenv("WORK_END", "20:00")),
        breaks=parse_breaks(os.getenv("BREAKS", "")),
        work_days=parse_ints(os.getenv("WORK_DAYS", "1,2,3,4,5,6")),
        slot_step=int(os.getenv("SLOT_STEP_MINUTES", "30")),
        days_ahead=int(os.getenv("DAYS_AHEAD", "14")),
        min_lead=int(os.getenv("MIN_LEAD_MINUTES", "60")),
        remind_before=int(os.getenv("REMIND_BEFORE_MINUTES", "120")),
        max_active_per_user=int(os.getenv("MAX_ACTIVE_PER_USER", "3")),
        demo_mode=os.getenv("DEMO_MODE", "0").strip().lower() in ("1", "true", "yes"),
    )
    if cfg.work_start >= cfg.work_end:
        raise RuntimeError("WORK_START должен быть раньше WORK_END")
    if cfg.slot_step <= 0 or cfg.days_ahead <= 0:
        raise RuntimeError("SLOT_STEP_MINUTES и DAYS_AHEAD должны быть > 0")
    if not cfg.work_days <= set(range(1, 8)):
        raise RuntimeError("WORK_DAYS: допустимы значения 1..7")
    return cfg

from datetime import date, datetime, timedelta

from bot.config import Config

Interval = tuple[datetime, datetime]


def candidate_days(cfg: Config, now: datetime) -> list[date]:
    today = now.date()
    days = (today + timedelta(days=i) for i in range(cfg.days_ahead))
    return [d for d in days if d.isoweekday() in cfg.work_days]


def free_slots(cfg: Config, day: date, duration: int, busy: list[Interval], now: datetime) -> list[datetime]:
    """Свободные начала слотов: в рабочее время, вне перерывов и чужих записей, не раньше now + min_lead."""
    if day not in candidate_days(cfg, now):
        return []

    blocked = list(busy) + [
        (datetime.combine(day, start), datetime.combine(day, end)) for start, end in cfg.breaks
    ]
    length = timedelta(minutes=duration)
    step = timedelta(minutes=cfg.slot_step)
    earliest = now + timedelta(minutes=cfg.min_lead)
    day_end = datetime.combine(day, cfg.work_end)

    result = []
    slot = datetime.combine(day, cfg.work_start)
    while slot + length <= day_end:
        end = slot + length
        if slot >= earliest and not any(b_start < end and b_end > slot for b_start, b_end in blocked):
            result.append(slot)
        slot += step
    return result

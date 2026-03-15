"""
极简提醒引擎：完全内存实现，不依赖 json 缓存文件。

职责：
- 根据日程的日期 / 时间 / 重复类型 / 提前分钟数，判断“现在”是否该提醒。
- 在内存中记录本次运行内每条日程的“已提醒时间”和“延期截止时间”。
"""

from datetime import datetime, date, time, timedelta
from config import (
    REPEAT_ONCE, REPEAT_DAILY, REPEAT_WEEKLY, REPEAT_WEEKDAYS, REPEAT_WEEKENDS,
    REMINDER_WINDOW_MINUTES, REMINDER_WINDOW_START_EARLY_SECONDS,
)

# 本次运行内状态（只存在于内存）
_last_triggered: dict[int, datetime] = {}  # id -> datetime
_snoozes: dict[int, datetime] = {}         # id -> datetime


def _parse_time(t_str: str) -> time:
    """'HH:MM' 或 'HH:MM:SS' -> time，解析失败返回 00:00"""
    if not t_str:
        return time(0, 0)
    try:
        parts = str(t_str).strip().split(":")
        h = int(parts[0]) if parts else 0
        m = int(parts[1]) if len(parts) > 1 else 0
        return time(h, m)
    except Exception:
        return time(0, 0)


def _parse_date(d_str: str) -> date | None:
    """'YYYY-MM-DD' -> date，解析失败返回 None"""
    if not d_str:
        return None
    s = str(d_str).strip()[:10]
    try:
        return datetime.strptime(s.replace("/", "-"), "%Y-%m-%d").date()
    except Exception:
        return None


def _is_today_valid_for_repeat(schedule: dict, today: date) -> bool:
    """今天是否满足重复规则。"""
    repeat_type = schedule.get("repeat_type") or REPEAT_ONCE
    sdate = _parse_date(schedule.get("schedule_date"))

    if repeat_type == REPEAT_ONCE:
        return sdate is not None and sdate == today
    if repeat_type == REPEAT_DAILY:
        return True
    if repeat_type == REPEAT_WEEKLY:
        return sdate is not None and today.weekday() == sdate.weekday()
    if repeat_type == REPEAT_WEEKDAYS:
        return 0 <= today.weekday() <= 4
    if repeat_type == REPEAT_WEEKENDS:
        return today.weekday() >= 5
    return False


def _now_in_window(schedule: dict, now: datetime) -> bool:
    """
    当前时间是否落在提醒窗口内：
    窗口 = [ 提醒时刻 - 提前分钟 - 提前秒, 日程时刻 + REMINDER_WINDOW_MINUTES ]
    """
    today = now.date()
    schedule_time = _parse_time(schedule.get("schedule_time"))
    advance = int(schedule.get("advance_minutes") or 0)

    schedule_dt = datetime.combine(today, schedule_time)
    remind_at = schedule_dt - timedelta(minutes=advance)
    window_start = remind_at - timedelta(seconds=REMINDER_WINDOW_START_EARLY_SECONDS)
    window_end = schedule_dt + timedelta(minutes=REMINDER_WINDOW_MINUTES)

    return window_start <= now <= window_end


def mark_triggered(schedule: dict, when: datetime | None = None) -> None:
    """标记此日程在本次程序运行内已经弹过一次。"""
    when = when or datetime.now()
    sid = schedule.get("id")
    if sid is None:
        return
    try:
        sid = int(sid)
    except Exception:
        return
    _last_triggered[sid] = when


def snooze(schedule: dict, minutes: int) -> None:
    """为此日程设置延期时间，并清除本轮已触发标记。"""
    sid = schedule.get("id")
    if sid is None:
        return
    try:
        sid = int(sid)
    except Exception:
        return
    until = datetime.now() + timedelta(minutes=minutes)
    _snoozes[sid] = until
    _last_triggered.pop(sid, None)


def should_trigger(schedule: dict, now: datetime | None = None) -> bool:
    """
    判断「现在」是否应该为这条日程弹窗。

    条件：
    1. 已开启提醒
    2. 今天满足重复规则
    3. 当前时间在提醒窗口内
    4. 不在延期中
    5. 本次运行内还没在本窗口内触发过
    """
    if not schedule or not schedule.get("remind_enabled", 1):
        return False

    sid = schedule.get("id")
    if sid is None:
        return False
    try:
        sid = int(sid)
    except Exception:
        return False

    now = now or datetime.now()
    today = now.date()

    if not _is_today_valid_for_repeat(schedule, today):
        return False

    if not _now_in_window(schedule, now):
        return False

    # 延期中：在延期截止时间之前不触发
    snooze_until = _snoozes.get(sid)
    if snooze_until and now < snooze_until:
        return False

    # 本次运行内如果已经在本窗口内触发过，就不再触发
    last = _last_triggered.get(sid)
    if last and last.date() == today and _now_in_window(schedule, last):
        return False

    return True


def get_next_remind_datetime(schedules: list, now: datetime | None = None) -> datetime | None:
    """返回今日接下来最近一次提醒时刻；无则返回 None。用于压力条等展示。"""
    now = now or datetime.now()
    today = now.date()
    candidates = []
    for s in schedules:
        if not s.get("remind_enabled", 1):
            continue
        if not _is_today_valid_for_repeat(s, today):
            continue
        t = _parse_time(s.get("schedule_time"))
        advance = int(s.get("advance_minutes") or 0)
        schedule_dt = datetime.combine(today, t)
        remind_at = schedule_dt - timedelta(minutes=advance)
        if remind_at >= now:
            candidates.append(remind_at)
    return min(candidates) if candidates else None


def get_notification_status(schedule: dict) -> str:
    """
    列表展示用的提醒状态（仅基于当前运行的内存状态）：
    - 已关闭提醒
    - 已延期
    - 今日已提醒
    - 待提醒
    """
    if not schedule.get("remind_enabled", 1):
        return "已关闭提醒"

    sid = schedule.get("id")
    try:
        sid = int(sid)
    except Exception:
        sid = None

    now = datetime.now()
    today = now.date()

    if sid is not None:
        snooze_until = _snoozes.get(sid)
        if snooze_until and now < snooze_until:
            return "已延期"

        last = _last_triggered.get(sid)
        if last and last.date() == today:
            return "今日已提醒"

    return "待提醒"

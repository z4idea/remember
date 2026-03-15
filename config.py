# -*- coding: utf-8 -*-
"""应用配置与常量"""

# 重复类型
REPEAT_ONCE = "once"
REPEAT_DAILY = "daily"
REPEAT_WEEKLY = "weekly"
REPEAT_WEEKDAYS = "weekdays"  # 周一至周五
REPEAT_WEEKENDS = "weekends"  # 周六周日

REPEAT_OPTIONS = [
    ("仅一次", REPEAT_ONCE),
    ("每天", REPEAT_DAILY),
    ("每周", REPEAT_WEEKLY),
    ("工作日（周一至周五）", REPEAT_WEEKDAYS),
    ("周末（周六、周日）", REPEAT_WEEKENDS),
]

# 提前提醒分钟数选项
ADVANCE_MINUTES_OPTIONS = [0, 5, 10, 15, 30, 60, 120]

# 路径（打包成 exe 时使用 exe 所在目录存放数据）
import os
import sys

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "schedules.db")
REMINDERS_CACHE_PATH = os.path.join(BASE_DIR, "last_reminders.json")
REMINDERS_SNOOZE_PATH = os.path.join(BASE_DIR, "snooze.json")

# 延期再提醒的分钟数
SNOOZE_MINUTES = 5

# 检查间隔（秒），3 秒一次
CHECK_INTERVAL = 3

# 提醒时间窗口：日程时刻之后多少分钟内仍会触发（避免漏提醒）
REMINDER_WINDOW_MINUTES = 5

# 提前进入窗口的秒数（设置为 0，确保不会提前提醒）
REMINDER_WINDOW_START_EARLY_SECONDS = 0

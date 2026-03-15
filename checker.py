"""
后台提醒检查（极简版）：

每 CHECK_INTERVAL 秒：
1. 从数据库取出所有日程
2. 对每条开启提醒的日程调用 reminder_engine.should_trigger
3. 若应提醒，则先 mark_triggered，再放入弹窗队列
"""

import threading
import time
from datetime import datetime

from database import get_all_schedules
from reminder_engine import should_trigger, mark_triggered
from notification import queue_popup
from config import CHECK_INTERVAL


def _run_check() -> None:
    now = datetime.now()
    schedules = get_all_schedules()
    for s in schedules:
        if not s.get("remind_enabled", 1):
            continue
        if not should_trigger(s, now=now):
            continue
        # 标记本次运行内已触发，避免重复弹窗
        mark_triggered(s, when=now)
        title = s.get("title") or "日程提醒"
        msg = f"时间：{s.get('schedule_date', '')} {s.get('schedule_time', '')}"
        note = (s.get("note") or "").strip()
        sid = s.get("id")
        queue_popup(title, msg, note, schedule_id=sid)


def start_background_checker() -> None:
    def loop() -> None:
        while True:
            try:
                _run_check()
            except Exception:
                # 避免线程崩溃
                pass
            time.sleep(CHECK_INTERVAL)

    t = threading.Thread(target=loop, daemon=True)
    t.start()

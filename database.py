# -*- coding: utf-8 -*-
"""日程数据存储"""

import sqlite3
from datetime import datetime
from config import DB_PATH, REPEAT_ONCE


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            note TEXT,
            schedule_date DATE NOT NULL,
            schedule_time TEXT NOT NULL,
            repeat_type TEXT NOT NULL DEFAULT 'once',
            advance_minutes INTEGER NOT NULL DEFAULT 0,
            remind_enabled INTEGER NOT NULL DEFAULT 1,
            group_name TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    try:
        conn.execute("ALTER TABLE schedules ADD COLUMN group_name TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def add_schedule(title, note, schedule_date, schedule_time, repeat_type=REPEAT_ONCE,
                 advance_minutes=0, remind_enabled=True, group_name=""):
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO schedules 
           (title, note, schedule_date, schedule_time, repeat_type, advance_minutes, remind_enabled, group_name, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, note or "", schedule_date, schedule_time, repeat_type, advance_minutes, 1 if remind_enabled else 0, (group_name or "").strip(), now, now)
    )
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def update_schedule(sid, title, note, schedule_date, schedule_time, repeat_type,
                    advance_minutes, remind_enabled, group_name=""):
    now = datetime.now().isoformat()
    conn = get_connection()
    conn.execute(
        """UPDATE schedules SET 
           title=?, note=?, schedule_date=?, schedule_time=?, repeat_type=?, 
           advance_minutes=?, remind_enabled=?, group_name=?, updated_at=?
           WHERE id=?""",
        (title, note or "", schedule_date, schedule_time, repeat_type,
         advance_minutes, 1 if remind_enabled else 0, (group_name or "").strip(), now, sid)
    )
    conn.commit()
    conn.close()


def delete_schedule(sid):
    conn = get_connection()
    conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
    conn.commit()
    conn.close()


def get_all_schedules():
    # 使用无 row_factory 的连接，保证 fetchall() 返回元组，r[0] 即 id，避免 Row 导致 id 错位
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, title, note, schedule_date, schedule_time, repeat_type, advance_minutes, remind_enabled, group_name, created_at, updated_at FROM schedules ORDER BY id ASC"
    ).fetchall()
    columns = ["id", "title", "note", "schedule_date", "schedule_time", "repeat_type", "advance_minutes", "remind_enabled", "group_name", "created_at", "updated_at"]
    result = [dict(zip(columns, r)) for r in rows]
    conn.close()
    return result


def get_all_group_names():
    """返回已使用的全部分组名（不含空），用于下拉补全。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT group_name FROM schedules WHERE group_name IS NOT NULL AND group_name != '' ORDER BY group_name"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_schedule_by_id(sid):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, title, note, schedule_date, schedule_time, repeat_type, advance_minutes, remind_enabled, group_name, created_at, updated_at FROM schedules WHERE id=?", (sid,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    columns = ["id", "title", "note", "schedule_date", "schedule_time", "repeat_type", "advance_minutes", "remind_enabled", "group_name", "created_at", "updated_at"]
    conn.close()
    return dict(zip(columns, row))

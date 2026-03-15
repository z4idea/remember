# -*- coding: utf-8 -*-
"""
任务日压力可视化：主窗口最小化到托盘时，在任务栏系统托盘左侧显示动态柱状图
（紧贴任务栏、在 WiFi/声音/电池/时钟 图标左侧，不遮挡图标）。
根据「距离最近一次提醒」的剩余比例分三档配色。
"""

import math
import sys
import tkinter as tk
from datetime import datetime

from database import get_all_schedules
from reminder_engine import get_next_remind_datetime

# 压力条数量、刷新间隔(ms)、参考时间跨度(分钟)
NUM_BARS = 7
UPDATE_MS = 80
PRESSURE_SPAN_MINUTES = 60
TRANSPARENT_BG = "#010002"
# 任务栏高度（与任务栏同高，嵌入同一行）；右侧预留像素（更小=压力条更靠右，贴近 WiFi/声音/电池）
TASKBAR_HEIGHT = 48
TRAY_RESERVED_PX = 175

# 三档压力：剩余 100%～2/3 轻松 / 2/3～1/3 稍有压力 / 1/3～0 压力大
# 每档多色，柱子轮流取不同色，避免单调
COLOR_RELAXED = ["#66bb6a", "#81c784", "#a5d6a7", "#4db6ac", "#80cbc4", "#26a69a", "#2e7d32"]
COLOR_MEDIUM = ["#ffb74d", "#ffca28", "#ffa726", "#ffcc80", "#ffb300", "#ff8f00", "#ff9800"]
COLOR_URGENT = ["#ef5350", "#e57373", "#f44336", "#ec407a", "#f48fb1", "#d32f2f", "#c62828"]


def _remaining_ratio(schedules) -> float:
    """距离最近一次提醒的剩余比例：1=还很远，0=马上/已到。基于 PRESSURE_SPAN_MINUTES 内的分钟数。"""
    next_at = get_next_remind_datetime(schedules, datetime.now())
    if next_at is None:
        return 1.0
    delta_min = (next_at - datetime.now()).total_seconds() / 60.0
    if delta_min <= 0:
        return 0.0
    return min(1.0, delta_min / PRESSURE_SPAN_MINUTES)


def _pressure_tier(ratio: float) -> int:
    """0=轻松(剩余>2/3)，1=稍有压力(2/3～1/3)，2=压力大(1/3～0)。"""
    if ratio > 2.0 / 3:
        return 0
    if ratio > 1.0 / 3:
        return 1
    return 2


def _colors_for_tier(tier: int):
    if tier == 0:
        return COLOR_RELAXED
    if tier == 1:
        return COLOR_MEDIUM
    return COLOR_URGENT


def _win32_screen_size():
    """用 Win32 获取主屏宽高，不依赖 Tk。"""
    if sys.platform != "win32":
        return 1920, 1080
    try:
        import ctypes
        SM_CXSCREEN = 0
        SM_CYSCREEN = 1
        sw = ctypes.windll.user32.GetSystemMetrics(SM_CXSCREEN)
        sh = ctypes.windll.user32.GetSystemMetrics(SM_CYSCREEN)
        return max(800, sw), max(600, sh)
    except Exception:
        return 1920, 1080


def _win32_move_to_taskbar_left(hwnd, x, y, w, h):
    """用 Win32 将窗口移动到屏幕坐标 (x,y)，尺寸 (w,h)。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        GA_ROOT = 2
        top = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)
        if not top:
            top = hwnd
        SWP_NOACTIVATE = 0x0010
        SWP_NOZORDER = 0x0004
        ctypes.windll.user32.SetWindowPos(
            top, None, int(x), int(y), int(w), int(h),
            SWP_NOACTIVATE | SWP_NOZORDER
        )
    except Exception:
        pass


class PressureOverlay(tk.Toplevel):
    """任务栏系统托盘左侧的细条窗口：与任务栏同高，在 WiFi/声音等图标左侧，不遮挡图标。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=TRANSPARENT_BG)
        try:
            self.attributes("-transparentcolor", TRANSPARENT_BG)
        except tk.TclError:
            pass
        self._bars = []
        self._anim_offset = 0.0
        self._win_w = 140
        self._win_h = TASKBAR_HEIGHT
        self.withdraw()

        self._canvas = tk.Canvas(
            self, width=self._win_w, height=self._win_h,
            bg=TRANSPARENT_BG, highlightthickness=0
        )
        self._canvas.pack(fill="both", expand=True)
        self._build_bars()
        self._tick_count = 0
        self._tick()

    def show_overlay(self):
        """显示并定位到任务栏系统托盘左侧（不遮挡 WiFi/声音等图标）。"""
        self._place_bottom_right()
        self.deiconify()
        self.update_idletasks()
        self.lift()
        for delay in (30, 80, 200):
            self.after(delay, self._place_bottom_right)

    def hide_overlay(self):
        """隐藏。"""
        self.withdraw()

    def _place_bottom_right(self):
        if not self.winfo_exists():
            return
        self.update_idletasks()
        # 用 Win32 取屏宽高，避免父窗口最小化时 Tk 取到 0 或错误值
        sw, sh = _win32_screen_size()
        # 贴在任务栏同一行，且在系统托盘（WiFi/声音/电池/时钟）左侧，不遮挡图标
        x = sw - TRAY_RESERVED_PX - self._win_w
        y = sh - self._win_h
        geom = "%dx%d+%d+%d" % (self._win_w, self._win_h, x, y)
        self.wm_geometry(geom)
        self.geometry(geom)
        try:
            hwnd = self.winfo_id()
            _win32_move_to_taskbar_left(hwnd, x, y, self._win_w, self._win_h)
        except Exception:
            pass

    def _build_bars(self):
        self._bars = []
        cw, ch = self._win_w, self._win_h
        gap = 4
        bar_w = max(4, (cw - (NUM_BARS + 1) * gap) // NUM_BARS)
        for i in range(NUM_BARS):
            x1 = gap + i * (bar_w + gap)
            x2 = x1 + bar_w
            self._bars.append((x1, x2, ch - 4))

    def _should_overlay_be_visible(self):
        """主窗口未打开（已最小化到托盘）时，压力条应常驻。"""
        if not self._parent:
            return False
        try:
            return not self._parent.winfo_viewable()
        except Exception:
            return False

    def _tick(self):
        try:
            should_show = self._should_overlay_be_visible()
            if should_show:
                try:
                    if not self.winfo_viewable():
                        self.deiconify()
                        self.attributes("-topmost", True)
                        self.lift()
                        self._place_bottom_right()
                except Exception:
                    pass
            schedules = get_all_schedules()
            ratio = _remaining_ratio(schedules)
            tier = _pressure_tier(ratio)
            self._anim_offset += 0.28
            if self._anim_offset > 100 * math.pi:
                self._anim_offset -= 100 * math.pi
            self._draw_bars(tier, ratio)
            self._tick_count += 1
            if self._tick_count % 15 == 0 and should_show:
                try:
                    if self.winfo_viewable():
                        self._place_bottom_right()
                        self.attributes("-topmost", True)
                except Exception:
                    pass
        except Exception:
            pass
        if self.winfo_exists():
            self.after(UPDATE_MS, self._tick)

    def _draw_bars(self, tier: int, remaining_ratio: float):
        self._canvas.delete("bars")
        ch = self._win_h - 4
        t = self._anim_offset
        palette = _colors_for_tier(tier)
        for i, (x1, x2, y_bottom) in enumerate(self._bars):
            phase = t + i * 0.7
            bounce = math.sin(t * 1.5 + i * 0.5) * 0.12
            wave = math.sin(phase) * 0.25 + math.sin(phase * 2.3) * 0.1
            base = 0.4 + 0.35 * (1.0 - remaining_ratio)
            scale = base + wave + bounce
            scale = max(0.2, min(0.96, scale))
            h = (ch - 4) * scale
            y1 = y_bottom - h
            color = palette[i % len(palette)]
            self._canvas.create_rectangle(x1, y1, x2, y_bottom, fill=color, outline="", tags="bars")
        self._canvas.tag_raise("bars")

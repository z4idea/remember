"""弹窗提醒（极简版）：置顶窗口 + 队列处理 + 延期（完全内存实现）"""

import queue
import threading

from config import SNOOZE_MINUTES
from reminder_engine import snooze

# 队列元素：(title, message, note, schedule_id)
_reminder_queue: "queue.Queue[tuple]" = queue.Queue()
_refresh_callback = None


def set_refresh_callback(callback):
    """主窗口调用：点击「知道了」/「延期」后刷新列表。"""
    global _refresh_callback
    _refresh_callback = callback


def queue_popup(title, message, note: str = "", schedule_id=None):
    """后台线程调用：将提醒放入队列，由主线程弹窗。"""
    _reminder_queue.put((title, message, note or "", schedule_id))


def _show_popup_window(parent, title, message, note: str = "", schedule_id=None):
    """
    在主线程中显示 CustomTkinter 置顶弹窗，使用当前主题玻璃风格。
    """
    import customtkinter as ctk
    from themes import get_theme_colors, glass_frame_kw

    c = get_theme_colors()
    gkw = glass_frame_kw()

    win = ctk.CTkToplevel(parent)
    win.title("日程提醒")
    win.geometry("400x220")
    win.configure(fg_color=c["bg"])
    win.attributes("-topmost", True)
    win.resizable(False, False)

    win.update_idletasks()
    w, h = 400, 220
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")

    frame = ctk.CTkFrame(win, **gkw)
    frame.pack(fill="both", expand=True, padx=24, pady=24)

    ctk.CTkLabel(
        frame, text=title, font=ctk.CTkFont(size=18, weight="bold"), text_color=c["text"],
    ).pack(anchor="w", pady=(0, 8))

    ctk.CTkLabel(
        frame, text=message, font=ctk.CTkFont(size=14),
        text_color=c["text_secondary"], wraplength=340,
    ).pack(anchor="w", pady=(0, 4))

    if note:
        ctk.CTkLabel(
            frame, text=note, font=ctk.CTkFont(size=12),
            text_color=c["text_secondary"], wraplength=340,
        ).pack(anchor="w", pady=(0, 16))
    else:
        frame.pack_configure(pady=(0, 16))

    btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
    btn_frame.pack(pady=(8, 0))

    def _after_action():
        if _refresh_callback:
            try:
                _refresh_callback()
            except Exception:
                pass

    def on_ok():
        _after_action()
        win.destroy()

    def on_snooze():
        if schedule_id is not None:
            snooze({"id": schedule_id}, SNOOZE_MINUTES)
        _after_action()
        win.destroy()

    ctk.CTkButton(
        btn_frame, text="知道了", width=110, command=on_ok,
        fg_color=c["accent"], hover_color=c.get("accent_hover", c["accent"]),
        text_color=c.get("accent_text", c["text"]),
    ).pack(side="left", padx=(0, 10))
    if schedule_id is not None:
        ctk.CTkButton(
            btn_frame, text=f"{SNOOZE_MINUTES} 分钟后再提醒", width=150, command=on_snooze,
            fg_color=c["glass"], border_width=1, border_color=c["glass_border"],
        ).pack(side="left")

    # 不要调用单独的 mainloop，交给主窗口的 mainloop 驱动


def show_popup(title, message, note: str = ""):
    """备用：无队列时直接弹窗。"""

    # 备用接口：创建一个独立根窗口弹一次即可
    import customtkinter as ctk

    root = ctk.CTk()
    _show_popup_window(root, title, message, note, schedule_id=None)
    root.mainloop()


def process_pending_popups(root):
    """
    主窗口中通过 after 循环调用。
    每次最多弹出一条，弹出后立即再调度自己；队列空时 1 秒后再检查。
    """
    try:
        title, message, note, schedule_id = _reminder_queue.get_nowait()
        _show_popup_window(root, title, message, note, schedule_id)
        next_delay = 0
    except queue.Empty:
        next_delay = 1000

    if root.winfo_exists():
        root.after(next_delay, lambda: process_pending_popups(root))


def _fallback_notification(title, message):
    try:
        from plyer import notification
        notification.notify(title=title or "日程提醒", message=message or "", app_name="日程提醒")
    except Exception:
        pass

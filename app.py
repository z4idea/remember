import sys
import threading

import customtkinter as ctk
from datetime import datetime, date, timedelta
from PIL import Image, ImageDraw
import pystray
from database import (
    init_db, get_all_schedules, add_schedule, update_schedule, delete_schedule,
    get_schedule_by_id,
)
from config import REPEAT_OPTIONS, ADVANCE_MINUTES_OPTIONS
from reminder_engine import get_notification_status
from checker import start_background_checker
from notification import process_pending_popups, set_refresh_callback
from pressure_overlay import PressureOverlay

# 主题与外观（使用 themes 模块，启动时应用当前主题）
ctk.set_appearance_mode("dark")
from themes import (
    get_current_theme_id, set_theme, get_theme_colors,
    glass_frame_kw, card_frame_kw, THEME_IDS, THEME_NAMES,
)


def _format_repeat_label(repeat_type):
    for label, rtype in REPEAT_OPTIONS:
        if rtype == repeat_type:
            return label
    return repeat_type or "仅一次"


def _format_advance(minutes):
    if minutes == 0:
        return "准时"
    return f"提前 {minutes} 分钟"


def _status_color(status_text, theme_colors=None):
    """提醒状态对应的强调色；若传入 theme_colors 则用主题色系。"""
    if theme_colors:
        accent = theme_colors.get("accent", "#64b5f6")
        if status_text == "今日已提醒":
            return "#81c784", accent
        if status_text == "已延期":
            return "#ffb74d", accent
        if status_text == "待提醒":
            return accent, theme_colors.get("accent_hover", accent)
        return theme_colors.get("text_secondary", "#9e9e9e"), accent
    if status_text == "今日已提醒":
        return "#2e7d32", "#81c784"
    if status_text == "已延期":
        return "#e65100", "#ffb74d"
    if status_text == "待提醒":
        return "#1565c0", "#64b5f6"
    return "#616161", "#9e9e9e"


def _validate_date(s):
    """校验日期字符串，支持 YYYY-MM-DD / YYYY/MM/DD。返回 (是否合法, 规范后的 YYYY-MM-DD 或 None)。"""
    if not s or not str(s).strip():
        return False, None
    raw = str(s).strip().replace("/", "-")[:10]
    try:
        d = datetime.strptime(raw, "%Y-%m-%d")
        return True, d.strftime("%Y-%m-%d")
    except ValueError:
        return False, None


def _validate_time(s):
    """校验时间字符串，支持 HH:MM 或 HH:MM:SS。返回 (是否合法, 规范后的字符串或 None)。"""
    if not s or not str(s).strip():
        return False, None
    raw = str(s).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(raw, fmt)
            if fmt == "%H:%M":
                return True, t.strftime("%H:%M")
            return True, t.strftime("%H:%M:%S")
        except ValueError:
            continue
    return False, None


class AddEditDialog(ctk.CTkToplevel):
    def __init__(self, parent, schedule_id=None, on_saved=None):
        super().__init__(parent)
        self.schedule_id = schedule_id
        self.on_saved = on_saved
        self._theme_id = get_current_theme_id()
        self._colors = get_theme_colors(self._theme_id)
        self.title("编辑日程" if schedule_id else "添加日程")
        self.geometry("480x640")
        self.resizable(False, False)
        self.configure(fg_color=self._colors["bg"])
        # 弹窗置顶，避免被主窗口挡住
        self.attributes("-topmost", True)
        self.after(200, self._center)
        self._build_ui()
        if schedule_id:
            self._load_schedule()
        else:
            self._set_quick_date(0)
            self.entry_time.insert(0, datetime.now().strftime("%H:%M"))
        self.after(300, self.focus_force)

    def _center(self):
        self.update_idletasks()
        w, h = 480, 640
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        gkw = glass_frame_kw(self._theme_id)
        c = self._colors
        # 底部按钮区：保存/添加 在左，取消 在右
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=24, pady=(0, 20))

        save_label = "保存" if self.schedule_id else "添加"
        save_btn = ctk.CTkButton(
            btn_frame, text=save_label, width=110, height=38, command=self._save,
            fg_color=c["accent"], hover_color=c.get("accent_hover", c["accent"]),
            text_color=c.get("accent_text", c["text"]),
        )
        save_btn.pack(side="left", padx=(0, 12))
        cancel_btn = ctk.CTkButton(
            btn_frame, text="取消", width=110, height=38, command=self.destroy,
            fg_color=c["glass"], border_width=1, border_color=c["glass_border"],
        )
        cancel_btn.pack(side="left")

        # 表单区域（玻璃风格，可滚动以免「重复/提前提醒」被裁掉）
        form_frame = ctk.CTkFrame(self, **gkw)
        form_frame.pack(fill="both", expand=True, padx=24, pady=(20, 16))
        scroll = ctk.CTkScrollableFrame(form_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # 标题
        ctk.CTkLabel(scroll, text="标题（必填）", font=ctk.CTkFont(size=13), text_color=c["text"]).pack(anchor="w", pady=(0, 4))
        self.entry_title = ctk.CTkEntry(scroll, placeholder_text="输入日程标题", height=36, fg_color=c["surface"], border_color=c["glass_border"], text_color=c["text"])
        self.entry_title.pack(fill="x", pady=(0, 12))

        # 分组（可选）
        ctk.CTkLabel(scroll, text="分组（可选）", font=ctk.CTkFont(size=13), text_color=c["text"]).pack(anchor="w", pady=(0, 4))
        self.entry_group = ctk.CTkEntry(scroll, placeholder_text="如：工作、生活，留空为无分组", height=36, fg_color=c["surface"], border_color=c["glass_border"], text_color=c["text"])
        self.entry_group.pack(fill="x", pady=(0, 12))

        # 备注
        ctk.CTkLabel(scroll, text="备注（可选）", font=ctk.CTkFont(size=13), text_color=c["text"]).pack(anchor="w", pady=(0, 4))
        self.entry_note = ctk.CTkEntry(scroll, placeholder_text="备注说明", height=36, fg_color=c["surface"], border_color=c["glass_border"], text_color=c["text"])
        self.entry_note.pack(fill="x", pady=(0, 12))

        # 日期：输入框 + 快捷（今天/明天/后天），带格式提示与校验提示
        ctk.CTkLabel(scroll, text="日期", font=ctk.CTkFont(size=13), text_color=c["text"]).pack(anchor="w", pady=(0, 4))
        self.entry_date = ctk.CTkEntry(scroll, placeholder_text="例如 2026-03-17", height=36, fg_color=c["surface"], border_color=c["glass_border"], text_color=c["text"])
        self.entry_date.pack(fill="x", pady=(0, 2))
        self.entry_date.bind("<FocusOut>", lambda e: self._on_date_entry_blur())
        date_btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        date_btn_row.pack(fill="x", pady=(4, 0))
        for label, delta in [("今天", 0), ("明天", 1), ("后天", 2)]:
            btn = ctk.CTkButton(date_btn_row, text=label, width=70, height=28, fg_color=c["glass"], text_color=c["text"], command=lambda d=delta: self._set_quick_date(d))
            btn.pack(side="left", padx=(0, 8))
        self.label_date_error = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=12), text_color="#e57373", anchor="w")
        self.label_date_error.pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(scroll, text="格式：YYYY-MM-DD", font=ctk.CTkFont(size=11), text_color=c["text_secondary"], anchor="w").pack(anchor="w", pady=(0, 12))

        # 时间：输入框，带格式提示与校验提示
        ctk.CTkLabel(scroll, text="时间", font=ctk.CTkFont(size=13), text_color=c["text"]).pack(anchor="w", pady=(0, 4))
        self.entry_time = ctk.CTkEntry(scroll, placeholder_text="例如 14:30 或 14:30:00", height=36, fg_color=c["surface"], border_color=c["glass_border"], text_color=c["text"])
        self.entry_time.pack(fill="x", pady=(0, 2))
        self.entry_time.bind("<FocusOut>", lambda e: self._on_time_entry_blur())
        self.label_time_error = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=12), text_color="#e57373", anchor="w")
        self.label_time_error.pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(scroll, text="格式：HH:MM 或 HH:MM:SS", font=ctk.CTkFont(size=11), text_color=c["text_secondary"], anchor="w").pack(anchor="w", pady=(0, 12))

        # 重复（仅一次 / 每天 / 每周 / 工作日 / 周末）
        ctk.CTkLabel(scroll, text="重复", font=ctk.CTkFont(size=13), text_color=c["text"]).pack(anchor="w", pady=(0, 4))
        self.combo_repeat = ctk.CTkComboBox(
            scroll, values=[o[0] for o in REPEAT_OPTIONS], height=36,
            fg_color=c["surface"], button_color=c["glass"], button_hover_color=c["glass_border"], text_color=c["text"],
        )
        self.combo_repeat.pack(fill="x", pady=(0, 12))

        # 提前提醒
        ctk.CTkLabel(scroll, text="提前提醒", font=ctk.CTkFont(size=13), text_color=c["text"]).pack(anchor="w", pady=(0, 4))
        advance_labels = [_format_advance(m) for m in ADVANCE_MINUTES_OPTIONS]
        self.combo_advance = ctk.CTkComboBox(
            scroll, values=advance_labels, height=36,
            fg_color=c["surface"], button_color=c["glass"], button_hover_color=c["glass_border"], text_color=c["text"],
        )
        self.combo_advance.pack(fill="x", pady=(0, 12))

        # 是否启用提醒
        self.var_remind = ctk.BooleanVar(value=True)
        self.check_remind = ctk.CTkCheckBox(
            scroll, text="启用弹窗提醒", variable=self.var_remind,
            fg_color=c["accent"], text_color=c["text"],
        )
        self.check_remind.pack(anchor="w", pady=(0, 8))

    def _set_quick_date(self, day_delta):
        d = date.today() + timedelta(days=day_delta)
        self.entry_date.delete(0, "end")
        self.entry_date.insert(0, d.strftime("%Y-%m-%d"))
        self.entry_date.configure(border_color=self._colors["glass_border"])
        self.label_date_error.configure(text="")

    def _on_date_entry_blur(self):
        s = self.entry_date.get().strip()
        ok, norm = _validate_date(s)
        if ok and norm:
            self.entry_date.configure(border_color=self._colors["glass_border"])
            self.label_date_error.configure(text="")
        elif s:
            self.entry_date.configure(border_color="#e57373")
            self.label_date_error.configure(text="日期格式错误，请使用 YYYY-MM-DD，例如 2026-03-17")
        else:
            self.label_date_error.configure(text="")

    def _on_time_entry_blur(self):
        s = self.entry_time.get().strip()
        ok, norm = _validate_time(s)
        if ok and norm:
            self.entry_time.configure(border_color=self._colors["glass_border"])
            self.label_time_error.configure(text="")
        elif s:
            self.entry_time.configure(border_color="#e57373")
            self.label_time_error.configure(text="时间格式错误，请使用 HH:MM 或 HH:MM:SS，例如 14:30")
        else:
            self.label_time_error.configure(text="")

    def _load_schedule(self):
        s = get_schedule_by_id(self.schedule_id)
        if not s:
            return
        self.entry_title.insert(0, s.get("title", ""))
        self.entry_note.insert(0, s.get("note") or "")
        self.entry_group.insert(0, s.get("group_name") or "")
        sd, st = s.get("schedule_date", ""), s.get("schedule_time", "")
        if sd:
            self.entry_date.insert(0, sd)
        if st:
            self.entry_time.insert(0, st)
        repeat_label = _format_repeat_label(s.get("repeat_type", "once"))
        for i, (label, _) in enumerate(REPEAT_OPTIONS):
            if label == repeat_label:
                self.combo_repeat.set(label)
                break
        advance = s.get("advance_minutes", 0)
        self.combo_advance.set(_format_advance(advance))
        self.var_remind.set(bool(s.get("remind_enabled", 1)))

    def _get_repeat_type(self):
        val = self.combo_repeat.get()
        for label, rtype in REPEAT_OPTIONS:
            if label == val:
                return rtype
        return "once"

    def _get_advance_minutes(self):
        val = self.combo_advance.get()
        for m in ADVANCE_MINUTES_OPTIONS:
            if _format_advance(m) == val:
                return m
        return 0

    def _save(self):
        title = self.entry_title.get().strip()
        if not title:
            return
        note = self.entry_note.get().strip()
        schedule_date = self.entry_date.get().strip()
        schedule_time = self.entry_time.get().strip()
        if not schedule_date or not schedule_time:
            return
        ok_d, norm_date = _validate_date(schedule_date)
        ok_t, norm_time = _validate_time(schedule_time)
        if not ok_d or not norm_date:
            self.entry_date.configure(border_color="#e57373")
            self.label_date_error.configure(text="日期格式错误，请使用 YYYY-MM-DD，例如 2026-03-17")
            self.entry_date.focus_set()
            return
        if not ok_t or not norm_time:
            self.entry_time.configure(border_color="#e57373")
            self.label_time_error.configure(text="时间格式错误，请使用 HH:MM 或 HH:MM:SS，例如 14:30")
            self.entry_time.focus_set()
            return
        self.label_date_error.configure(text="")
        self.label_time_error.configure(text="")
        schedule_date, schedule_time = norm_date, norm_time
        repeat_type = self._get_repeat_type()
        advance_minutes = self._get_advance_minutes()
        remind_enabled = self.var_remind.get()
        group_name = self.entry_group.get().strip()
        if self.schedule_id:
            update_schedule(
                self.schedule_id, title, note, schedule_date, schedule_time,
                repeat_type, advance_minutes, remind_enabled, group_name,
            )
        else:
            add_schedule(
                title, note, schedule_date, schedule_time,
                repeat_type, advance_minutes, remind_enabled, group_name,
            )
        if self.on_saved:
            self.on_saved()
        self.destroy()


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        init_db()
        self.title("日程提醒")
        self.geometry("720x520")
        self.minsize(560, 400)
        self.configure(fg_color=get_theme_colors()["bg"])

        # 分组展开/折叠状态
        self._group_expanded = {}
        # 托盘是否已启动
        self._tray_started = False

        self._build_ui()
        set_refresh_callback(self._refresh_list)
        self._refresh_list()
        start_background_checker()
        self.after(1000, lambda: process_pending_popups(self))

        # 关闭按钮：隐藏到托盘，而不是退出
        self.protocol("WM_DELETE_WINDOW", self._on_close_to_tray)
        self._start_tray_icon()
        # 任务日压力条（最小化时显示）
        self._pressure_overlay = PressureOverlay(self)

    def _on_close_to_tray(self):
        """点击右上角关闭按钮：隐藏到托盘并显示压力条。"""
        self._pressure_overlay.show_overlay()
        self.withdraw()

    def _build_ui(self):
        c = get_theme_colors()
        # 顶部标题、主题切换、添加按钮（保留引用以便切换主题时更新颜色）
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 12))
        self._header_title = ctk.CTkLabel(
            header, text="📅 日程提醒", font=ctk.CTkFont(size=24, weight="bold"), text_color=c["text"],
        )
        self._header_title.pack(side="left")
        theme_values = [THEME_NAMES[tid] for tid in THEME_IDS]
        self._theme_combo = ctk.CTkComboBox(
            header, values=theme_values, width=100, height=32,
            fg_color=c["glass"], button_color=c["glass_border"], text_color=c["text"],
            command=self._on_theme_changed,
        )
        self._theme_combo.set(THEME_NAMES.get(get_current_theme_id(), "蓝色"))
        self._theme_combo.pack(side="right", padx=(12, 0))
        self._add_btn = ctk.CTkButton(
            header, text="＋ 添加日程", width=120, height=36, command=self._on_add,
            fg_color=c["accent"], hover_color=c.get("accent_hover", c["accent"]),
            text_color=c.get("accent_text", c["text"]),
        )
        self._add_btn.pack(side="right")

        # 列表区域（用主题背景色，避免 transparent 被渲染成默认蓝）
        self._list_frame = ctk.CTkFrame(self, fg_color=c["bg"])
        self._list_frame.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        self.scroll = ctk.CTkScrollableFrame(self._list_frame, fg_color=c["bg"])
        self.scroll.pack(fill="both", expand=True)
        self._list_containers = []

    def _on_theme_changed(self, choice):
        for tid in THEME_IDS:
            if THEME_NAMES.get(tid) == choice:
                set_theme(tid)
                break
        c = get_theme_colors()
        self.configure(fg_color=c["bg"])
        self._list_frame.configure(fg_color=c["bg"])
        self.scroll.configure(fg_color=c["bg"])
        # 同步更新顶部标题、主题下拉框、添加按钮的颜色
        self._header_title.configure(text_color=c["text"])
        self._theme_combo.configure(
            fg_color=c["glass"], button_color=c["glass_border"], text_color=c["text"],
        )
        self._add_btn.configure(
            fg_color=c["accent"], hover_color=c.get("accent_hover", c["accent"]),
            text_color=c.get("accent_text", c["text"]),
        )
        self._refresh_list()

    def _on_add(self):
        AddEditDialog(self, on_saved=self._refresh_list)

    def _on_edit(self, sid):
        AddEditDialog(self, schedule_id=sid, on_saved=self._refresh_list)

    def _on_delete(self, sid):
        delete_schedule(sid)
        self._refresh_list()

    def _refresh_list(self):
        for c in self._list_containers:
            c.destroy()
        self._list_containers.clear()

        theme_id = get_current_theme_id()
        colors = get_theme_colors(theme_id)
        card_kw = card_frame_kw(theme_id)

        schedules = get_all_schedules()
        if not schedules:
            empty = ctk.CTkLabel(
                self.scroll,
                text="暂无日程，点击「添加日程」开始",
                font=ctk.CTkFont(size=14),
                text_color=colors["text_secondary"],
            )
            empty.pack(pady=40)
            self._list_containers.append(empty)
            return

        # 按分组展示：先按 group_name 分组，无分组的显示为「无分组」
        from collections import OrderedDict
        groups_map = OrderedDict()
        for s in schedules:
            g = (s.get("group_name") or "").strip() or "无分组"
            if g not in groups_map:
                groups_map[g] = []
            groups_map[g].append(s)

        is_first_group = True
        for group_label, group_schedules in groups_map.items():
            # 分组标题，可展开/折叠
            group_header = ctk.CTkFrame(self.scroll, fg_color="transparent")
            group_header.pack(fill="x", pady=(16 if not is_first_group else 0, 6))
            self._list_containers.append(group_header)
            is_first_group = False

            expanded = self._group_expanded.get(group_label, True)
            prefix = "▼ " if expanded else "▶ "

            def make_toggle(label=group_label):
                def _toggle():
                    current = self._group_expanded.get(label, True)
                    self._group_expanded[label] = not current
                    self._refresh_list()
                return _toggle

            ctk.CTkButton(
                group_header,
                text=prefix + group_label,
                fg_color="transparent",
                hover=False,
                text_color=colors["text_secondary"],
                anchor="w",
                command=make_toggle(),
            ).pack(fill="x")

            # 折叠状态下，不渲染该分组的日程项
            if not expanded:
                continue

            for s in group_schedules:
                row = ctk.CTkFrame(self.scroll, **card_kw)
                row.pack(fill="x", pady=4)
                self._list_containers.append(row)

                left = ctk.CTkFrame(row, fg_color="transparent")
                left.pack(side="left", fill="both", expand=True, padx=16, pady=12)
                ctk.CTkLabel(
                    left, text=s.get("title", ""), font=ctk.CTkFont(size=15, weight="bold"),
                    text_color=colors["text"], anchor="w",
                ).pack(anchor="w")
                sub = f"{s['schedule_date']} {s['schedule_time']} · {_format_repeat_label(s['repeat_type'])} · {_format_advance(s.get('advance_minutes', 0))}"
                ctk.CTkLabel(
                    left, text=sub, font=ctk.CTkFont(size=12),
                    text_color=colors["text_secondary"], anchor="w",
                ).pack(anchor="w")
                status_text = get_notification_status(s)
                fg_dark, fg_light = _status_color(status_text, colors)
                ctk.CTkLabel(
                    left, text=status_text, font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=(fg_dark, fg_light), anchor="w",
                ).pack(anchor="w", pady=(4, 0))
                if s.get("note"):
                    ctk.CTkLabel(
                        left, text=s["note"], font=ctk.CTkFont(size=12),
                        text_color=colors["text_secondary"], anchor="w", wraplength=400,
                    ).pack(anchor="w", pady=(2, 0))

                btn_frame = ctk.CTkFrame(row, fg_color="transparent")
                btn_frame.pack(side="right", padx=12, pady=12)
                sid = s["id"]
                ctk.CTkButton(
                    btn_frame, text="编辑", width=60, height=28,
                    fg_color=colors["glass"], hover_color=colors["glass_border"],
                    command=lambda sid=sid: self._on_edit(sid),
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    btn_frame, text="删除", width=60, height=28,
                    fg_color=colors["glass_border"], hover_color=colors["text_secondary"],
                    command=lambda sid=sid: self._on_delete(sid),
                ).pack(side="left", padx=2)

    # ---- 托盘 & 关闭行为 ----

    def _show_from_tray(self):
        """从托盘恢复主窗口。"""
        self._pressure_overlay.hide_overlay()
        self.deiconify()
        self.lift()
        self.focus_force()

    def _destroy_and_exit(self):
        try:
            self.destroy()
        finally:
            sys.exit(0)

    def _create_tray_image(self):
        """创建简单的托盘图标（白色日历形状）。"""
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        # 外圈
        draw.ellipse((8, 8, size - 8, size - 8), outline=(255, 255, 255, 255), width=3)
        # 中间横条
        draw.rectangle((18, size // 2 - 4, size - 18, size // 2 + 4), fill=(255, 255, 255, 255))
        return image

    def _start_tray_icon(self):
        """启动系统托盘图标（单独线程运行 pystray）。"""
        if self._tray_started:
            return
        self._tray_started = True

        def run_icon():
            image = self._create_tray_image()

            def on_show(icon, item):
                # 回到 Tk 主线程恢复窗口
                self.after(0, self._show_from_tray)

            def on_exit(icon, item):
                # 停止图标并退出
                try:
                    icon.visible = False
                    icon.stop()
                except Exception:
                    pass
                self.after(0, self._destroy_and_exit)

            menu = pystray.Menu(
                pystray.MenuItem("显示主窗口", on_show),
                pystray.MenuItem("退出", on_exit),
            )
            icon = pystray.Icon("remember", image, "日程提醒", menu)
            icon.run()

        threading.Thread(target=run_icon, daemon=True).start()


def run():
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    run()

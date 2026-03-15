# -*- coding: utf-8 -*-
"""
主题与玻璃风格（iOS 26 风格）：统一首页、添加日程、通知弹窗的视觉。
内置：粉色、紫色、淡黄、蓝色、深色。玻璃气泡感通过圆角、浅边框、半透明色模拟。
"""

import json
import os

# 主题 id -> 显示名
THEME_IDS = ["pink", "purple", "yellow", "blue", "dark"]
THEME_NAMES = {
    "pink": "粉色",
    "purple": "紫色",
    "yellow": "淡黄色",
    "blue": "蓝色",
    "dark": "深色",
}

# 每个主题：背景、玻璃表面、强调色、文字、次要文字、边框、玻璃高光、强调色上的文字（保证可读）
THEMES = {
    "pink": {
        "bg": "#1a0f12",
        "surface": "#2d1a22",
        "glass": "#3d2430",
        "glass_border": "#5a3548",
        "accent": "#e8a0b8",
        "accent_hover": "#f0b8cc",
        "text": "#f5e6eb",
        "text_secondary": "#b89ba6",
        "card": "#2a1820",
        "accent_text": "#1a0f12",
    },
    "purple": {
        "bg": "#120f1a",
        "surface": "#1e1a2d",
        "glass": "#2a243d",
        "glass_border": "#3d3560",
        "accent": "#b8a0e8",
        "accent_hover": "#ccc0f5",
        "text": "#e8e5f5",
        "text_secondary": "#9d96b8",
        "card": "#1f1929",
        "accent_text": "#120f1a",
    },
    "yellow": {
        "bg": "#1a1810",
        "surface": "#2d2a1a",
        "glass": "#3d3824",
        "glass_border": "#5a5235",
        "accent": "#e8d8a0",
        "accent_hover": "#f0e8b8",
        "text": "#f5f0e6",
        "text_secondary": "#b8b09d",
        "card": "#2a2618",
        "accent_text": "#1a1810",
    },
    "blue": {
        "bg": "#0f121a",
        "surface": "#1a2230",
        "glass": "#24303d",
        "glass_border": "#35485a",
        "accent": "#64b5f6",
        "accent_hover": "#90caf9",
        "text": "#e3f2fd",
        "text_secondary": "#9eb4c9",
        "card": "#18202a",
        "accent_text": "#0f121a",
    },
    "dark": {
        "bg": "#0d0d0d",
        "surface": "#1a1a1a",
        "glass": "#252525",
        "glass_border": "#404040",
        "accent": "#b0b0b0",
        "accent_hover": "#c8c8c8",
        "text": "#e8e8e8",
        "text_secondary": "#909090",
        "card": "#151515",
        "accent_text": "#0d0d0d",
    },
}

_CONFIG_PATH = None


def _config_path():
    global _CONFIG_PATH
    if _CONFIG_PATH is None:
        import sys
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        _CONFIG_PATH = os.path.join(base, "theme_config.json")
    return _CONFIG_PATH


def get_current_theme_id():
    path = _config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("theme", "blue")
        except Exception:
            pass
    return "blue"


def set_theme(theme_id: str):
    if theme_id not in THEMES:
        theme_id = "blue"
    path = _config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"theme": theme_id}, f, ensure_ascii=False)
    except Exception:
        pass


def get_theme_colors(theme_id: str = None):
    theme_id = theme_id or get_current_theme_id()
    return THEMES.get(theme_id, THEMES["blue"]).copy()


def glass_frame_kw(theme_id: str = None):
    """返回用于 CTkFrame 的玻璃风格参数字典。"""
    c = get_theme_colors(theme_id)
    return {
        "fg_color": c["glass"],
        "border_width": 1,
        "border_color": c["glass_border"],
        "corner_radius": 16,
    }


def card_frame_kw(theme_id: str = None):
    c = get_theme_colors(theme_id)
    return {
        "fg_color": c["card"],
        "border_width": 1,
        "border_color": c["glass_border"],
        "corner_radius": 12,
    }

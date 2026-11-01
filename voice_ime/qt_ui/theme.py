# -*- coding: utf-8 -*-
"""Qt 客户端设计 token（对齐 code.html 原型的深色仪表风）。"""
import os
import sys

# ---- 原型 Tailwind 配色 ----
SURFACE = "#111318"
SURFACE_LOWEST = "#0c0e13"
SURFACE_LOW = "#1a1b21"
SURFACE_CONTAINER = "#1e2025"
SURFACE_HIGH = "#282a2f"
SURFACE_HIGHEST = "#33353a"
OUTLINE = "#8c909f"
OUTLINE_VARIANT = "#424754"
TEXT = "#e2e2e9"
TEXT_VARIANT = "#c2c6d6"
PRIMARY = "#adc6ff"
PRIMARY_CONTAINER = "#4d8eff"
SECONDARY = "#b7c8e1"
SECONDARY_CONTAINER = "#3a4a5f"
TERTIARY = "#ffb786"
ERROR = "#ffb4ab"
SUCCESS = SECONDARY

# 兼容旧命名（overlay / tray 仍在使用）
BG_DARK = SURFACE_LOWEST
WINDOW_BG = SURFACE
ACCENT = PRIMARY
BORDER = OUTLINE_VARIANT
MUTED = TEXT_VARIANT

FONT_FAMILY = "Microsoft YaHei UI"
FONT_MONO = "Consolas"

RADIUS_SM = 4
RADIUS = 8
RADIUS_LG = 12
RADIUS_PILL = 28

STATE_CONFIG = {
    "RECORDING": {"text": "", "color": PRIMARY, "w": 180, "h": 56},
    "TRANSCRIBING": {"text": "转写中…", "color": TERTIARY, "w": 180, "h": 56},
    "REFINING": {"text": "纠错中…", "color": SECONDARY, "w": 180, "h": 56},
    "INJECTING": {"text": "写入中…", "color": PRIMARY, "w": 180, "h": 56},
    "PREVIEW": {"text": None, "color": SECONDARY, "w": 380, "h": 80},
    "ERROR": {"text": None, "color": ERROR, "w": 420, "h": 84},
}

WAVE_BAR_COUNT = 17
WAVE_BAR_WIDTH = 3
WAVE_BAR_GAP = 3
WAVE_MIN_HEIGHT = 4
WAVE_MAX_HEIGHT = 32


def asset_path(name):
    """定位 asset；源码运行取 voice_ime/assets，PyInstaller 取 _MEIPASS/assets。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "assets", name)
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", name
    )

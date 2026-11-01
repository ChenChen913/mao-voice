# -*- coding: utf-8 -*-
"""Qt 原型配色与状态配置（与现有 Tk 胶囊保持同一套视觉）。"""

BG_DARK = "#1E1E1E"
WINDOW_BG = "#121417"
SURFACE = "#1B1E23"
BORDER = "#2A2F36"
TEXT = "#E8EAED"
MUTED = "#9AA0A6"
ACCENT = "#4A90D9"
SUCCESS = "#27AE60"
WARNING = "#F39C12"
ERROR = "#E74C3C"

FONT_FAMILY = "Microsoft YaHei UI"

STATE_CONFIG = {
    "RECORDING": {"text": "", "color": ACCENT, "w": 180, "h": 56},
    "TRANSCRIBING": {"text": "✍ 转写中", "color": WARNING, "w": 150, "h": 52},
    "REFINING": {"text": "✨ 润色中", "color": "#9B59B6", "w": 150, "h": 52},
    "INJECTING": {"text": "⬇ 注入中", "color": ACCENT, "w": 150, "h": 52},
    "PREVIEW": {"text": None, "color": SUCCESS, "w": 380, "h": 80},
    "ERROR": {"text": None, "color": ERROR, "w": 380, "h": 80},
}

WAVE_BAR_COUNT = 15
WAVE_BAR_WIDTH = 4
WAVE_BAR_GAP = 4
WAVE_MIN_HEIGHT = 4
WAVE_MAX_HEIGHT = 34

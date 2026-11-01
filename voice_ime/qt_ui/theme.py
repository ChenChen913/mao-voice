# -*- coding: utf-8 -*-
"""Qt 客户端设计 token（深色仪表风 / 浅色主题）。

主题在进程启动时确定（环境变量 MAO_THEME=dark|light），避免运行时切换导致
各处内联样式与新配色不一致；设置页修改主题后提示重启客户端。
"""
import os
import sys

_DARK = {
    "surface": "#111318",
    "lowest": "#0c0e13",
    "low": "#1a1b21",
    "container": "#1e2025",
    "high": "#282a2f",
    "highest": "#33353a",
    "outline": "#8c909f",
    "outline_variant": "#424754",
    "text": "#e2e2e9",
    "text_variant": "#c2c6d6",
    "primary": "#adc6ff",
    "primary_container": "#4d8eff",
    "on_primary": "#002e6a",
    "primary_hover": "#c4d6ff",
    "secondary": "#b7c8e1",
    "secondary_container": "#3a4a5f",
    "tertiary": "#ffb786",
    "on_tertiary": "#3a1a00",
    "tertiary_hover": "#ffd0ad",
    "error": "#ffb4ab",
    "success": "#b7c8e1",
}

_LIGHT = {
    "surface": "#f4f6fb",
    "lowest": "#ffffff",
    "low": "#eef1f7",
    "container": "#e6ebf4",
    "high": "#dbe2ee",
    "highest": "#cfd8e8",
    "outline": "#68717f",
    "outline_variant": "#c4ccd9",
    "text": "#1a1e26",
    "text_variant": "#444c5a",
    "primary": "#2f6fd0",
    "primary_container": "#1f5fb8",
    "on_primary": "#ffffff",
    "primary_hover": "#2559a8",
    "secondary": "#33628a",
    "secondary_container": "#9db6cf",
    "tertiary": "#b35c00",
    "on_tertiary": "#ffffff",
    "tertiary_hover": "#8f4a00",
    "error": "#b3261e",
    "success": "#2f6b4f",
}

MODE = os.environ.get("MAO_THEME", "dark").strip().lower()
if MODE not in ("dark", "light"):
    MODE = "dark"
_P = _LIGHT if MODE == "light" else _DARK

SURFACE = _P["surface"]
SURFACE_LOWEST = _P["lowest"]
SURFACE_LOW = _P["low"]
SURFACE_CONTAINER = _P["container"]
SURFACE_HIGH = _P["high"]
SURFACE_HIGHEST = _P["highest"]
OUTLINE = _P["outline"]
OUTLINE_VARIANT = _P["outline_variant"]
TEXT = _P["text"]
TEXT_VARIANT = _P["text_variant"]
PRIMARY = _P["primary"]
PRIMARY_CONTAINER = _P["primary_container"]
ON_PRIMARY = _P["on_primary"]
PRIMARY_HOVER = _P["primary_hover"]
SECONDARY = _P["secondary"]
SECONDARY_CONTAINER = _P["secondary_container"]
TERTIARY = _P["tertiary"]
ON_TERTIARY = _P["on_tertiary"]
TERTIARY_HOVER = _P["tertiary_hover"]
ERROR = _P["error"]
SUCCESS = _P["success"]

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

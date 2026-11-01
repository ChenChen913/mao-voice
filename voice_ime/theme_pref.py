# -*- coding: utf-8 -*-
"""主题偏好：dark / light / auto（auto 读取 Windows 应用浅色模式）。"""
import sys

LIGHT_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def system_prefers_light():
    """Windows「应用使用浅色模式」为 1 时返回 True；读取失败按深色处理。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, LIGHT_REGISTRY_PATH, 0, winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(value)
    except OSError:
        return False


def resolve(value):
    """把配置里的主题值解析成 dark / light。"""
    value = (value or "").strip().lower()
    if value in ("dark", "light"):
        return value
    return "light" if system_prefers_light() else "dark"

# -*- coding: utf-8 -*-
"""Windows 开机自启：写 HKCU Run，不写系统级注册表、不需要管理员权限。"""
import os
import sys

APP_NAME = "mao-voice"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command():
    """返回开机启动命令：打包版直接启动 exe，源码版优先用 pythonw 避免黑窗。"""
    if getattr(sys, "frozen", False):
        return '"{}"'.format(sys.executable)
    base = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(base, "client_main.py")
    python = sys.executable
    pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
    if os.path.exists(pythonw):
        python = pythonw
    return '"{}" "{}"'.format(python, script)


def is_supported():
    return sys.platform == "win32"


def is_enabled():
    if not is_supported():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
        return bool(value)
    except OSError:
        return False


def set_enabled(enabled):
    """开启/关闭开机自启；返回 (是否成功, 说明)。"""
    if not is_supported():
        return False, "当前系统不支持开机自启设置"
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
                return True, "已设置开机自启"
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            return True, "已关闭开机自启"
    except OSError as e:
        return False, "写入开机启动项失败：{}".format(e)

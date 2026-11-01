# -*- coding: utf-8 -*-
"""按应用模式：识别前台窗口所属程序，匹配用户配置的纠错档位/注入方式。"""
import ctypes
import ctypes.wintypes as wintypes
import logging
import os

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def window_info(hwnd=0):
    """返回 {'hwnd', 'exe', 'class_name', 'title'}；任何一步失败都返回空字段。"""
    hwnd = int(hwnd or 0)
    info = {"hwnd": hwnd, "exe": "", "class_name": "", "title": ""}
    if not hwnd:
        return info
    try:
        buf = ctypes.create_unicode_buffer(512)
        if user32.GetClassNameW(hwnd, buf, 512) > 0:
            info["class_name"] = buf.value
    except Exception:
        logging.debug("读取窗口类名失败", exc_info=True)
    try:
        buf = ctypes.create_unicode_buffer(1024)
        if user32.GetWindowTextW(hwnd, buf, 1024) > 0:
            info["title"] = buf.value
    except Exception:
        logging.debug("读取窗口标题失败", exc_info=True)
    info["exe"] = _process_exe(hwnd)
    return info


def _process_exe(hwnd):
    pid = wintypes.DWORD()
    try:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    except Exception:
        return ""
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value).lower()
    except Exception:
        logging.debug("读取进程路径失败", exc_info=True)
        return ""
    finally:
        kernel32.CloseHandle(handle)


def foreground_info():
    try:
        hwnd = user32.GetForegroundWindow()
    except Exception:
        hwnd = 0
    return window_info(hwnd)


def match_mode(modes_cfg, info):
    """按配置匹配前台应用；返回模式 dict（含 name/level/paste_mode）或 None。"""
    if not modes_cfg or not modes_cfg.get("enabled", True):
        return None
    exe = (info or {}).get("exe", "").lower()
    class_name = (info or {}).get("class_name", "").lower()
    for app in modes_cfg.get("apps") or []:
        if not isinstance(app, dict):
            continue
        want_exe = str(app.get("exe") or "").strip().lower()
        want_class = str(app.get("class") or "").strip().lower()
        if want_exe and (exe == want_exe or exe.endswith(want_exe)):
            return app
        if want_class and want_class in class_name:
            return app
    return None


def mode_override(modes_cfg, info):
    """返回当前应生效的覆盖项（只包含非空字段）。"""
    mode = match_mode(modes_cfg, info)
    if not mode:
        return {}
    override = {}
    for key in ("level", "paste_mode"):
        value = mode.get(key)
        if value not in (None, ""):
            override[key] = value
    if mode.get("name"):
        override["name"] = mode["name"]
    return override

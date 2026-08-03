# -*- coding: utf-8 -*-
"""pytest 公共配置：把 voice_ime 根目录加入 sys.path，便于直接 import 被测模块。"""
import os
import sys

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

import pytest


@pytest.fixture(scope="session")
def tk_app_root():
    """会话级共享 Tk 根窗口。

    v5.15：UI 相关测试共用同一个 Tk 根，避免"创建-销毁-再创建"引发
    `tcl_findLibrary` 类错误（GitHub Actions Windows 环境下必现）。
    """
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("无可用显示环境")
        return None
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass

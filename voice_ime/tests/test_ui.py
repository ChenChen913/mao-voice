# -*- coding: utf-8 -*-
"""悬浮窗波形绘制单元测试。

说明（D3）：真实 Tk 绘制用例在无显示环境下由 conftest 的 tk_app_root fixture
自动跳过——该缺口已被接受（见修复 SPEC D3）；本文件另含不依赖 Tk 的静态用例。
"""
import tkinter as tk

import pytest

from ui import Overlay, WAVE_BAR_COUNT


@pytest.fixture()
def overlay(tk_app_root):
    ov = Overlay(tk_app_root)
    ov.show("RECORDING")
    for _ in range(5):
        tk_app_root.update()
    yield ov
    try:
        ov.hide()
        tk_app_root.withdraw()
    except tk.TclError:
        pass


def test_silent_static_wave_and_speaking_animated(overlay):
    w, h = overlay._root.winfo_width(), overlay._root.winfo_height()
    overlay.set_speaking(False)
    overlay._tick_recording(w, h)
    boxes1 = [overlay._canvas.bbox(i) for i in overlay._canvas.find_all()[1:]]
    assert len(boxes1) == WAVE_BAR_COUNT
    overlay._tick_recording(w, h)
    boxes2 = [overlay._canvas.bbox(i) for i in overlay._canvas.find_all()[1:]]
    assert boxes1 == boxes2  # 静音完全静止

    overlay.set_speaking(True)
    overlay.set_levels([0.1, 0.3, 0.6, 0.9, 0.7, 0.4, 0.2] * 3)
    overlay._rms = 0.5
    overlay._tick_recording(w, h)
    s1 = [overlay._canvas.bbox(i) for i in overlay._canvas.find_all()[1:]]
    overlay._tick_recording(w, h)
    s2 = [overlay._canvas.bbox(i) for i in overlay._canvas.find_all()[1:]]
    assert s1 != s2  # 说话逐帧变化（律动）


def test_no_text_items_in_recording(overlay):
    w, h = overlay._root.winfo_width(), overlay._root.winfo_height()
    overlay.set_speaking(False)
    overlay._tick_recording(w, h)
    for item in overlay._canvas.find_all():
        assert overlay._canvas.type(item) == "polygon"


def test_unknown_state_does_not_crash(overlay):
    """m2：未知状态回退默认样式，不再抛 KeyError。"""
    overlay._show_impl("BOGUS_STATE", "x")
    assert overlay._active is True


def test_max_chars_config_used(tk_app_root):
    """C7：ui.max_chars 控制错误/预览文本截断长度。"""
    ov = Overlay(tk_app_root, max_chars=12)
    ov.show("ERROR", "这是一段很长的错误提示文本，应该被截断")
    for _ in range(5):
        tk_app_root.update()
    texts = [
        ov._canvas.itemcget(i, "text")
        for i in ov._canvas.find_all()
        if ov._canvas.type(i) == "text"
    ]
    assert texts, "应绘制出文本"
    assert any(t.endswith("…") and len(t) <= 13 for t in texts)


def test_state_config_has_required_keys():
    """D3：不依赖 Tk 的静态用例——所有状态配置都包含必需键。"""
    from ui import STATE_CONFIG

    for state, cfg in STATE_CONFIG.items():
        assert {"text", "color", "w", "h"} <= set(cfg), "状态 {} 缺少必需键".format(state)

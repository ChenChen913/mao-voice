# -*- coding: utf-8 -*-
"""安全注入单元测试：只测无副作用路径（真实注入需要人工目标窗口）。"""
import safe_inject


def test_empty_text_guard():
    ok, msg = safe_inject.inject("")
    assert ok is False
    assert "为空" in msg

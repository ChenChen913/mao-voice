# -*- coding: utf-8 -*-
"""doctor 配置校验单元测试。"""
import doctor


def test_combo_hotkey_rejected(monkeypatch):
    monkeypatch.setattr(doctor, "_load_config", lambda: ({"hotkey": "ctrl+alt+x"}, None))
    name, ok, detail = doctor._check_config()
    assert ok is False
    assert "仅支持单键" in detail


def test_single_hotkey_accepted(monkeypatch):
    monkeypatch.setattr(doctor, "_load_config", lambda: ({"hotkey": "f9"}, None))
    name, ok, detail = doctor._check_config()
    assert ok is True

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


def test_invalid_settings_hotkey_rejected(monkeypatch):
    """B6：设置热键为未知键名时 doctor 应报错，而不是全绿。"""
    monkeypatch.setattr(
        doctor, "_load_config",
        lambda: ({"hotkey": "f9", "settings_hotkey": "bogus"}, None),
    )
    name, ok, detail = doctor._check_config()
    assert ok is False
    assert "settings_hotkey" in detail
    assert "未知键名" in detail


def test_empty_optional_hotkey_allowed(monkeypatch):
    """B6：settings/refine 热键为空串表示禁用，应放行。"""
    monkeypatch.setattr(
        doctor, "_load_config",
        lambda: ({"hotkey": "f9", "settings_hotkey": "", "refine_cycle_hotkey": ""}, None),
    )
    name, ok, detail = doctor._check_config()
    assert ok is True


def test_api_key_from_env(monkeypatch):
    """N-m3：配置文件为空时 DEEPSEEK_API_KEY 环境变量应判通过。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    monkeypatch.setattr(
        doctor, "_load_config",
        lambda: ({"refine": {"api_key": ""}, "asr": {"cloud": {}}}, None),
    )
    name, ok, detail = doctor._check_api_key()
    assert ok is True
    assert "DEEPSEEK_API_KEY" in detail


def test_api_key_from_config(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        doctor, "_load_config",
        lambda: ({"refine": {"api_key": "sk-x"}, "asr": {"cloud": {}}}, None),
    )
    name, ok, detail = doctor._check_api_key()
    assert ok is True


def test_api_key_missing(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        doctor, "_load_config",
        lambda: ({"refine": {"api_key": ""}, "asr": {"cloud": {}}}, None),
    )
    name, ok, detail = doctor._check_api_key()
    assert ok is False

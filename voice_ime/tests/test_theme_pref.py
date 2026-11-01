# -*- coding: utf-8 -*-
"""主题偏好与配色切换测试。"""
import importlib

import pytest

import theme_pref


def test_resolve_explicit_values(monkeypatch):
    monkeypatch.setattr(theme_pref, "system_prefers_light", lambda: False)
    assert theme_pref.resolve("light") == "light"
    assert theme_pref.resolve("dark") == "dark"


def test_resolve_auto_uses_system(monkeypatch):
    monkeypatch.setattr(theme_pref, "system_prefers_light", lambda: True)
    assert theme_pref.resolve("auto") == "light"
    monkeypatch.setattr(theme_pref, "system_prefers_light", lambda: False)
    assert theme_pref.resolve("") == "dark"


def test_theme_palette_switches(monkeypatch):
    pytest.importorskip("PySide6")
    import qt_ui.theme as theme

    monkeypatch.setenv("MAO_THEME", "light")
    importlib.reload(theme)
    assert theme.SURFACE == "#f4f6fb"
    assert theme.ON_PRIMARY == "#ffffff"

    monkeypatch.delenv("MAO_THEME", raising=False)
    importlib.reload(theme)
    assert theme.SURFACE == "#111318"
    assert theme.ON_PRIMARY == "#002e6a"

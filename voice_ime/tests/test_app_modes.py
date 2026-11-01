# -*- coding: utf-8 -*-
"""按应用模式匹配测试。"""
import app_modes


def test_match_by_exe_case_insensitive():
    cfg = {
        "enabled": True,
        "apps": [
            {"exe": "code.exe", "name": "VS Code", "level": "light"},
            {"exe": "windowsterminal.exe", "name": "终端", "paste_mode": "unicode"},
        ],
    }
    info = {"exe": "code.exe", "class_name": "", "title": ""}
    assert app_modes.match_mode(cfg, info)["name"] == "VS Code"
    assert app_modes.mode_override(cfg, info) == {"level": "light", "name": "VS Code"}


def test_match_by_window_class():
    cfg = {"enabled": True, "apps": [{"class": "CASCADIA", "name": "终端"}]}
    info = {"exe": "", "class_name": "CASCADIA_HOSTING_WINDOW_CLASS"}
    assert app_modes.match_mode(cfg, info)["name"] == "终端"


def test_disabled_and_unmatched_return_none():
    cfg = {"enabled": False, "apps": [{"exe": "code.exe", "name": "VS Code"}]}
    info = {"exe": "code.exe", "class_name": ""}
    assert app_modes.match_mode(cfg, info) is None
    assert app_modes.mode_override(cfg, info) == {}

    cfg["enabled"] = True
    assert app_modes.match_mode(cfg, {"exe": "chrome.exe", "class_name": ""}) is None
    assert app_modes.mode_override(None, info) == {}


def test_override_ignores_empty_values():
    cfg = {"enabled": True, "apps": [{
        "exe": "code.exe", "name": "", "level": "", "paste_mode": "ctrl_v",
    }]}
    assert app_modes.mode_override(cfg, {"exe": "code.exe"}) == {"paste_mode": "ctrl_v"}

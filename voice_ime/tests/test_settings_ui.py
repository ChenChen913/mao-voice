# -*- coding: utf-8 -*-
"""托盘图标与设置窗口单元测试（需要 Tk，无显示环境则跳过）。"""

import config
import settings_ui
from history import HistoryStore
from settings_ui import SettingsWindow, make_tray_image


class FakeApp:
    def __init__(self, cfg, history):
        self.cfg = cfg
        self.history = history
        self.saved = False

    def save_cfg(self):
        self.saved = True


def test_make_tray_image():
    img = make_tray_image()
    assert img.size == (64, 64)


def test_pick_download_model():
    """C8：下载模型跟随当前配置（small/medium/未知）。"""
    assert settings_ui.pick_download_model("small") == "small"
    assert settings_ui.pick_download_model("models/faster-whisper-medium") == "medium"
    assert settings_ui.pick_download_model("") == "medium"
    assert settings_ui.pick_download_model("C:/models/faster-whisper-small") == "small"


def test_settings_window_tabs_and_save(tmp_path, monkeypatch, tk_app_root):
    monkeypatch.setattr(settings_ui.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(settings_ui.messagebox, "showerror", lambda *a, **k: None)

    cfg = config.load_config(str(tmp_path / "c.json"))
    app = FakeApp(cfg, HistoryStore(str(tmp_path / "h.json")))
    win = SettingsWindow(app, parent=tk_app_root)
    win.root.update()

    assert win.var_hotkey.get() == "alt_r"
    win.var_hotkey.set("f9")
    win.var_cycle.set("f10")
    win.var_settings_hk.set("f11")
    win.save()
    assert app.saved is True
    assert cfg["hotkey"] == "f9"
    assert cfg["refine_cycle_hotkey"] == "f10"
    assert cfg["settings_hotkey"] == "f11"

    win.root.destroy()


def test_settings_window_rejects_duplicate_hotkeys(tmp_path, monkeypatch, tk_app_root):
    """M6：三个热键重复时拒绝保存。"""
    errors = []
    monkeypatch.setattr(settings_ui.messagebox, "showerror", lambda *a, **k: errors.append(a))

    cfg = config.load_config(str(tmp_path / "c.json"))
    app = FakeApp(cfg, HistoryStore(str(tmp_path / "h.json")))
    win = SettingsWindow(app, parent=tk_app_root)
    win.root.update()

    win.var_hotkey.set("f9")
    win.var_cycle.set("f9")
    win.var_settings_hk.set("f8")
    win.save()

    assert errors, "应弹出错误提示"
    assert app.saved is False, "重复热键不应保存"
    win.root.destroy()

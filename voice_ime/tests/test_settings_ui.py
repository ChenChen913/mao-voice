# -*- coding: utf-8 -*-
"""托盘图标与设置窗口单元测试（需要 Tk，无显示环境则跳过）。"""
import tkinter as tk

import pytest

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


def test_settings_window_tabs_and_save(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("无可用显示环境")
    root.withdraw()
    monkeypatch.setattr(settings_ui.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(settings_ui.messagebox, "showerror", lambda *a, **k: None)

    cfg = config.load_config(str(tmp_path / "c.json"))
    app = FakeApp(cfg, HistoryStore(str(tmp_path / "h.json")))
    win = SettingsWindow(app, parent=root)
    win.root.update()

    assert win.var_hotkey.get() == "alt_r"
    win.var_hotkey.set("f9")
    win.save()
    assert app.saved is True
    assert cfg["hotkey"] == "f9"

    win.root.destroy()
    root.destroy()

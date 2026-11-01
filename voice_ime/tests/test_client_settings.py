# -*- coding: utf-8 -*-
"""客户端设置应用逻辑测试（不需要 QApplication，不写真实 config.json）。"""
import json

import pytest

pytest.importorskip("PySide6")

import config  # noqa: E402
import main  # noqa: E402
import qt_ui.client_app as client_app  # noqa: E402


class _Overlay:
    def show(self, *a, **k):
        pass

    def hide(self):
        pass

    def set_level(self, *a):
        pass

    def set_speaking(self, *a):
        pass

    def set_levels(self, *a):
        pass


class _Root:
    def after(self, *a):
        pass

    def quit(self):
        pass


class _Reloadable:
    def __init__(self):
        self.reloads = 0

    def reload(self):
        self.reloads += 1

    def refresh_stats(self):
        self.reloads += 1


class _Window:
    def __init__(self):
        self.refreshed = 0
        self.history_page = _Reloadable()
        self.home = _Reloadable()

    def set_status(self, *a):
        pass

    def refresh_data(self, cfg=None):
        self.refreshed += 1


def _make_client(tmp_path, monkeypatch):
    cfg = config.load_config(str(tmp_path / "config.json"))
    app = client_app.ClientApp(cfg, _Overlay(), _Root(), _Window())
    app.history = None
    app.learn = None
    written = {}

    def fake_save(data, path=None):
        written["data"] = json.loads(json.dumps(data))

    monkeypatch.setattr(client_app, "save_config", fake_save)
    return app, written


def test_apply_settings_persists_and_enables_history(tmp_path, monkeypatch):
    app, written = _make_client(tmp_path, monkeypatch)

    ok, msg = app.apply_settings({
        "refine": {"level": "light"},
        "history": {"enabled": True},
        "learn": {"enabled": True},
    })

    assert ok is True
    assert app.cfg["refine"]["level"] == "light"
    assert app.history is not None
    assert app.learn is not None
    assert written["data"]["refine"]["level"] == "light"
    assert app.window.refreshed >= 1
    assert "已保存" in msg


def test_apply_settings_turns_history_off(tmp_path, monkeypatch):
    app, _ = _make_client(tmp_path, monkeypatch)
    app.apply_settings({"history": {"enabled": True}, "learn": {"enabled": True}})

    ok, _ = app.apply_settings({"history": {"enabled": False}, "learn": {"enabled": False}})

    assert ok is True
    assert app.history is None
    assert app.learn is None


def test_delete_and_clear_history(tmp_path, monkeypatch):
    from history import HistoryStore, read_entries

    app, _ = _make_client(tmp_path, monkeypatch)
    path = tmp_path / "history.json"
    app.history = HistoryStore(path=str(path))
    app.history.add("原始", "结果", duration_s=1)
    entry = app.history.items()[0]

    app.delete_history(entry)
    assert app.history.items() == []
    assert read_entries(str(path)) == []
    assert app.window.history_page.reloads >= 1
    assert app.window.home.reloads >= 1

    app.history.add("原始2", "结果2")
    app.clear_history()
    assert app.history.items() == []
    assert read_entries(str(path)) == []


def test_reload_dictionary_calls_engine():
    class _Engine:
        def __init__(self):
            self.calls = 0

        def reload_glossary(self):
            self.calls += 1

    app = client_app.ClientApp.__new__(client_app.ClientApp)
    primary = _Engine()
    app.asr = type("Wrapper", (), {"primary": primary})()
    app.reload_dictionary()
    assert primary.calls == 1

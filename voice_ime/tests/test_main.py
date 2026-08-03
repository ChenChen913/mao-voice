# -*- coding: utf-8 -*-
"""主程序 App 逻辑单元测试（用假 overlay/root，不启动 Tk）。"""
import config
import main


class FakeOverlay:
    def __init__(self):
        self.calls = []

    def show(self, state, text=""):
        self.calls.append(("show", state, text))

    def hide(self):
        self.calls.append(("hide",))

    def set_level(self, v):
        pass

    def set_speaking(self, v):
        pass

    def set_levels(self, v):
        pass


class FakeRoot:
    def __init__(self):
        self.after_calls = []

    def after(self, ms, fn):
        self.after_calls.append((ms, fn))
        return len(self.after_calls)


def _make_app(tmp_path):
    cfg = config.load_config(str(tmp_path / "c.json"))
    return main.App(cfg, FakeOverlay(), FakeRoot())


def test_cycle_refine_levels(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(main, "save_config", lambda cfg: saved.append(dict(cfg)))
    app = _make_app(tmp_path)
    assert app.cfg["refine"]["level"] == "conservative"

    app.on_cycle_refine()
    assert app.cfg["refine"]["level"] == "light"
    app.on_cycle_refine()
    assert app.cfg["refine"]["level"] == "polish"
    app.on_cycle_refine()
    assert app.cfg["refine"]["level"] == "conservative"
    assert len(saved) == 3

    kind, payload = app._ui_queue.get_nowait()
    assert kind == "toast"
    assert "润色强度" in payload[0]


def test_invalid_level_recovers(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "save_config", lambda cfg: None)
    app = _make_app(tmp_path)
    app.cfg["refine"]["level"] = "bogus"
    app.on_cycle_refine()
    assert app.cfg["refine"]["level"] == "light"

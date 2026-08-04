# -*- coding: utf-8 -*-
"""主程序 App 逻辑单元测试（用假 overlay/root，不启动 Tk）。"""
import numpy as np

import config
import cloud_asr
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


class FakeRecorder:
    def __init__(self, duration=1.0):
        self.duration = duration
        self.active = True
        self.stopped = False
        self.vad = None

    def stop(self):
        self.stopped = True
        return np.zeros(1600, dtype=np.float32)


class FakeRefiner:
    enabled = False


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


def test_make_asr_cloud_key_from_env(tmp_path, monkeypatch):
    """M3：云端 ASR key 统一走 resolve_keys，环境变量生效且不写回配置。"""
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    created = {}

    class FakeCloud:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setattr(cloud_asr, "CloudASREngine", FakeCloud)
    cfg = config.load_config(str(tmp_path / "c.json"))
    cfg["asr"]["engine"] = "cloud"
    cfg["asr"]["cloud"] = {"base_url": "https://x/v1", "api_key": "", "model": "whisper-1"}
    engine = main.make_asr(cfg)
    assert isinstance(engine, FakeCloud)
    assert created["api_key"] == "sk-env"
    assert cfg["asr"]["cloud"]["api_key"] == ""


def test_process_releases_recorder_and_idle(tmp_path, monkeypatch):
    """B4：处理结束后 self.recorder 置 None（释放全程音频），状态回到 IDLE。"""
    app = _make_app(tmp_path)
    recorder = FakeRecorder(duration=1.0)
    app.recorder = recorder
    app.state = "RECORDING"
    app._target_hwnd = 12345
    app.history = None
    app.asr.transcribe = lambda audio: "测试文本"
    app.refiner = FakeRefiner()
    inject_calls = []
    monkeypatch.setattr(
        main.safe_inject, "inject",
        lambda *a, **k: inject_calls.append(k) or (True, "ok"),
    )
    monkeypatch.setattr(main.time, "sleep", lambda s: None)  # 去掉状态提示等待

    app._process()

    assert recorder.stopped is True
    assert app.recorder is None
    assert app.state == "IDLE"
    # B7：把录制结束时的前台窗口句柄传给注入模块
    assert inject_calls[0]["expected_hwnd"] == 12345
    assert inject_calls[0]["require_same_focus"] is True


def test_max_duration_triggers_finish(tmp_path, monkeypatch):
    """B4：录音时长达到 max_duration_sec 时自动结束。"""
    app = _make_app(tmp_path)
    app.cfg["recorder"]["max_duration_sec"] = 300
    app.recorder = FakeRecorder(duration=999.0)
    app.state = "RECORDING"
    calls = []
    monkeypatch.setattr(main.App, "_finish_recording", lambda self: calls.append(1))

    app._poll_recording()

    assert calls == [1]

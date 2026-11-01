# -*- coding: utf-8 -*-
"""管线集成测试：录音结束 → ASR → 润色 → 注入 → 历史/学习沉淀的完整接线。

与 test_main.py 的状态机单测互补：这里把整条 _process 链路串起来跑，
断言「注入的是什么文本、顺序是什么、失败时还会不会写历史」。
"""
import numpy as np

import config
import main


class FakeOverlay:
    def show(self, state, text=""):
        pass

    def hide(self):
        pass

    def set_level(self, v):
        pass

    def set_speaking(self, v):
        pass

    def set_levels(self, v):
        pass


class FakeRoot:
    def after(self, ms, fn):
        return 1


class FakeRecorder:
    def __init__(self, duration=2.0):
        self.duration = duration
        self.active = True
        self.vad = None

    def stop(self):
        self.active = False
        return np.zeros(1600, dtype=np.float32)


class FakeRefiner:
    def __init__(self, enabled=True, result=None, error=None):
        self.enabled = enabled
        self.result = result
        self.error = error
        self.calls = []

    def refine(self, raw, level=None, words_block=""):
        self.calls.append((raw, level, words_block))
        if self.error:
            raise self.error
        return self.result if self.result is not None else raw


def _states(app):
    """取出 _ui_queue 里所有状态推送的 (state, text)。"""
    return [p[1] for p in list(app._ui_queue.queue) if p[0] == "state"]


def _make_app(tmp_path):
    cfg = config.load_config(str(tmp_path / "c.json"))
    app = main.App(cfg, FakeOverlay(), FakeRoot())
    app.history = None
    app.learn = None
    app.recorder = FakeRecorder()
    app.state = "RECORDING"
    app._target_hwnd = 0
    return app


def test_pipeline_injects_refined_text_in_order(tmp_path, monkeypatch):
    """成功链路：注入润色结果，状态依次 TRANSCRIBING→REFINING→INJECTING→IDLE。"""
    app = _make_app(tmp_path)
    app.asr.transcribe = lambda audio: "  原始转写  "
    app.refiner = FakeRefiner(result="润色后文本")
    injected = []
    monkeypatch.setattr(
        main.safe_inject, "inject",
        lambda text, **kwargs: injected.append(text) or (True, "注入成功，剪贴板已恢复"),
    )
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    app._process()

    assert injected == ["润色后文本"]
    seq = [s[0] for s in _states(app)]
    assert seq == ["TRANSCRIBING", "REFINING", "INJECTING", "IDLE"]
    assert app.state == "IDLE"
    assert app.recorder is None


def test_pipeline_writes_history_and_learn_only_on_success(tmp_path, monkeypatch):
    """历史与学习只在注入成功时写入，且拿到的是 (原始转写, 润色结果, 时长)。"""
    app = _make_app(tmp_path)
    app.asr.transcribe = lambda audio: "配森脚本"
    app.refiner = FakeRefiner(result="Python 脚本")
    hist, learned = [], []

    class FakeHistory:
        def add(self, raw, final, duration_s=None, app=None):
            hist.append((raw, final, duration_s))

    class FakeLearn:
        def add(self, raw, final):
            learned.append((raw, final))

    app.history = FakeHistory()
    app.learn = FakeLearn()
    monkeypatch.setattr(
        main.safe_inject, "inject", lambda text, **kwargs: (True, "注入成功")
    )
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    app._process()

    assert hist == [("配森脚本", "Python 脚本", 2.0)]
    assert learned == [("配森脚本", "Python 脚本")]


def test_pipeline_injection_failure_skips_history(tmp_path, monkeypatch):
    """注入失败（如 UIPI 拦截）：报错、不写历史/学习、状态仍回 IDLE。"""
    app = _make_app(tmp_path)
    app.asr.transcribe = lambda audio: "原始"
    app.refiner = FakeRefiner(enabled=True, result="原始")  # 避开「未配置 Key」提示干扰
    hist, learned = [], []

    class FakeHistory:
        def add(self, *a, **k):
            hist.append(a)

    class FakeLearn:
        def add(self, *a, **k):
            learned.append(a)

    app.history = FakeHistory()
    app.learn = FakeLearn()
    monkeypatch.setattr(
        main.safe_inject, "inject",
        lambda text, **kwargs: (False, "UIPI 拦截：目标窗口以管理员权限运行"),
    )
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    app._process()

    errors = [s for s in _states(app) if s[0] == "ERROR"]
    assert any("注入失败" in text for _, text in errors)
    assert hist == [] and learned == []
    assert app.state == "IDLE"


def test_pipeline_refine_error_falls_back_to_raw(tmp_path, monkeypatch):
    """润色异常：提示后仍注入原始转写，不让用户白说一段话。"""
    app = _make_app(tmp_path)
    app.asr.transcribe = lambda audio: "原始转写"
    app.refiner = FakeRefiner(error=RuntimeError("HTTP 401"))
    injected = []
    monkeypatch.setattr(
        main.safe_inject, "inject",
        lambda text, **kwargs: injected.append(text) or (True, "注入成功"),
    )
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    app._process()

    assert injected == ["原始转写"]
    errors = [s for s in _states(app) if s[0] == "ERROR"]
    assert errors and "润色失败" in errors[0][1]

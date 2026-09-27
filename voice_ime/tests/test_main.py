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


class _FakeThread:
    """捕获 target 但不真正启动的假线程（用于状态机测试）。"""

    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon

    def start(self):
        pass


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
    monkeypatch.setattr(
        main.App, "_finish_recording",
        lambda self, reason=None: calls.append(reason),
    )

    app._poll_recording()

    assert calls == ["max_duration"]


def test_finish_recording_max_duration_toast(tmp_path, monkeypatch):
    """N-m6：max_duration 自动结束时发 toast 提示，且状态机照常进入 PROCESSING。"""
    app = _make_app(tmp_path)
    app.recorder = FakeRecorder(duration=1.0)
    app.state = "RECORDING"
    started = []
    monkeypatch.setattr(
        main.threading, "Thread",
        lambda target, daemon=False: started.append(target) or _FakeThread(target, daemon),
    )

    app._finish_recording(reason="max_duration")

    kinds = [item[0] for item in list(app._ui_queue.queue)]
    assert "toast" in kinds
    assert app.state == "PROCESSING"


def test_poll_recording_survives_recorder_none(tmp_path):
    """N-M1：recorder 为 None 时轮询不崩溃，且继续调度下一次。"""
    app = _make_app(tmp_path)
    app.recorder = None
    app.state = "RECORDING"

    app._poll_recording()  # 不应抛 AttributeError

    assert len(app.root.after_calls) == 1


def test_poll_recording_bad_numeric_config_does_not_crash(tmp_path):
    """B2：手改 recorder 数值配置为非数字时，轮询不崩溃且继续调度。"""
    app = _make_app(tmp_path)
    app.recorder = FakeRecorder(duration=1.0)
    app.state = "RECORDING"
    app.cfg["recorder"]["auto_stop_silence_sec"] = "abc"
    app.cfg["recorder"]["max_duration_sec"] = "abc"

    app._poll_recording()  # 不应抛 TypeError

    assert len(app.root.after_calls) == 1


def test_show_toast_bad_preview_sec_falls_back(tmp_path):
    """B2：ui.preview_sec 为非数字时回退默认 1.5s。"""
    app = _make_app(tmp_path)
    app.cfg["ui"]["preview_sec"] = "abc"
    app._show_toast("x")
    kind, payload = app._ui_queue.get_nowait()
    assert kind == "toast"
    assert payload[1] == 1.5


def test_show_toast_uses_preview_sec(tmp_path):
    """C7：ui.preview_sec 已接线到 toast 时长，不再是死配置。"""
    app = _make_app(tmp_path)
    app.cfg["ui"]["preview_sec"] = 2.5
    app._show_toast("x")
    kind, payload = app._ui_queue.get_nowait()
    assert kind == "toast"
    assert payload[1] == 2.5


def test_finish_recording_starts_single_worker(tmp_path, monkeypatch):
    """D2：重复调用 _finish_recording 只启动一个 worker（状态机防重复）。"""
    app = _make_app(tmp_path)
    app.recorder = FakeRecorder(duration=1.0)
    app.state = "RECORDING"
    started = []
    monkeypatch.setattr(
        main.threading, "Thread",
        lambda target, daemon=False: started.append(target) or _FakeThread(target, daemon),
    )

    app._finish_recording()
    app._finish_recording()

    assert len(started) == 1
    assert app.state == "PROCESSING"


# ==================== v5.18：草稿预热收敛 / 无 Key 单次提示 / 学习沉淀 ====================

def test_on_draft_warmup_limit(tmp_path):
    """v5.18：草稿转写仅预热前 warmup_drafts 个分块，后续分块直接跳过。"""
    app = _make_app(tmp_path)
    app.state = "RECORDING"
    calls = []
    app.asr.transcribe = lambda audio: calls.append(len(audio)) or "x"

    app._on_draft(b"1")
    app._on_draft(b"2")
    app._on_draft(b"3")
    assert len(calls) == 1, "warmup_drafts 默认 1：只应转写首个分块"

    # 0 = 关闭预热
    app2 = _make_app(tmp_path)
    app2.state = "RECORDING"
    app2.cfg["recorder"]["warmup_drafts"] = 0
    calls2 = []
    app2.asr.transcribe = lambda audio: calls2.append(audio) or "x"
    app2._on_draft(b"1")
    assert calls2 == []


def test_on_draft_resets_each_recording(tmp_path):
    """每次新录音（_start_recording）重置预热计数。"""
    app = _make_app(tmp_path)
    app.state = "RECORDING"
    calls = []
    app.asr.transcribe = lambda audio: calls.append(audio) or "x"
    app._on_draft(b"1")
    app._on_draft(b"2")
    assert len(calls) == 1
    app._draft_count = 0  # 模拟 _start_recording 的重置
    app._on_draft(b"3")
    assert len(calls) == 2


def test_no_key_notice_shown_once(tmp_path, monkeypatch):
    """v5.18：未配置 Key 的降级提示只弹一次 ERROR，之后只留控制台日志。"""
    app = _make_app(tmp_path)
    app.recorder = FakeRecorder(duration=1.0)
    app.state = "RECORDING"
    app.history = None
    app.refiner = FakeRefiner()  # enabled=False
    app.asr.transcribe = lambda audio: "原始文本"
    monkeypatch.setattr(
        main.safe_inject, "inject", lambda *a, **k: (True, "ok")
    )
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    app._process()
    # 第二轮：模拟真实流程重新创建 recorder（上一轮 finally 已将其置 None）
    app.recorder = FakeRecorder(duration=1.0)
    app.state = "RECORDING"
    app._process()

    # _post 走 _ui_queue（测试里没有 poll_ui 消费），直接数队列里的 ERROR 状态
    states = [p[1][0] for p in list(app._ui_queue.queue) if p[0] == "state"]
    errors = [s for s in states if s == "ERROR"]
    assert len(errors) == 1, "无 Key 提示只应弹一次，实际 {}".format(len(errors))


def test_learn_rules_accumulate_on_success(tmp_path, monkeypatch):
    """v5.18：注入成功且润色有改动时，(raw, final) 沉淀进学习规则库。"""
    app = _make_app(tmp_path)
    app.recorder = FakeRecorder(duration=1.0)
    app.state = "RECORDING"
    app.history = None
    added = []

    class FakeLearn:
        def add(self, raw, final):
            added.append((raw, final))

        def build_block(self):
            return ""

    app.learn = FakeLearn()
    app.refiner = FakeRefiner()
    app.refiner.enabled = True
    app.refiner.refine = lambda raw, words_block="": raw + "！"
    app.asr.transcribe = lambda audio: "你好"
    monkeypatch.setattr(
        main.safe_inject, "inject", lambda *a, **k: (True, "ok")
    )
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    app._process()

    assert added == [("你好", "你好！")]


def test_learn_block_merged_into_words_block(tmp_path, monkeypatch):
    """v5.18：学习规则块拼进 build_words_block 的结果一起传给润色。"""
    app = _make_app(tmp_path)
    app.recorder = FakeRecorder(duration=1.0)
    app.state = "RECORDING"
    app.history = None

    class FakeLearn:
        def build_block(self):
            return "- 配森 → Python"

    app.learn = FakeLearn()
    seen = {}
    app.refiner = FakeRefiner()
    app.refiner.enabled = True
    app.refiner.refine = lambda raw, words_block="": seen.update(words_block=words_block) or raw
    app.asr.transcribe = lambda audio: "你好"
    monkeypatch.setattr(
        main.safe_inject, "inject", lambda *a, **k: (True, "ok")
    )
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    monkeypatch.setattr(main, "build_words_block", lambda: "（无）")

    app._process()

    assert "配森 → Python" in seen["words_block"]

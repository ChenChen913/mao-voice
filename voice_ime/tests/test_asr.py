"""ASR 引擎单元测试：聚焦并发推理串行化（C1），不加载真实模型。"""
import threading
import time

import numpy as np

from asr import FallbackASR, WhisperEngine



def test_transcribe_serialized_with_infer_lock(monkeypatch):
    """多个线程并发 transcribe 时，_transcribe_once 必须串行执行（最大并发数=1）。"""
    engine = WhisperEngine(model="small")
    monkeypatch.setattr(engine, "_load", lambda: None)  # 不加载真实模型

    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_transcribe_once(audio, use_vad):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return "结果"

    monkeypatch.setattr(engine, "_transcribe_once", fake_transcribe_once)

    errors = []

    def worker():
        try:
            assert engine.transcribe(np.zeros(1600, dtype=np.float32)) == "结果"
        except Exception as e:  # noqa: BLE001 - 测试线程汇总异常
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, errors
    assert max_active == 1, "并发 transcribe 未串行化，max_active={}".format(max_active)


# ==================== FallbackASR（v5.18 云端自动兜底） ====================

class FakeEngine:
    """可控假引擎：记录调用并按脚本决定成功/失败。"""

    def __init__(self, name, fail_times=0):
        self.name = name
        self.fail_times = fail_times
        self.calls = 0
        self.warmed = False

    def transcribe(self, audio):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("{} 失败 #{}".format(self.name, self.calls))
        return "{} 结果".format(self.name)

    def warmup(self):
        self.warmed = True


def _make_fallback(fail_times=0):
    primary = FakeEngine("local", fail_times=fail_times)
    secondary = FakeEngine("cloud")
    return primary, secondary, FallbackASR(primary, secondary, fail_threshold=2)


def test_fallback_primary_success_never_switches():
    primary, secondary, fb = _make_fallback()
    assert fb.transcribe(b"x") == "local 结果"
    assert primary.calls == 1 and secondary.calls == 0
    assert fb.active_engine == "local"


def test_fallback_below_threshold_raises_and_stays_local():
    primary, secondary, fb = _make_fallback(fail_times=1)
    try:
        fb.transcribe(b"x")
        raise AssertionError("低于阈值时应向上抛出本地错误")
    except RuntimeError as e:
        assert "local" in str(e)
    assert secondary.calls == 0
    assert fb.active_engine == "local"


def test_fallback_switches_after_threshold_and_sticky():
    primary, secondary, fb = _make_fallback(fail_times=2)  # 本地前 2 次调用都失败
    # 第 1 次失败：未达阈值（2），向上抛出且不切换
    try:
        fb.transcribe(b"x")
        raise AssertionError("第 1 次失败不应触发切换")
    except RuntimeError:
        pass
    assert fb.active_engine == "local"
    # 第 2 次失败：达到阈值 → 本次起切换云端
    assert fb.transcribe(b"y") == "cloud 结果"
    assert fb.active_engine == "cloud"
    # 粘滞：之后即使"本地恢复健康"（primary 已不再失败），也继续走云端
    assert fb.transcribe(b"z") == "cloud 结果"
    assert primary.calls == 2 and secondary.calls == 2


def test_fallback_success_resets_failure_counter():
    primary = FakeEngine("local")
    fails = {"n": 0}

    def flaky(audio):
        fails["n"] += 1
        if fails["n"] == 1:
            raise RuntimeError("偶发失败")
        return "local 结果"

    primary.transcribe = flaky
    secondary = FakeEngine("cloud")
    fb = FallbackASR(primary, secondary, fail_threshold=2)
    try:
        fb.transcribe(b"x")
        raise AssertionError("第一次偶发失败应上抛")
    except RuntimeError:
        pass
    assert fb.transcribe(b"y") == "local 结果", "失败计数应在成功后清零，不触发兜底"
    assert secondary.calls == 0


def test_fallback_warmup_only_primary():
    primary, secondary, fb = _make_fallback()
    fb.warmup()
    assert primary.warmed and not secondary.warmed

# -*- coding: utf-8 -*-
"""VAD 状态机单元测试。"""
import numpy as np

from vad import VAD


def frame(amp, ms=20):
    return np.full(int(16000 * ms / 1000), amp, dtype=np.float32)


def test_silence_stays_silent():
    v = VAD()
    for _ in range(30):
        v.process(frame(0.0))
    assert not v.is_speaking()
    assert v.silence_seconds() == 0.0


def test_speech_onset_requires_debounce():
    v = VAD()
    v.process(frame(0.0, 100))
    v.process(frame(0.2, 100))  # 累计 100ms < 120ms 阈值
    assert not v.is_speaking()
    v.process(frame(0.2, 50))   # 累计 150ms ≥ 120ms
    assert v.is_speaking()


def test_silence_off_requires_debounce():
    v = VAD()
    for _ in range(10):
        v.process(frame(0.2))
    assert v.is_speaking()
    v.process(frame(0.0, 100))  # < 200ms 不应退出
    assert v.is_speaking()
    v.process(frame(0.0, 150))  # 累计 250ms ≥ 200ms
    assert not v.is_speaking()


def test_silence_seconds_after_speech():
    v = VAD()
    for _ in range(10):
        v.process(frame(0.2))
    v.process(frame(0.0, 300))
    assert v.silence_seconds() >= 0.2


def test_bytes_input_and_reset():
    v = VAD()
    v.process(frame(0.2, 150).tobytes())
    assert v.is_speaking()
    v.reset()
    assert not v.is_speaking()
    assert v.silence_seconds() == 0.0


def test_non_finite_input_safe():
    v = VAD()
    v.process(np.array([np.inf, -np.inf, np.nan], dtype=np.float32))
    assert not v.is_speaking()

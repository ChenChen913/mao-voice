# -*- coding: utf-8 -*-
"""录音模块单元测试：不打开真实麦克风（用伪造流/直接调回调）。"""
import threading
import time

import numpy as np

from recorder import Recorder


class FakeStream:
    def __init__(self):
        self.stopped = False

    def start(self):
        pass

    def stop(self):
        self.stopped = True

    def close(self):
        pass


def _frame(amp, n=320):
    return np.full((n, 1), amp, dtype=np.float32)


def test_frequency_bands_shape():
    r = Recorder()
    sr = 16000
    peaks = {}
    for freq in (200, 1000, 3000):
        t = np.arange(320, dtype=np.float32) / sr
        x = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32).reshape(-1, 1)
        bands = r._compute_bands(x)
        assert bands is not None and len(bands) == Recorder.SPECTRUM_BANDS
        assert all(0.0 <= b <= 1.0 for b in bands)
        peaks[freq] = int(np.argmax(bands))
    assert peaks[3000] > peaks[1000] > peaks[200]


def test_speaking_hysteresis():
    r = Recorder(on_level=lambda v: None)
    for _ in range(5):
        r._callback(_frame(0.0), 320, None, None)
    assert r.speaking_now is False
    for _ in range(3):
        r._callback(_frame(0.05), 320, None, None)  # rms01≈0.17 → 开启
    assert r.speaking_now is True
    for _ in range(3):
        r._callback(_frame(0.002), 320, None, None)  # rms01≈0.007 < 关闭阈值
    assert r.speaking_now is False


def test_snapshot_epoch_guard():
    r = Recorder(on_draft=lambda a: None)
    r._all_parts = [np.zeros(1600, dtype=np.float32)]
    r._chunks = [np.zeros(1600, dtype=np.float32)]
    r._epoch = 6
    out = r._snapshot_from_offset(5)  # 旧会话残留线程
    assert out.size == 0
    assert len(r._all_parts) == 1 and len(r._chunks) == 1


def test_stop_does_not_block_on_slow_draft():
    r = Recorder(on_draft=lambda a: time.sleep(2.0))
    r._stream = FakeStream()
    r._all_parts = [np.zeros(1600, dtype=np.float32)]
    r._chunks = [np.zeros(1600, dtype=np.float32)]

    def slow_draft():
        time.sleep(2.0)

    r._draft_thread = threading.Thread(target=slow_draft, daemon=True)
    r._draft_thread.start()
    t0 = time.time()
    audio = r.stop()
    assert time.time() - t0 < 0.5
    assert audio.size == 3200
    assert r.active is False


def test_active_flag():
    r = Recorder()
    r._stream = FakeStream()
    assert r.active is True
    r._stream = None
    assert r.active is False

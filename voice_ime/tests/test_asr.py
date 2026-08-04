"""ASR 引擎单元测试：聚焦并发推理串行化（C1），不加载真实模型。"""
import threading
import time

import numpy as np

from asr import WhisperEngine


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

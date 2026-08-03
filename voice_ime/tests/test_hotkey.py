# -*- coding: utf-8 -*-
"""热键模块单元测试：防抖逻辑用可控时钟，生命周期用真实 pynput。"""
import threading
import time

import pytest
from pynput import keyboard

from hotkey import HotkeyListener


def test_debounce_ignores_fast_double_press(monkeypatch):
    h = HotkeyListener("f9", lambda: None)
    now = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    h._on_press(keyboard.Key.f9)
    assert h._task_queue.qsize() == 1
    now[0] += 0.1
    h._on_press(keyboard.Key.f9)
    assert h._task_queue.qsize() == 1  # 200ms 内被防抖忽略
    now[0] += 0.3
    h._on_press(keyboard.Key.f9)
    assert h._task_queue.qsize() == 2


def test_alt_r_accepts_altgr():
    h = HotkeyListener("alt_r", lambda: None)
    assert keyboard.Key.alt_gr in h.keys


def test_start_stop_lifecycle():
    h = HotkeyListener("f9", lambda: None)
    h.start()
    assert h._worker is not None and h._worker.is_alive()
    h.stop()
    assert h._worker is None or not h._worker.is_alive()


def test_stop_from_worker_does_not_self_join():
    h = HotkeyListener("f9", lambda: h.stop())  # 回调即 stop：模拟 worker 线程内调用 stop
    h.start()
    h._task_queue.put(object())       # 触发一次 on_toggle（即 stop）
    h._worker.join(timeout=3.0)
    assert not h._worker.is_alive()
    # worker 已退出；外部再 stop 一次应无异常
    h.stop()

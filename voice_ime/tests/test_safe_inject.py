# -*- coding: utf-8 -*-
"""安全注入单元测试：真实注入需要人工目标窗口，其余路径用 mock 覆盖（D1/B2）。"""
import safe_inject


def test_empty_text_guard():
    ok, msg = safe_inject.inject("")
    assert ok is False
    assert "为空" in msg


class _FakeKeyboard:
    """模拟 pynput KeyboardController，只记录按键。"""

    def __init__(self):
        self.pressed = []
        self.released = []

    def press(self, key):
        self.pressed.append(key)

    def release(self, key):
        self.released.append(key)


def _mock_full_inject(monkeypatch):
    """把注入成功路径所需的剪贴板/键盘全部替换为可控 mock，返回 sleep 记录。"""
    sleeps = []
    monkeypatch.setattr(safe_inject.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(safe_inject, "_check_uipi_block", lambda: (False, ""))
    monkeypatch.setattr(safe_inject, "_save_all_clipboard_formats", lambda: (0, []))
    monkeypatch.setattr(safe_inject, "_open_clipboard", lambda *a: True)
    monkeypatch.setattr(safe_inject, "_restore_clipboard_from_saved",
                        lambda saved, seq: (True, "剪贴板已成功恢复"))
    monkeypatch.setattr(safe_inject.user32, "EmptyClipboard", lambda: True)
    monkeypatch.setattr(safe_inject.user32, "SetClipboardData", lambda f, h: 1)
    monkeypatch.setattr(safe_inject.user32, "GetClipboardSequenceNumber", lambda: 1)
    monkeypatch.setattr(safe_inject.kernel32, "GlobalAlloc", lambda *a: 1)
    monkeypatch.setattr(safe_inject.kernel32, "GlobalLock", lambda *a: 1)
    monkeypatch.setattr(safe_inject.kernel32, "GlobalUnlock", lambda *a: True)
    monkeypatch.setattr(safe_inject.ctypes, "memmove", lambda *a: None)
    fake_kb = _FakeKeyboard()
    monkeypatch.setattr(safe_inject, "KeyboardController", lambda: fake_kb)
    return sleeps, fake_kb


def test_inject_success_uses_restore_delay(monkeypatch):
    """注入成功路径：Ctrl+V 后等待可配置的 restore_delay_sec 再恢复剪贴板（M2）。"""
    sleeps, fake_kb = _mock_full_inject(monkeypatch)

    ok, msg = safe_inject.inject("你好", restore_delay_sec=0.35)

    assert ok is True
    assert "剪贴板已恢复" in msg
    assert 0.35 in sleeps, "应等待配置的恢复延迟 0.35s，实际等待序列：{}".format(sleeps)
    assert fake_kb.pressed == [safe_inject.Key.ctrl, "v"]
    assert fake_kb.released == ["v", safe_inject.Key.ctrl]


def test_restore_delay_clamped(monkeypatch):
    """N-m2：非数字回退默认 0.2s，超范围钳制到 5s，不再抛 TypeError。"""
    sleeps, _ = _mock_full_inject(monkeypatch)

    ok, msg = safe_inject.inject("你好", restore_delay_sec="abc")
    assert ok is True
    assert 0.2 in sleeps

    sleeps.clear()
    ok, msg = safe_inject.inject("你好", restore_delay_sec=999)
    assert ok is True
    assert max(sleeps) == 5.0


def test_inject_aborts_when_focus_changed(monkeypatch):
    """B7：前台窗口与录制结束时不一致 → 取消注入且完全不碰剪贴板。"""
    monkeypatch.setattr(safe_inject, "_check_uipi_block", lambda: (False, ""))
    monkeypatch.setattr(safe_inject, "_foreground_root_hwnd", lambda: 111)
    clipboard_calls = []
    monkeypatch.setattr(
        safe_inject, "_save_all_clipboard_formats",
        lambda: clipboard_calls.append(1) or (0, []),
    )

    ok, msg = safe_inject.inject("你好", expected_hwnd=222, require_same_focus=True)

    assert ok is False
    assert "前台窗口已切换" in msg
    assert clipboard_calls == [], "焦点不一致时不应打开/修改剪贴板"


def test_restore_skipped_when_sequence_changed(monkeypatch):
    """D1：注入期间剪贴板被外部修改 → 跳过恢复并保留备份供调用方释放。"""
    saved = [(safe_inject.CF_UNICODETEXT, 11)]
    monkeypatch.setattr(safe_inject.user32, "GetClipboardSequenceNumber", lambda: 999)

    ok, msg = safe_inject._restore_clipboard_from_saved(saved, original_seq=100)

    assert ok is False
    assert "外部修改" in msg
    assert saved == [(safe_inject.CF_UNICODETEXT, 11)]


def test_restore_partial_failure_frees_remaining_and_clears(monkeypatch):
    """D1：恢复中途 SetClipboardData 失败 → 剩余句柄释放、saved 清空（防 double-free）。"""
    saved = [(safe_inject.CF_UNICODETEXT, 11), (safe_inject.CF_UNICODETEXT, 12)]
    monkeypatch.setattr(safe_inject, "_open_clipboard", lambda *a: True)
    monkeypatch.setattr(safe_inject.user32, "GetClipboardSequenceNumber", lambda: 100)
    monkeypatch.setattr(safe_inject.user32, "EmptyClipboard", lambda: True)
    monkeypatch.setattr(safe_inject.user32, "SetClipboardData", lambda fmt, h: False)
    freed = []
    monkeypatch.setattr(safe_inject.kernel32, "GlobalFree", lambda h: freed.append(h) or 0)

    ok, msg = safe_inject._restore_clipboard_from_saved(saved, original_seq=100)

    assert ok is False
    assert "SetClipboardData 失败" in msg
    assert saved == [], "失败后必须清空 saved，防止调用方 double-free"
    assert freed == [11, 12]

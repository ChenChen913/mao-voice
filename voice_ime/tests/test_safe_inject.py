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
    # v5.18：钉死窗口类名解析（测试环境前台可能是终端，auto 模式会误入 Unicode 通道）
    monkeypatch.setattr(safe_inject, "_foreground_root_hwnd", lambda: 0)
    monkeypatch.setattr(safe_inject, "_window_class_name", lambda h: "FakeWindow")
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
    put_calls = []
    monkeypatch.setattr(
        safe_inject, "_save_all_clipboard_formats",
        lambda: clipboard_calls.append(1) or (0, []),
    )
    monkeypatch.setattr(
        safe_inject, "_put_text_to_clipboard",
        lambda t: put_calls.append(t) or True,
    )

    ok, msg = safe_inject.inject("你好", expected_hwnd=222, require_same_focus=True)

    assert ok is False
    assert "前台窗口已切换" in msg
    assert "已复制到剪贴板" in msg
    assert clipboard_calls == [], "焦点不一致时不应打开/修改剪贴板"
    assert put_calls == ["你好"], "中止时应把文本降级写入剪贴板"


def test_inject_uipi_aborts_copies_text_to_clipboard(monkeypatch):
    """B3：UIPI 拦截时同样把文本降级写入剪贴板。"""
    monkeypatch.setattr(
        safe_inject, "_check_uipi_block",
        lambda: (True, "目标窗口以管理员权限运行"),
    )
    put_calls = []
    monkeypatch.setattr(
        safe_inject, "_put_text_to_clipboard",
        lambda t: put_calls.append(t) or True,
    )

    ok, msg = safe_inject.inject("你好")

    assert ok is False
    assert "UIPI 拦截" in msg
    assert "已复制到剪贴板" in msg
    assert put_calls == ["你好"]


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


# ==================== v5.18：粘贴通道选择与 Unicode 直注 ====================

def test_resolve_paste_mode_explicit():
    assert safe_inject._resolve_paste_mode("Notepad", "unicode") == "unicode"
    assert safe_inject._resolve_paste_mode("mintty", "ctrl_v") == "ctrl_v"


def test_resolve_paste_mode_auto_terminal_classes():
    # auto：终端类名子串命中（大小写不敏感）→ Unicode 直注
    assert safe_inject._resolve_paste_mode("ConsoleWindowClass", "auto") == "unicode"
    assert safe_inject._resolve_paste_mode("CASCADIA_HOSTING_WINDOW_CLASS", "auto") == "unicode"
    assert safe_inject._resolve_paste_mode("mintty.exe 窗口", "auto") == "unicode"
    assert safe_inject._resolve_paste_mode("PuTTY", "auto") == "unicode"


def test_resolve_paste_mode_auto_normal_window():
    assert safe_inject._resolve_paste_mode("Notepad", "auto") == "ctrl_v"
    assert safe_inject._resolve_paste_mode("", "auto") == "ctrl_v"  # 类名取不到 → fail-open
    assert safe_inject._resolve_paste_mode(None, None) == "ctrl_v"  # 缺省 auto


def test_resolve_paste_mode_custom_classes():
    classes = ["MyTerminal"]
    assert safe_inject._resolve_paste_mode("MyTerminal123", "auto", classes) == "unicode"
    assert safe_inject._resolve_paste_mode("Notepad", "auto", classes) == "ctrl_v"


def test_unicode_key_events_ascii_cjk_surrogate():
    events = safe_inject._unicode_key_events("A中")
    # 每个码元按下+抬起：A(1) + 中(1) → 4 个事件
    assert len(events) == 4
    assert events[0] == (ord("A"), False) and events[1] == (ord("A"), True)
    assert events[2] == (ord("中"), False) and events[3] == (ord("中"), True)
    # 代理对（😀 = U+1F600）：两个 UTF-16 码元 → 4 个事件
    events = safe_inject._unicode_key_events("😀")
    assert len(events) == 4
    # 第 1 个码元（下/上两个事件）是高位代理，第 2 个码元是低位代理
    assert 0xD800 <= events[0][0] <= 0xDBFF  # high surrogate
    assert 0xDC00 <= events[2][0] <= 0xDFFF  # low surrogate


def test_inject_unicode_channel_skips_clipboard(monkeypatch):
    """paste_mode=unicode 时直接走 SendInput 通道，完全不碰剪贴板。"""
    monkeypatch.setattr(safe_inject, "_check_uipi_block", lambda: (False, ""))
    monkeypatch.setattr(safe_inject, "_foreground_root_hwnd", lambda: 0)
    monkeypatch.setattr(safe_inject, "_window_class_name", lambda h: "Notepad")
    clipboard_calls = []
    monkeypatch.setattr(
        safe_inject, "_save_all_clipboard_formats",
        lambda: clipboard_calls.append(1) or (0, []),
    )
    sent = []
    monkeypatch.setattr(
        safe_inject, "_inject_unicode",
        lambda t: sent.append(t) or (True, "注入成功（Unicode 直注，未占用剪贴板）"),
    )

    ok, msg = safe_inject.inject("你好", paste_mode="unicode")

    assert ok is True and "Unicode 直注" in msg
    assert sent == ["你好"]
    assert clipboard_calls == [], "Unicode 通道不应打开剪贴板"


def test_inject_auto_uses_unicode_for_terminal(monkeypatch):
    """auto 模式：目标窗口是终端类 → 自动切 Unicode 通道。"""
    monkeypatch.setattr(safe_inject, "_check_uipi_block", lambda: (False, ""))
    monkeypatch.setattr(safe_inject, "_foreground_root_hwnd", lambda: 777)
    monkeypatch.setattr(safe_inject, "_window_class_name", lambda h: "ConsoleWindowClass")
    sent = []
    monkeypatch.setattr(
        safe_inject, "_inject_unicode",
        lambda t: sent.append(t) or (True, "注入成功（Unicode 直注，未占用剪贴板）"),
    )

    ok, msg = safe_inject.inject("ls -la", expected_hwnd=777, paste_mode="auto")

    assert ok is True and sent == ["ls -la"]

# -*- coding: utf-8 -*-
"""手动端到端冒烟：TTS 合成语音 → 本地 ASR → 真实注入 → 校验剪贴板恢复。

这是 CI 之外的「真机」冒烟，覆盖单测无法覆盖的三段：
  1. faster-whisper 真实加载模型并转写一段语音；
  2. 把文本真正注入一个前台窗口（跨进程消息循环，与真实应用一致）；
  3. 确认注入后剪贴板恢复到注入前的哨兵内容。

用法（在 voice_ime/ 目录下执行）：
    python tests/e2e_live.py            # 完整链路（需已下载本地模型 + Windows TTS）
    python tests/e2e_live.py --no-asr   # 只跑注入 + 剪贴板恢复（不需要模型）

退出码：0 = 通过；1 = 失败；2 = 环境不满足（跳过，不算失败）。
"""
import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
if BASE not in sys.path:
    sys.path.insert(0, BASE)

SENTINEL = "__mao_voice_clipboard_sentinel__"
TTS_TEXT = "Hello, this is a mao voice end to end test."
SKIP = 2


def _synthesize_wav(text, path):
    """用 Windows SAPI 合成一段 wav；失败返回 False。"""
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SetOutputToWaveFile('{}'); $s.Speak('{}'); $s.Dispose()"
    ).format(path.replace("'", "''"), text.replace("'", "''"))
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True, capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print("[跳过] TTS 合成失败：{}".format(e))
        return False
    return os.path.exists(path) and os.path.getsize(path) > 0


def _read_wav(path, target_sr=16000):
    """读取 PCM wav → 单声道 float32 @ target_sr（线性插值重采样）。"""
    import numpy as np

    with wave.open(path, "rb") as f:
        if f.getsampwidth() != 2:
            raise ValueError("仅支持 16-bit PCM wav（当前 {} bit）".format(f.getsampwidth() * 8))
        sr, channels = f.getframerate(), f.getnchannels()
        frames = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32)
    frames /= 32768.0
    if channels > 1:
        frames = frames.reshape(-1, channels).mean(axis=1)
    if sr != target_sr and frames.size:
        n = int(round(frames.size * target_sr / sr))
        frames = np.interp(
            np.linspace(0, frames.size - 1, n), np.arange(frames.size), frames
        ).astype(np.float32)
    return frames


def _transcribe():
    """加载本地模型并转写 TTS 音频；返回转写文本，环境不满足返回 None。"""
    import config
    from asr import WhisperEngine

    cfg = config.load_config()
    model = cfg.get("asr", {}).get("model", "")
    if not model:
        print("[跳过] 配置里没有 asr.model")
        return None
    if os.sep in model or "/" in model:
        if not os.path.exists(model):
            print("[跳过] 模型目录不存在：{}\n       先运行 python download_model.py".format(model))
            return None

    tmp = tempfile.mkdtemp(prefix="mao_e2e_")
    wav_path = os.path.join(tmp, "tts.wav")
    if not _synthesize_wav(TTS_TEXT, wav_path):
        return None
    try:
        audio = _read_wav(wav_path)
    except Exception as e:
        print("[跳过] 音频读取失败：{}".format(e))
        return None
    finally:
        try:
            os.remove(wav_path)
            os.rmdir(tmp)
        except OSError:
            pass

    if audio.size < 16000:
        print("[跳过] 合成音频过短（{} 采样点）".format(audio.size))
        return None

    print("[1/2] 加载模型并转写 {} 秒音频…".format(round(audio.size / 16000, 1)))
    engine = WhisperEngine(model, cfg.get("asr", {}).get("language"))
    try:
        got = engine.transcribe(audio).strip()
    except Exception as e:
        print("[失败] 转写异常：{}".format(e))
        return ""
    print("       识别结果：{!r}".format(got))
    if not got:
        print("[失败] 转写结果为空")
        return ""
    if not any(k in got.lower() for k in ("mao", "test", "voice")):
        print("[提示] 识别结果与预期差异较大，但非空，继续验证注入链路")
    return got


def _root_hwnd(root):
    import ctypes

    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    return int(user32.GetParent(root.winfo_id()) or root.winfo_id())


def _force_foreground(root, hwnd):
    """把测试窗口拉到前台。

    从后台终端启动的进程会被 Windows 前台锁挡住（focus_force 无效），
    先模拟一次 Alt 按下/抬起解锁，再 SetForegroundWindow，实测有效。
    """
    import ctypes

    import safe_inject

    user32 = ctypes.windll.user32
    VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002
    for _ in range(5):
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        root.update()
        time.sleep(0.15)
        if safe_inject._foreground_root_hwnd() == hwnd:
            return True
    return False


def _clipboard_win32():
    """返回 (设置文本, 读取文本) 两个 Win32 剪贴板操作，避免 Tk 自己持有剪贴板。

    Tk 的 clipboard_append 会让 Tk 成为剪贴板所有者，注入期间会与
    safe_inject 的备份/恢复互相干扰；用 Win32 设置哨兵更接近真实外部应用。
    """
    import ctypes
    import ctypes.wintypes as wt

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wt.HWND]
    user32.OpenClipboard.restype = wt.BOOL
    user32.CloseClipboard.restype = wt.BOOL
    user32.EmptyClipboard.restype = wt.BOOL
    user32.GetClipboardData.argtypes = [wt.UINT]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [wt.UINT, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = wt.BOOL
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]

    def _set(text):
        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            data = (text + "\0").encode("utf-16-le")
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not handle:
                return False
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                kernel32.GlobalFree(handle)
                return False
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                return False
            return True
        finally:
            user32.CloseClipboard()

    def _get():
        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    return _set, _get


def _inject_and_verify(text):
    """在真实 Tk 窗口中注入并校验：文本落到输入框、剪贴板恢复为哨兵。

    注入放在工作线程、Tk 主循环持续运行：这样目标应用才能像真实程序一样
    在注入的 0.3s 等待窗口内处理 Ctrl+V，而不是等注入结束才去读剪贴板。
    """
    import tkinter as tk

    import safe_inject

    root = tk.Tk()
    root.title("mao-voice e2e target")
    root.geometry("640x220+120+120")
    txt = tk.Text(root, height=6)
    txt.pack(fill="both", expand=True, padx=8, pady=8)

    def _paste(event):
        txt.insert("insert", root.clipboard_get())
        return "break"  # 阻止类绑定再粘贴一次

    txt.bind("<Control-v>", _paste)
    root.update()
    root.attributes("-topmost", True)
    root.update()
    hwnd = _root_hwnd(root)
    if not _force_foreground(root, hwnd):
        root.destroy()
        print("[失败] 无法把测试窗口切到前台（前台锁未解锁），请在桌面会话中重试")
        return ["测试窗口无法取得前台焦点"]

    txt.focus_set()
    root.update()

    set_clip, get_clip = _clipboard_win32()
    if not set_clip(SENTINEL):
        root.destroy()
        print("[失败] 无法写入剪贴板哨兵")
        return ["剪贴板哨兵写入失败"]

    state = {"done": False, "ok": False, "reason": "", "finished_at": 0.0}

    def worker():
        state["ok"], state["reason"] = safe_inject.inject(
            text, expected_hwnd=hwnd, require_same_focus=True, restore_delay_sec=0.4,
        )
        state["finished_at"] = time.time()
        state["done"] = True

    print("[2/2] 注入到前台窗口（hwnd={}）…".format(hwnd))
    threading.Thread(target=worker, daemon=True).start()

    def poll():
        if state["done"] and time.time() - state["finished_at"] > 0.4:
            root.quit()
            return
        root.after(50, poll)

    root.after(50, poll)
    root.mainloop()

    got = txt.get("1.0", "end").strip()
    clipboard_after = get_clip()
    root.destroy()

    print("       inject 返回：ok={} reason={}".format(state["ok"], state["reason"]))
    print("       窗口收到：{!r}".format(got))
    print("       剪贴板恢复：{!r}".format(clipboard_after))

    problems = []
    if not state["ok"]:
        problems.append("注入失败：" + state["reason"])
    if got != text:
        problems.append("窗口内容与注入文本不一致")
    if clipboard_after != SENTINEL:
        problems.append("剪贴板未恢复到注入前内容")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="mao-voice 真机端到端冒烟")
    parser.add_argument("--no-asr", action="store_true",
                        help="跳过模型转写，只用固定文本验证注入与剪贴板恢复")
    args = parser.parse_args(argv)

    if not sys.platform.startswith("win"):
        print("[跳过] 仅支持 Windows")
        return SKIP

    if args.no_asr:
        text = "端到端注入测试 mao-voice 123"
        print("[1/2] 已跳过 ASR（--no-asr）")
    else:
        text = _transcribe()
        if text is None:
            return SKIP
        if not text:
            return 1

    problems = _inject_and_verify(text)
    if problems:
        for p in problems:
            print("[失败] " + p)
        return 1
    print("[通过] 端到端冒烟通过：转写 → 注入 → 剪贴板恢复")
    return 0


if __name__ == "__main__":
    sys.exit(main())

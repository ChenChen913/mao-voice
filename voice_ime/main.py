"""AI 语音输入法 MVP —— 入口。

运行：python main.py
热键：默认右 Alt（toggle 模式），按一下开始录音，再按一下结束并 转写→润色→注入。
"""
import queue
import threading
import time
import tkinter as tk
import logging

from config import build_words_block, ensure_defaults, load_config, save_config
from hotkey import HotkeyListener
from recorder import Recorder
from asr import WhisperEngine
from refiner import Refiner
import safe_inject
from history import HistoryStore
from ui import Overlay
from settings_ui import SettingsWindow, TrayIcon

MIN_DURATION = 0.5

# 热键配置名 → 悬浮窗可读文案（默认 alt_r 显示"右 Alt"）
_HOTKEY_LABEL = {
    "alt_r": "右 Alt",
    "alt_l": "左 Alt",
    "ctrl_r": "右 Ctrl",
    "ctrl_l": "左 Ctrl",
    "shift_r": "右 Shift",
    "shift_l": "左 Shift",
}


def make_asr(cfg):
    """按配置选择 ASR 引擎：云端（需配置）> 本地 whisper。"""
    a = cfg.get("asr", {})
    cloud = a.get("cloud", {})
    if a.get("engine") == "cloud" and cloud.get("api_key") and cloud.get("base_url"):
        from cloud_asr import CloudASREngine
        return CloudASREngine(
            base_url=cloud["base_url"], api_key=cloud["api_key"],
            model=cloud.get("model", "whisper-1"),
        )
    return WhisperEngine(a.get("model", "small"), a.get("language", "zh"))


class App:
    # 润色强度循环档位（F9 运行时切换）
    REFINE_LEVELS = ("conservative", "light", "polish")
    REFINE_LABELS = {
        "conservative": "保守纠错",
        "light": "轻度规整",
        "polish": "完整规整",
    }

    def __init__(self, cfg, overlay, root):
        self.cfg = cfg
        self.overlay = overlay
        self.root = root
        self.asr = make_asr(cfg)
        self.refiner = Refiner(cfg)
        # v5.13.4：输入历史（成功注入后记录；配置关闭或落盘失败都不影响主流程）
        self.history = None
        hist_cfg = cfg.get("history", {})
        if hist_cfg.get("enabled", True):
            self.history = HistoryStore(max_entries=hist_cfg.get("max_entries", 100))
        self.recorder = None
        self.tray = None               # 托盘图标（pystray）
        self.settings_win = None       # 设置窗口（单例）
        self._last_tray_state = None
        self.state = "IDLE"
        self._last_draft = ""
        self._last_rms = 0.0          # 录音线程写入的最新电平（0~1），float 原子写，无需加锁
        self._lock = threading.Lock()
        self._ui_queue = queue.Queue()
        self._toast_text = None      # 悬浮窗短暂提示文本（如润色强度切换）
        self._toast_until = 0.0      # 提示到期时间（monotonic）

    # ---------- 热键事件（pynput 线程） ----------
    def on_toggle(self):
        """单击热键切换：IDLE→开始录音，RECORDING→结束录音并转写，PROCESSING→忽略。

        设计原因：toggle 模式下用户按一下立即松开即切换状态，不再需要按住/松开配对。
        RECORDING 分支不在锁内提前切 PROCESSING：状态转移统一由
        _finish_recording 的 guard 完成（热键与静音自动停止共用同一保护），
        否则 _finish_recording 的 `state != "RECORDING"` 检查会把热键路径挡掉。
        """
        with self._lock:
            if self.state == "IDLE":
                # v5.11：在同一个临界区内创建 recorder 并置 RECORDING，
                # 杜绝"状态已切 RECORDING 但 recorder 仍为 None"的竞态窗口
                self.recorder = Recorder(
                    on_draft=self._on_draft, on_level=self._on_level,
                    device=self.cfg.get("recorder", {}).get("device") or None,
                )
                self.state = "RECORDING"
                action = "start"
            elif self.state == "RECORDING":
                action = "finish"
            else:
                return  # 转写/处理中不响应，避免打断
        if action == "start":
            self._start_recording()
        else:
            self._finish_recording()

    # ---------- 润色强度运行时切换（F9，v5.13.3） ----------
    def on_cycle_refine(self):
        """循环切换润色强度并持久化；热键线程调用，只操作锁内配置 + 队列。"""
        levels = self.REFINE_LEVELS
        current = self.cfg.get("refine", {}).get("level", "conservative")
        if current not in levels:
            current = "conservative"
        nxt = levels[(levels.index(current) + 1) % len(levels)]
        with self._lock:
            self.cfg.setdefault("refine", {})["level"] = nxt
        try:
            save_config(self.cfg)
        except Exception:
            print("[提示] 润色强度已切换，但写入配置失败（本次运行仍生效）")
        label = self.REFINE_LABELS[nxt]
        hotkey = self.cfg.get("refine_cycle_hotkey", "f9")
        print("[设置] 润色强度 -> {}".format(label))
        self._show_toast("✨ 润色强度：{}（再按 {} 切换）".format(label, hotkey))

    def _show_toast(self, text, seconds=1.5):
        """在悬浮窗短暂显示提示文本（仅空闲态自动隐藏，不覆盖录音/处理状态）。"""
        self._ui_queue.put(("toast", (text, seconds)))

    # ---------- 托盘 / 设置窗口（v5.13.5） ----------
    def open_settings(self):
        """跨线程安全：托盘线程调用 → 主线程队列处理。"""
        self._ui_queue.put(("settings", None))

    def exit_app(self):
        """跨线程安全：托盘线程调用 → 主线程队列处理。"""
        self._ui_queue.put(("exit", None))

    def save_cfg(self):
        save_config(self.cfg)

    def _open_settings_impl(self):
        if self.settings_win is None or not self.settings_win.root.winfo_exists():
            self.settings_win = SettingsWindow(self)
        else:
            self.settings_win.lift()

    def _update_tray(self, state):
        if self.tray is not None and state != self._last_tray_state:
            self._last_tray_state = state
            try:
                self.tray.set_status(state)
            except Exception:
                pass

    def _start_recording(self):
        self._last_draft = ""
        self._last_rms = 0.0
        label = _HOTKEY_LABEL.get(self.cfg["hotkey"], self.cfg["hotkey"])
        with self._lock:
            if self.state != "RECORDING":
                return  # 极快速双击时已被并发的结束操作抢占 → 放弃启动，避免悬挂录音
            recorder = self.recorder
        self._post("RECORDING", "🎤 录音中…（再按一下 {} 结束）".format(label))
        try:
            recorder.start()
        except Exception:
            # 启动失败（无输入设备等）：复位状态并提示，避免一直卡在 RECORDING
            with self._lock:
                if self.recorder is recorder:
                    self.recorder = None
                self.state = "IDLE"
            self._post("ERROR", "录音启动失败，请检查麦克风")

    # ---------- 录音电平（音频回调线程 → 共享变量 → 主线程轮询） ----------
    def _on_level(self, rms_01):
        # 音频回调线程：只写共享 float（原子写），绝不在回调线程里操作 tkinter
        self._last_rms = rms_01

    def _poll_level(self):
        """主线程每 100ms 读取电平与快速说话指示并交给悬浮窗。

        RECORDING 时驱动实时波形，且只有"正在说话"才显示声波；
        其余状态输出 0 实现归零。
        set_level 只在此主线程调用（tkinter 线程安全），worker/回调线程绝不碰悬浮窗。
        """
        with self._lock:
            recording = self.state == "RECORDING"
            recorder = self.recorder
        speaking = False
        if recording and recorder is not None:
            try:
                # v5.5：用逐帧更新的快速说话指示（双阈值滞回），
                # 比 VAD 去抖判定更快，声波"开口即现、停口即灭"
                speaking = recorder.speaking_now
            except Exception:
                pass
        try:
            self.overlay.set_speaking(speaking)
            # v5.7：频带电平（频谱形状）驱动多频段波形；无数据时悬浮窗回退 RMS
            self.overlay.set_levels(recorder.bands_now if recorder is not None else None)
            self.overlay.set_level(self._last_rms if recording else 0.0)
        except Exception:
            pass  # 悬浮窗偶发异常不影响录音主流程
        self.root.after(100, self._poll_level)

    def _finish_recording(self):
        """结束录音并启动转写（RECORDING→PROCESSING）；静音自动停止也走这里。

        原实现不转移状态：_process 执行期间（ASR+润色+预览+注入可能数秒）
        state 仍为 RECORDING，静音轮询每次 tick 都会再次触发本方法，启动多个
        并发 worker（重复注入文本）；热键在 PROCESSING 期间按下也会再开 worker。
        锁内先检查后置位（原子转移 RECORDING→PROCESSING）：热键路径与自动停止
        路径共用此 guard，重复 worker 不可能出现。
        """
        with self._lock:
            if self.state != "RECORDING":
                return  # 已有处理在进行，避免重复启动 worker
            if self.recorder is None or not self.recorder.active:
                # v5.11：录音流尚未真正启动（刚按下 start 的极短窗口）→ 本次结束忽略，
                # 用户再按一次即可；避免对未启动的 recorder 空转
                return
            self.state = "PROCESSING"
        threading.Thread(target=self._process, daemon=True).start()

    # ---------- 录音期间增量草稿 ----------
    def _on_draft(self, audio):
        try:
            with self._lock:
                if self.state != "RECORDING":
                    # v5.11：结束录音（已进入 PROCESSING）后不再发起新的增量转写，
                    # 缩小与最终整段转写的并发窗口
                    return
            text = self.asr.transcribe(audio)
            text = text.strip()
            if text:
                with self._lock:
                    # 预留字段：v5 起浮窗不再展示转写内容，保留增量转写
                    # 用于模型预热与未来"实时草稿"功能
                    self._last_draft = text
        except Exception:
            logging.exception("增量草稿转写异常（已忽略，不影响录音）")

    # ---------- 静音自动停止（主线程轮询） ----------
    def _poll_recording(self):
        auto_stop = self.cfg.get("recorder", {}).get("auto_stop_silence_sec", 0)
        if auto_stop > 0:
            with self._lock:
                recording = self.state == "RECORDING"
            # v5.11：active 守卫——新 Recorder 创建完成前，不读上一会话已停止的 recorder
            if recording and self.recorder is not None and self.recorder.active:
                try:
                    if self.recorder.vad.silence_seconds() >= auto_stop:
                        self._finish_recording()
                except Exception:
                    pass
        self.root.after(300, self._poll_recording)

    # ---------- 处理管线（worker 线程） ----------
    def _process(self):
        try:
            # 在 try 内获取 recorder：即使为 None（异常路径），finally 仍会复位状态，
            # 不会像原实现那样因 stop() 抛异常而把应用卡死在 PROCESSING
            with self._lock:
                recorder = self.recorder
            audio = recorder.stop()
            if recorder.duration < MIN_DURATION:
                self._post("IDLE", "")
                return
            self._post("TRANSCRIBING", "✍️ 转写中…")
            try:
                raw = self.asr.transcribe(audio).strip()
            except Exception as e:
                # 转写异常显示可读原因（如"GPU 不可用已回退 CPU 后仍失败"），而非裸报错
                self._post("ERROR", "转写失败：{}".format(e))
                time.sleep(2.5)
                return
            if not raw:
                self._post("ERROR", "没有识别到内容，请重试")
                time.sleep(1.5)
                self._post("IDLE", "")
                return

            words_block = build_words_block()
            final = raw
            if self.refiner.enabled:
                self._post("REFINING", "✨ 润色中…")
                try:
                    final = self.refiner.refine(raw, words_block=words_block)
                except Exception as e:
                    final = raw
                    self._post("ERROR", "润色失败，已输出原始转写：{}".format(e))
                    time.sleep(1.2)
            else:
                self._post("ERROR", "未配置 API Key，已输出原始转写")
                time.sleep(1.2)

            # v5 起不再在浮窗预览转写内容：润色完成后直接注入输入框
            # （用户反馈"先显示再注入"是多余步骤；状态提示仍保留在浮窗）
            self._post("INJECTING", "⬇️ 注入中…")
            ok, reason = safe_inject.inject(final)
            if not ok:
                self._post("ERROR", "注入失败：{}".format(reason))
                time.sleep(2.5)
            elif "恢复未完成" in reason:
                # v5.4：注入成功即成功；剪贴板未恢复（如被其他程序占用/修改）
                # 只在控制台留一行提示供排查，不再弹 ERROR 打扰用户
                print("[剪贴板] " + reason)
            if ok and self.history is not None:
                try:
                    self.history.add(raw, final, duration_s=recorder.duration)
                except Exception:
                    logging.exception("写入历史记录失败（已忽略）")
        except Exception as e:
            self._post("ERROR", "出错了：{}".format(e))
            time.sleep(2.5)
        finally:
            self._post("IDLE", "")
            # 电平归零：float 原子写（音频回调线程只写、主线程只读），无需加锁；
            # 主线程 _poll_level 在 state 置 IDLE 前后可能读到 recording=False 而显示 0，
            # 与这里的归零互为冗余、无副作用——注释如实说明，避免误导为"只有 worker 归零"
            self._last_rms = 0.0
            with self._lock:
                self.state = "IDLE"

    # ---------- UI 更新（主线程轮询） ----------
    def _post(self, state, text):
        self._ui_queue.put(("state", (state, text)))

    def poll_ui(self):
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "state":
                    state, text = payload
                    if state == "IDLE":
                        self.overlay.hide()
                    else:
                        self.overlay.show(state, text)
                elif kind == "toast":
                    text, seconds = payload
                    self._toast_text = text
                    self._toast_until = time.monotonic() + seconds
                    self.overlay.show("PREVIEW", text)
                elif kind == "settings":
                    self._open_settings_impl()
                elif kind == "exit":
                    self.root.quit()
                    return
        except queue.Empty:
            pass
        # toast 到期且回到空闲态才隐藏，避免盖掉录音/处理中的悬浮窗
        with self._lock:
            idle = self.state == "IDLE"
        if self._toast_text and time.monotonic() > self._toast_until and idle:
            self._toast_text = None
            self.overlay.hide()
        with self._lock:
            cur_state = self.state
        self._update_tray(cur_state)
        self.root.after(60, self.poll_ui)


def main():
    ensure_defaults()
    cfg = load_config()
    if not cfg["refine"].get("api_key"):
        print("[提示] 尚未配置 DeepSeek API Key：请编辑 voice_ime/config.json 的 refine.api_key")
    root = tk.Tk()
    root.withdraw()
    overlay = Overlay(root)
    app = App(cfg, overlay, root)
    # 后台预热 ASR 模型：避免第一次按键时才下载/加载（首次可能耗时很久）
    if hasattr(app.asr, "warmup"):
        threading.Thread(target=app.asr.warmup, daemon=True).start()
    hotkey = HotkeyListener(cfg["hotkey"], app.on_toggle)
    hotkey.start()
    settings_hotkey = None
    settings_key = cfg.get("settings_hotkey", "f8")
    if settings_key and settings_key not in (cfg["hotkey"], cfg.get("refine_cycle_hotkey")):
        settings_hotkey = HotkeyListener(settings_key, app.open_settings)
        settings_hotkey.start()
        print("[设置] 按一下 {} 打开设置窗口".format(settings_key))
    refine_hotkey = None
    cycle_hotkey = cfg.get("refine_cycle_hotkey", "f9")
    if cycle_hotkey and cycle_hotkey != cfg["hotkey"]:
        refine_hotkey = HotkeyListener(cycle_hotkey, app.on_cycle_refine)
        refine_hotkey.start()
        print("[设置] 按一下 {} 循环切换润色强度（保守纠错/轻度规整/完整规整）".format(cycle_hotkey))
    auto_stop = cfg.get("recorder", {}).get("auto_stop_silence_sec", 0)
    print("[就绪] 按一下 {} 开始录音，再按一下结束并自动输入。右键悬浮窗可退出。".format(cfg["hotkey"]))
    if auto_stop > 0:
        print("[设置] 静音超过 {} 秒将自动结束录音".format(auto_stop))
    app.tray = TrayIcon(app)
    app.tray.start()
    root.after(60, app.poll_ui)
    root.after(300, app._poll_recording)
    root.after(100, app._poll_level)  # 电平轮询更快，波形才跟得上声音
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        hotkey.stop()
        if settings_hotkey:
            settings_hotkey.stop()
        if refine_hotkey:
            refine_hotkey.stop()
        if app.tray:
            app.tray.stop()


if __name__ == "__main__":
    main()

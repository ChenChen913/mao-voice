"""AI 语音输入法 MVP —— 入口。

运行：python main.py
热键：默认右 Alt（toggle 模式），按一下开始录音，再按一下结束并 转写→润色→注入。
"""
import queue
import threading
import time
import tkinter as tk

from config import build_words_block, ensure_defaults, load_config
from hotkey import HotkeyListener
from recorder import Recorder
from asr import WhisperEngine
from refiner import Refiner
import draft_smoother
import safe_inject
from ui import Overlay

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
    def __init__(self, cfg, overlay, root):
        self.cfg = cfg
        self.overlay = overlay
        self.root = root
        self.asr = make_asr(cfg)
        self.refiner = Refiner(cfg)
        self.recorder = None
        self.state = "IDLE"
        self._last_draft = ""
        self._last_rms = 0.0          # 录音线程写入的最新电平（0~1），float 原子写，无需加锁
        self._lock = threading.Lock()
        self._ui_queue = queue.Queue()

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

    def _start_recording(self):
        self._last_draft = ""
        self._last_rms = 0.0
        label = _HOTKEY_LABEL.get(self.cfg["hotkey"], self.cfg["hotkey"])
        with self._lock:
            if self.state != "RECORDING":
                return  # 极快速双击时已被并发的结束操作抢占 → 放弃启动，避免悬挂录音
            # 锁内创建并赋值 recorder：保证热键线程把状态切到 PROCESSING 并启动 _process 时，
            # 必然能看到已赋值的 recorder（原实现锁外赋值，存在 recorder 为 None 的竞态）
            self.recorder = Recorder(on_draft=self._on_draft, on_level=self._on_level)
        self._post("RECORDING", "🎤 录音中…（再按一下 {} 结束）".format(label))
        try:
            self.recorder.start()
        except Exception:
            # 启动失败（无输入设备等）：复位状态并提示，避免一直卡在 RECORDING
            with self._lock:
                self.recorder = None
                self.state = "IDLE"
            self._post("ERROR", "录音启动失败，请检查麦克风")

    # ---------- 录音电平（音频回调线程 → 共享变量 → 主线程轮询） ----------
    def _on_level(self, rms_01):
        # 音频回调线程：只写共享 float（原子写），绝不在回调线程里操作 tkinter
        self._last_rms = rms_01

    def _poll_level(self):
        """主线程每 100ms 读取电平并交给悬浮窗。

        RECORDING 时驱动实时波形；其余状态输出 0 实现归零。
        set_level 只在此主线程调用（tkinter 线程安全），worker/回调线程绝不碰悬浮窗。
        """
        with self._lock:
            recording = self.state == "RECORDING"
        try:
            self.overlay.set_level(self._last_rms if recording else 0.0)
        except Exception:
            pass
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
            self.state = "PROCESSING"
        threading.Thread(target=self._process, daemon=True).start()

    # ---------- 录音期间增量草稿 ----------
    def _on_draft(self, audio):
        try:
            text = self.asr.transcribe(audio)
            text = text.strip()
            if text:
                with self._lock:
                    self._last_draft = text  # 锁下写入：与 _process 的读取形成有序的 happens-before
                max_chars = self.cfg["ui"]["max_chars"]
                preview = text[:max_chars] + ("…" if len(text) > max_chars else "")
                self._post("RECORDING", "🎤 录音中…\n" + preview)
        except Exception:
            pass

    # ---------- 静音自动停止（主线程轮询） ----------
    def _poll_recording(self):
        auto_stop = self.cfg.get("recorder", {}).get("auto_stop_silence_sec", 0)
        if auto_stop > 0:
            with self._lock:
                recording = self.state == "RECORDING"
            if recording and self.recorder is not None:
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
                last_draft = self._last_draft  # 锁下快照草稿：跨线程读写的明确定序
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

            max_chars = self.cfg["ui"]["max_chars"]
            preview_sec = self.cfg["ui"]["preview_sec"]
            # 草稿平滑：从最近草稿过渡到最终文本，避免文本突变
            frames = [(final[:max_chars], preview_sec)]
            if last_draft and last_draft != final:
                try:
                    trans = draft_smoother.plan_transition(last_draft, final[:max_chars])
                    if len(trans) >= 2:
                        frames = trans[:-1] + [(final[:max_chars], preview_sec)]
                except Exception:
                    pass
            for frame_text, dur in frames:
                self._post("PREVIEW", frame_text)
                time.sleep(dur)

            self._post("INJECTING", "⬇️ 注入中…")
            ok, reason = safe_inject.inject(final)
            if not ok:
                # 区分"完全失败"与"已注入但剪贴板未恢复"两种情况，避免误导用户
                if reason.startswith("注入成功"):
                    self._post("ERROR", "文字已注入，但剪贴板未恢复：{}".format(reason))
                else:
                    self._post("ERROR", "注入失败：{}".format(reason))
                time.sleep(2.5)
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
        except queue.Empty:
            pass
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
    auto_stop = cfg.get("recorder", {}).get("auto_stop_silence_sec", 0)
    print("[就绪] 按一下 {} 开始录音，再按一下结束并自动输入。右键悬浮窗可退出。".format(cfg["hotkey"]))
    if auto_stop > 0:
        print("[设置] 静音超过 {} 秒将自动结束录音".format(auto_stop))
    root.after(60, app.poll_ui)
    root.after(300, app._poll_recording)
    root.after(100, app._poll_level)  # 电平轮询更快，波形才跟得上声音
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        hotkey.stop()


if __name__ == "__main__":
    main()

"""录音模块：16kHz 单声道 PCM 采集，支持录音期间增量草稿转写与 VAD 静音检测。"""
import logging
import threading
import time

import numpy as np
import sounddevice as sd

from vad import VAD


class Recorder:
    # RMS 归一化经验阈值：实测人声 RMS 达到 0.3 即视为"满格"（1.0），静音≈0
    RMS_NORMALIZE = 0.3

    # stop() 在 join(2s) 超时后最多再等草稿线程收尾的时长：on_draft 是慢转写回调，
    # 必须等它完成（快照在其前已入列）才能安全拼接最终音频；设上界防回调
    # 永久卡死（如用户回调死循环）把 stop() 拖死
    DRAFT_FINISH_WAIT_SEC = 8.0

    def __init__(self, samplerate=16000, on_draft=None, on_level=None, chunk_sec=2.0):
        self.samplerate = samplerate
        self.on_draft = on_draft          # callable(audio: np.ndarray)
        self.on_level = on_level          # callable(rms_01: float)  0~1 归一化录音电平
        self.chunk_sec = chunk_sec
        self._chunks = []                 # 实时录音帧（草稿快照后清空，内存有界于一个草稿窗口）
        self._all_parts = []              # 已被草稿快照消费的音频段：stop() 的最终转写需要全程音频
        self._stream = None
        self._lock = threading.Lock()
        self._draft_thread = None
        self._stop_draft = threading.Event()
        self._draft_done = threading.Event()  # 草稿线程真正退出时置位：stop() 靠它等 in-flight 收尾
        self._offset_samples = 0          # 本窗口内已消费样本数（快照后恒为 0）
        self._draft_busy = False
        self._epoch = 0                   # 会话代数：stop() 递增使残留的旧 draft 循环立即退出
        self.vad = VAD()

    def start(self):
        self._chunks = []
        self._all_parts = []
        self._offset_samples = 0
        self._stop_draft.clear()
        self._draft_done.clear()          # 上会话可能已置位：新会话重新开始等待
        self._epoch += 1
        epoch = self._epoch
        self.vad.reset()
        self._stream = sd.InputStream(
            samplerate=self.samplerate, channels=1, dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        if self.on_draft:
            self._draft_thread = threading.Thread(
                target=self._draft_loop, args=(epoch,), daemon=True
            )
            self._draft_thread.start()

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            self._chunks.append(indata.copy())
        # 音频回调线程异常无法安全上抛，但必须记日志：原实现静默吞掉会掩盖
        # VAD.process 或 on_level 的真实缺陷（如帧 dtype 不兼容），难以诊断
        try:
            self.vad.process(indata.flatten())
        except Exception:
            logging.exception("VAD.process 异常（已忽略，不影响录音）")
        # 每帧计算一次 RMS 电平（帧长约 20ms，频率适中），归一化后回调；
        # 回调抛异常必须静默吞掉，绝不影响录音主流程（同样记日志便于排查）
        try:
            if self.on_level:
                rms = float(np.sqrt(np.mean(indata ** 2)))
                self.on_level(min(rms / self.RMS_NORMALIZE, 1.0))
        except Exception:
            logging.exception("on_level 回调异常（已忽略，不影响录音）")

    def _draft_loop(self, epoch):
        chunk_samples = int(self.chunk_sec * self.samplerate)
        try:
            while not self._stop_draft.is_set():
                # 已被更新的会话取代（stop() 的 join 超时后旧循环残留）→ 立即退出，
                # 绝不与新一轮 draft 循环并发（epoch 检查比 _draft_busy 更可靠）
                if epoch != self._epoch:
                    break
                with self._lock:
                    busy = self._draft_busy
                if not busy:
                    with self._lock:
                        total = sum(c.shape[0] for c in self._chunks)
                    if total - self._offset_samples >= chunk_samples:
                        with self._lock:
                            self._draft_busy = True  # 锁下读写：跨循环串行化快照/回调段
                        try:
                            data = self._snapshot_from_offset()
                            if data.size > 0 and self.on_draft:
                                try:
                                    self.on_draft(data)
                                except Exception:
                                    # 与 _callback 同款设计原则：后台回调异常必须
                                    # 记日志且绝不能杀死录音循环——原实现会让
                                    # 异常从 _draft_loop 逸出、线程静默终止，
                                    # 本会话余下时间的增量草稿全部失效
                                    logging.exception(
                                        "on_draft 回调异常（本轮草稿已跳过，不影响后续）"
                                    )
                        finally:
                            with self._lock:
                                self._draft_busy = False
                time.sleep(0.3)
        finally:
            # 线程真正退出才置位：stop() 的 join 超时后靠它确认 in-flight 工作
            # （快照 + on_draft 回调）已经收尾，可以安全拼接/复用缓冲
            self._draft_done.set()

    def _snapshot_from_offset(self):
        """快照未消费音频并清空 _chunks：每次只拷贝一个窗口（O(窗口)）。

        原实现每次草稿都 np.concatenate 整个录音历史（累积 O(n²) 拷贝 + 无界 _chunks）。
        消费段移入 _all_parts 保留：stop() 的最终转写仍需要全程音频（功能不变），
        因此全程内存不可避免（见 README 取舍说明），但每段音频只被拷贝一次、_chunks 有界。
        """
        with self._lock:
            if not self._chunks:
                return np.empty(0, dtype=np.float32)
            data = np.concatenate(self._chunks).flatten()
            if data.size <= self._offset_samples:
                return np.empty(0, dtype=np.float32)
            out = data[self._offset_samples:]
            self._all_parts.append(out)
            self._chunks = []
            self._offset_samples = 0
            return out

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._stop_draft.set()
        self._epoch += 1  # join 超时（on_draft 慢）时旧循环下次迭代即退出，不会与下一轮并发
        if self._draft_thread:
            self._draft_thread.join(timeout=2)
            if self._draft_thread.is_alive():
                # join 超时：旧线程还卡在 on_draft（慢转写）中。此刻不能直接拼接
                # _all_parts——in-flight 的快照可能在拼接之后才追加音频，导致返回的
                # 最终音频缺尾段；若调用方立刻 start() 新会话，残留线程还可能串音到
                # 新缓冲（_epoch 检查只在循环顶部，挡不住快照在途的窗口）。
                # 等 _draft_done（线程真正退出）再继续；上界防回调永久卡死拖死 stop()
                logging.info(
                    "草稿线程 on_draft 较慢（join 超时），等待其收尾（≤%.0fs）",
                    Recorder.DRAFT_FINISH_WAIT_SEC,
                )
                self._draft_done.wait(timeout=Recorder.DRAFT_FINISH_WAIT_SEC)
                # 事件置位后线程立即退出（finally 末行是 set），短 join 收尾，
                # 避免线程退出前最后的调度间隙被下面 is_alive() 误判为卡死
                self._draft_thread.join(timeout=0.5)
                if self._draft_thread.is_alive():
                    # 极罕见（on_draft 卡死/快照被锁长阻塞）：放弃等待继续，
                    # 由 _epoch + _stop_draft 隔离残留线程（它不会再进入快照分支），
                    # 代价是可能丢最后一小段音频——记日志便于事后诊断
                    logging.warning(
                        "草稿线程 %.0fs 内未收尾，放弃等待继续（残留线程已被 epoch/stop 信号隔离）",
                        Recorder.DRAFT_FINISH_WAIT_SEC,
                    )
            self._draft_thread = None
        with self._lock:
            parts = self._all_parts
            if self._chunks:
                parts = parts + [np.concatenate(self._chunks).flatten()]
            data = np.concatenate(parts) if parts else np.empty(0, dtype=np.float32)
        return data.flatten()

    @property
    def duration(self):
        # 全程时长 = 已消费段 + 实时帧（_chunks 被草稿清空后只含最新窗口）
        with self._lock:
            total = sum(p.shape[0] for p in self._all_parts) + sum(
                c.shape[0] for c in self._chunks
            )
            return total / self.samplerate

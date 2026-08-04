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

    # 快速说话指示阈值（归一化 RMS，0~1）：驱动悬浮窗声波显示。
    # 与 VAD 分离：VAD 带 120/200ms 去抖，用于静音自动停止（偏保守）；
    # 波形显示要求更灵敏，用"开启/关闭双阈值滞回"逐帧更新，
    # 说话即亮、停口即灭，避免用户感知到约 1 秒的显示延迟。
    # v5.6：阈值大幅降低（约 -44dB），任何发声——包括轻声、气声、
    # "嗯/啊"等语气词——都会触发波形；只要用户出声，声波就跳动
    SPEAK_ON_RMS_01 = 0.02    # 开启阈值 ≈ -44dB（原始 RMS≈0.006）
    SPEAK_OFF_RMS_01 = 0.012  # 关闭阈值 ≈ -49dB，滞回防临界噪声抖动

    # 频谱频带数（v5.7）：与悬浮窗竖条数一致。对每帧音频做 FFT，
    # 按对数频带（80Hz~8kHz，覆盖人声）划分能量，驱动音乐播放器式的
    # 多频段波形——音调/语气不同，各频段能量不同，波形形状随之变化。
    SPECTRUM_BANDS = 15

    def __init__(self, samplerate=16000, on_draft=None, on_level=None, chunk_sec=2.0, device=None):
        self.samplerate = samplerate
        self.device = device  # 麦克风设备（None=系统默认）
        self.on_draft = on_draft          # callable(audio: np.ndarray)
        self.on_level = on_level          # callable(rms_01: float)  0~1 归一化录音电平
        self.chunk_sec = chunk_sec
        self._chunks = []                 # 实时录音帧（草稿快照后清空，内存有界于一个草稿窗口）
        self._all_parts = []              # 已被草稿快照消费的音频段：stop() 的最终转写需要全程音频
        self._stream = None
        self._lock = threading.Lock()
        self._draft_thread = None
        self._stop_draft = threading.Event()
        self._draft_done = threading.Event()  # 草稿线程真正退出时置位（保留供诊断，stop() 不再等待）
        self._offset_samples = 0          # 本窗口内已消费样本数（快照后恒为 0）
        self._draft_busy = False
        self._epoch = 0                   # 会话代数：stop() 递增使残留的旧 draft 循环立即退出
        self._speaking_fast = False       # 快速说话指示：音频回调线程逐帧更新，主线程只读
        self._last_bands = None           # 最近一帧的频带电平（0~1 形状）：回调线程写，主线程只读
        self._win_cache = {}              # 汉宁窗缓存（按帧长）：避免每帧重复生成
        self.vad = VAD()

    def start(self):
        with self._lock:
            self._chunks = []
            self._all_parts = []
            self._offset_samples = 0
            self._speaking_fast = False
            self._last_bands = None
            self._epoch += 1
            epoch = self._epoch
        self._stop_draft.clear()
        self._draft_done.clear()
        self.vad.reset()
        stream = sd.InputStream(
            samplerate=self.samplerate, channels=1, dtype="float32",
            device=self.device or None,
            blocksize=320,  # 20ms/帧：频谱与波形更新更细腻（原默认块可能达 100~200ms）
            callback=self._callback,
        )
        with self._lock:
            self._stream = stream
        try:
            stream.start()
        except Exception:
            # v5.11：设备被占用/不可用时清理已创建的流，避免泄漏
            with self._lock:
                self._stream = None
            try:
                stream.close()
            except Exception:
                pass
            raise
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
        # 每帧计算一次 RMS 电平（帧长约 20ms），归一化后更新快速说话指示。
        # v5.11：RMS 计算与 on_level 回调分开 try，失败来源不再混淆；
        # 回调抛异常必须静默吞掉，绝不影响录音主流程
        try:
            rms = float(np.sqrt(np.mean(indata ** 2)))
            rms_01 = min(rms / self.RMS_NORMALIZE, 1.0)
        except Exception:
            logging.exception("RMS 计算异常（已忽略，不影响录音）")
            rms_01 = None
        if rms_01 is not None:
            if rms_01 >= Recorder.SPEAK_ON_RMS_01:
                self._speaking_fast = True
            elif rms_01 <= Recorder.SPEAK_OFF_RMS_01:
                self._speaking_fast = False
            if self.on_level:
                try:
                    self.on_level(rms_01)
                except Exception:
                    logging.exception("on_level 回调异常（已忽略，不影响录音）")
        # 每帧计算频带电平（FFT）：失败不影响录音主流程
        try:
            bands = self._compute_bands(indata)
            if bands is not None:
                self._last_bands = bands  # 整表引用替换，跨线程读安全（GIL 原子）
        except Exception:
            logging.exception("频带计算异常（已忽略，不影响录音）")

    def _compute_bands(self, indata):
        """计算对数频带（80Hz~8kHz）的相对电平，返回 0~1 形状列表。

        只返回"形状"（按本帧峰值归一化），响度增益由 UI 用 RMS 再乘一次，
        避免安静帧的形状被放大成满幅；帧太短或无能量时返回 None。
        """
        x = np.asarray(indata, dtype=np.float32).flatten()
        n = x.size
        if n < 64:
            return None
        x = x - float(np.mean(x))  # 去直流，避免低频假能量
        win = self._win_cache.get(n)
        if win is None:
            win = np.hanning(n).astype(np.float32)  # 加窗减少频谱泄漏
            self._win_cache[n] = win
        spec = np.abs(np.fft.rfft((x * win).astype(np.float32)))
        freqs = np.fft.rfftfreq(n, 1.0 / self.samplerate)
        edges = np.geomspace(80.0, 8000.0, self.SPECTRUM_BANDS + 1)
        levels = np.empty(self.SPECTRUM_BANDS, dtype=np.float32)
        for i in range(self.SPECTRUM_BANDS):
            # v5.11：末频带包含 8kHz 端点（rfftfreq 末 bin 恰为 sr/2），
            # 避免最高频 bin 因 `freqs < 8000` 被漏掉
            if i == self.SPECTRUM_BANDS - 1:
                mask = (freqs >= edges[i]) & (freqs <= edges[i + 1])
            else:
                mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
            idx = np.flatnonzero(mask)
            levels[i] = float(np.mean(spec[idx])) if idx.size else 0.0
        peak = float(levels.max())
        if peak <= 1e-9:
            return None
        levels /= peak
        return [float(v) for v in levels]

    def _draft_loop(self, epoch):
        chunk_samples = int(self.chunk_sec * self.samplerate)
        try:
            while not self._stop_draft.is_set():
                with self._lock:
                    # 会话代数变更（stop/start）后残留线程立即退出（锁内读取，避免数据竞争）
                    if epoch != self._epoch:
                        break
                    if self._draft_busy:
                        busy, take = True, False
                    else:
                        busy, take = False, False
                        total = sum(c.shape[0] for c in self._chunks)
                        if total - self._offset_samples >= chunk_samples:
                            # 检查与置位在同一锁内完成：杜绝 check-then-act 竞态
                            self._draft_busy = True
                            take = True
                if not busy and take:
                    try:
                        data = self._snapshot_from_offset(epoch)
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

    def _snapshot_from_offset(self, epoch):
        """快照未消费音频并清空 _chunks：每次只拷贝一个窗口（O(窗口)）。

        原实现每次草稿都 np.concatenate 整个录音历史（累积 O(n²) 拷贝 + 无界 _chunks）。
        消费段移入 _all_parts 保留：stop() 的最终转写仍需要全程音频（功能不变），
        因此全程内存不可避免（见 README 取舍说明），但每段音频只被拷贝一次、_chunks 有界。

        epoch 在锁内二次校验：stop() 之后残留的草稿线程即使已通过循环顶部的检查，
        也会在这里被挡掉，绝不消费/污染新会话或停止后的缓冲。
        """
        with self._lock:
            if epoch != self._epoch or not self._chunks:
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
        # v5.16（m4）：锁内读取并清空 stream，锁外 stop/close，
        # 消除与 active 属性（锁内读 _stream）之间的 TOCTOU
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream:
            stream.stop()
            stream.close()
        self._stop_draft.set()
        # v5.5：不再等待草稿线程退出。原实现 join(≤2s) 会卡在 in-flight 的
        # on_draft（增量转写可能耗时 1~2s），导致"按完成键后迟迟不转写"。
        # 音频收集与草稿快照共用同一把锁，且快照在锁内做 epoch 二次校验，
        # 因此 stop() 可以直接安全拼接全程音频，残留线程由 epoch/stop 信号隔离。
        with self._lock:
            self._epoch += 1
        self._draft_thread = None
        with self._lock:
            parts = self._all_parts
            if self._chunks:
                parts = parts + [np.concatenate(self._chunks).flatten()]
            data = np.concatenate(parts) if parts else np.empty(0, dtype=np.float32)
        return data.flatten()

    @property
    def speaking_now(self):
        """快速说话指示（bool）：音频回调线程逐帧更新，主线程只读。

        用于悬浮窗声波显示：响应速度远快于 VAD 的去抖判定，
        说话立即亮波形、停口立即灭波形（约 1 帧延迟）。
        """
        return self._speaking_fast

    @property
    def active(self):
        """录音流是否开启（start() 之后、stop() 之前为 True）。

        用于主线程轮询守卫：状态机已切到 RECORDING 但新 Recorder 尚未创建时，
        避免对上一会话已停止的 recorder 误触发静音自动停止（v5.11）。
        """
        with self._lock:
            return self._stream is not None

    @property
    def bands_now(self):
        """最近一帧的频带电平（0~1 形状列表，长度 SPECTRUM_BANDS）。

        由音频回调线程整表替换更新；主线程读取引用是安全的。
        尚无数据（录音刚开始/帧过短）时返回 None。
        """
        return self._last_bands

    @property
    def duration(self):
        # 全程时长 = 已消费段 + 实时帧（_chunks 被草稿清空后只含最新窗口）
        with self._lock:
            total = sum(p.shape[0] for p in self._all_parts) + sum(
                c.shape[0] for c in self._chunks
            )
            return total / self.samplerate

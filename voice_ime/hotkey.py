"""全局热键监听：单击触发切换（toggle）。回调通过工作线程异步派发，不阻塞 pynput 监听线程。"""
import logging
import queue
import threading
import time

from pynput import keyboard

_log = logging.getLogger(__name__)

_SPECIAL = {
    "ctrl_l": keyboard.Key.ctrl_l, "ctrl_r": keyboard.Key.ctrl_r,
    "alt_l": keyboard.Key.alt_l, "alt_r": keyboard.Key.alt_r,
    "shift_l": keyboard.Key.shift_l, "shift_r": keyboard.Key.shift_r,
    "f1": keyboard.Key.f1, "f2": keyboard.Key.f2, "f3": keyboard.Key.f3,
    "f4": keyboard.Key.f4, "f5": keyboard.Key.f5, "f6": keyboard.Key.f6,
    "f7": keyboard.Key.f7, "f8": keyboard.Key.f8, "f9": keyboard.Key.f9,
    "f10": keyboard.Key.f10, "f11": keyboard.Key.f11, "f12": keyboard.Key.f12,
    "caps_lock": keyboard.Key.caps_lock, "space": keyboard.Key.space,
    "enter": keyboard.Key.enter, "esc": keyboard.Key.esc,
}

# 热键配置名 → 用户可读文案（托盘/悬浮窗提示用）
HOTKEY_LABELS = {
    "alt_r": "右 Alt",
    "alt_l": "左 Alt",
    "ctrl_r": "右 Ctrl",
    "ctrl_l": "左 Ctrl",
    "shift_r": "右 Shift",
    "shift_l": "左 Shift",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5", "f6": "F6",
    "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
    "caps_lock": "Caps Lock", "space": "空格", "enter": "回车", "esc": "Esc",
}


def parse_key(key_name):
    """把配置键名解析为 pynput 键对象；未知/非法返回 None（M6）。

    注意：pynput 的 KeyCode.from_char 对任意字符串都不抛异常（如 "bogus" 会生成
    一个永远匹配不上的 KeyCode），因此这里必须显式校验：白名单特殊键 + 单字符键。
    """
    if not isinstance(key_name, str) or not key_name:
        return None
    if key_name in _SPECIAL:
        return _SPECIAL[key_name]
    if len(key_name) != 1:
        return None
    try:
        return keyboard.KeyCode.from_char(key_name)
    except Exception:
        return None

# 防抖窗口（秒）：两次按下间隔小于该值视为双击误触，直接忽略。
# 原因：toggle 模式下"按一下=切换一次"，Windows 的键盘自动重复
# 或用户快速双击都会触发多次 on_press，200ms 防抖可保证一次单击只切换一次。
_DEBOUNCE_SEC = 0.2

# 工作线程停止哨兵
_STOP = object()


class HotkeyListener:
    """单击触发切换的热键监听：按下事件触发一次 on_toggle()，不依赖按住/松开配对。"""

    def __init__(self, key_name, on_toggle):
        # 主键 + 别名：Windows 上右 Alt 常被 pynput 报告为 Key.alt_gr（AltGr），
        # 因此 alt_r 配置需要同时匹配两者，否则用户按右 Alt 永远无法触发。
        key = parse_key(key_name)
        if key is None:
            raise ValueError("未知/不支持的热键: {!r}".format(key_name))
        self.keys = {key}
        if key_name == "alt_r":
            self.keys.add(keyboard.Key.alt_gr)
        self.on_toggle = on_toggle
        self._last_time = 0.0  # 上次触发时刻（monotonic），用于防抖
        self._lock = threading.Lock()  # 保护 _last_time 的读-改-写
        self._life_lock = threading.Lock()  # v5.11：保护 start/stop 生命周期状态
        self.listener = None
        self._task_queue: queue.Queue = queue.Queue(maxsize=16)
        self._worker: threading.Thread | None = None
        self._gen = 0  # 工作线程代数：stop() 递增使残留线程退出，避免新旧 worker 并发

    def start(self):
        with self._life_lock:
            if self.listener is not None:
                return  # 已在运行，避免创建重复监听器
            self._last_time = 0.0  # v5.11：重启后防抖窗口清零
            # 启动工作线程，从队列取 toggle 请求并串行执行
            self._gen += 1
            gen = self._gen
            self._task_queue = queue.Queue(maxsize=16)
            self._worker = threading.Thread(
                target=self._run_worker, args=(self._task_queue, gen),
                daemon=True, name="hotkey-worker",
            )
            self._worker.start()
            self.listener = keyboard.Listener(on_press=self._on_press)
            self.listener.daemon = True
            self.listener.start()

    def stop(self):
        with self._life_lock:
            if threading.current_thread() is self._worker:
                # v5.11：worker 线程内调用 stop 时不能 join 自身（会 RuntimeError），
                # 只递增代数并投递哨兵，让本线程在下次循环退出
                self._gen += 1
                self._task_queue.put(_STOP)
                return
            if self.listener:
                self.listener.stop()
                try:
                    self.listener.join(timeout=1.0)
                except Exception:
                    pass
                # v5.14：join 超时也清空引用，允许 start() 重建监听器；
                # 残留线程是 daemon，最坏情况只是多一个已停止的监听线程
                self.listener = None
            # 通知工作线程退出
            if self._worker is not None and self._worker.is_alive():
                self._gen += 1  # 残留线程（若 join 超时）下次循环即退出，不会消费新队列
                self._task_queue.put(_STOP)
                self._worker.join(timeout=2.0)
                if not self._worker.is_alive():
                    self._worker = None

    def _run_worker(self, task_queue, gen):
        """工作线程：只消费启动时绑定的队列；代数变化（stop/start）后立即退出。"""
        while True:
            if gen != self._gen:
                break
            try:
                item = task_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if item is _STOP:
                break
            try:
                self.on_toggle()
            except Exception:
                _log.exception("HotkeyListener.on_toggle 回调异常")

    def _on_press(self, key):
        if key not in self.keys:
            return
        now = time.monotonic()
        # 防抖：事件间隔 <200ms 忽略，防止双击误触 / 系统按键重复造成连切
        with self._lock:
            if now - self._last_time < _DEBOUNCE_SEC:
                return
            self._last_time = now
        # 派发到工作线程，绝不阻塞 pynput 监听线程。
        # v5.14：锁内取队列引用，避免 start()/stop() 换队列时把事件投进旧队列丢失
        with self._life_lock:
            q = self._task_queue
        # v5.11：有界队列（maxsize=16）背压生效——满则丢弃本次，避免阻塞监听线程
        try:
            q.put_nowait(key)
        except queue.Full:
            pass

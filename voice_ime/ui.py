"""
Windows 桌面悬浮窗 ——「胶囊 + 音频波」极简形态
修复字体错位：统一用单个 Canvas 重绘全部内容（背景、波形、文字），
每次绘制前 update_idletasks() 获取实际窗口尺寸，避免 geometry 未刷新导致的坐标偏移。
"""

import ctypes
import math
import random
import threading
import time
import tkinter as tk

# ── Win32 常量 ────────────────────────────────────────────────────
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

# ── 配色 ──────────────────────────────────────────────────────────
BG_DARK = '#1E1E1E'          # 胶囊深色背景
FONT_FAMILY = 'Microsoft YaHei UI'

# ── 各状态配置：尺寸 / 默认文字 / 主题色 ──────────────────────────
STATE_CONFIG = {
    'RECORDING':    {'text': '',                  'color': '#4A90D9', 'w': 150, 'h': 52},
    'TRANSCRIBING': {'text': '✍️ 转写中',         'color': '#F39C12', 'w': 150, 'h': 52},
    'REFINING':     {'text': '✨ 润色中',         'color': '#9B59B6', 'w': 150, 'h': 52},
    'INJECTING':    {'text': '⬇️ 注入中',         'color': '#3498DB', 'w': 150, 'h': 52},
    'PREVIEW':      {'text': None,                'color': '#27AE60', 'w': 380, 'h': 80},
    'ERROR':        {'text': None,                'color': '#E74C3C', 'w': 380, 'h': 80},
}

# ── 音频波参数 ────────────────────────────────────────────────────
WAVE_BAR_COUNT = 5          # 竖条数
WAVE_BAR_WIDTH = 3          # 每条宽度 px
WAVE_BAR_GAP = 5            # 条间距 px
WAVE_MIN_HEIGHT = 4         # 静默最低高度 px
WAVE_MAX_HEIGHT = 26        # 满幅最高高度 px


# ═══════════════════════════════════════════════════════════════════
# Canvas 辅助 —— 圆角矩形
# ═══════════════════════════════════════════════════════════════════

def _rounded_rect(canvas, x1, y1, x2, y2, radius=16, **kwargs):
    """在 Canvas 上绘制填充圆角矩形（单图元，smooth 曲线逼近圆角）。

    将四个角用密集的圆弧点替代直角顶点，配合 smooth=True
    生成视觉上足够平滑的胶囊圆角。
    """
    r = radius
    # 构建多边形点序列：从左上角圆弧开始顺时针绕一圈
    points = []
    steps = 8  # 每个圆角采样点数
    # 左上角
    for i in range(steps + 1):
        angle = math.pi + (math.pi / 2) * (i / steps)
        points.extend([x1 + r + r * math.cos(angle),
                       y1 + r + r * math.sin(angle)])
    # 右上角
    for i in range(steps + 1):
        angle = math.pi * 1.5 + (math.pi / 2) * (i / steps)
        points.extend([x2 - r + r * math.cos(angle),
                       y1 + r + r * math.sin(angle)])
    # 右下角
    for i in range(steps + 1):
        angle = 0 + (math.pi / 2) * (i / steps)
        points.extend([x2 - r + r * math.cos(angle),
                       y2 - r + r * math.sin(angle)])
    # 左下角
    for i in range(steps + 1):
        angle = math.pi / 2 + (math.pi / 2) * (i / steps)
        points.extend([x1 + r + r * math.cos(angle),
                       y2 - r + r * math.sin(angle)])
    return canvas.create_polygon(points, smooth=True, **kwargs)


# ═══════════════════════════════════════════════════════════════════
# Overlay
# ═══════════════════════════════════════════════════════════════════

class Overlay:
    """极简胶囊悬浮窗 —— 单 Canvas 全量重绘，根除布局错位。

    接口：
        overlay = Overlay()
        overlay.show('RECORDING')
        overlay.set_level(0.7)   # 驱动波形
        overlay.hide()

    show/hide/set_level 均可安全地从任意线程调用（内部自动路由到 Tk 主线程）。
    """

    def __init__(self, root=None):
        # 立即创建一个隐藏的 Tk 根窗口作为"锚点"，确保所有线程的
        # after() 调用都能正确路由到主线程。避免首次 show() 从
        # 工作线程调用时在错误的线程上创建 Tk 解释器。
        self._root = tk.Tk()
        self._root.withdraw()
        self._canvas = None
        self._menu = None
        self._anim_job = None
        self._active = False
        self._state = 'RECORDING'
        self._text = ''
        self._rms = 0.0          # 外部传入 RMS（0~1）
        self._smooth_rms = 0.0   # 平滑 RMS，驱动波形
        self._phase = 0.0        # 呼吸动画相位

    # ═══════════════════════════════════════════════════════════════
    # 窗口创建（惰性，仅一次）
    # ═══════════════════════════════════════════════════════════════

    def _ensure_window(self):
        """确保 Canvas 等组件已创建（首次调用时初始化）。"""
        if self._canvas is not None:
            return
        root = self._root
        root.overrideredirect(True)
        root.attributes('-topmost', True)
        root.configure(bg=BG_DARK)

        # 窗口就绪后应用 WS_EX_NOACTIVATE
        root.after(50, self._apply_no_activate)

        # 唯一布局组件：Canvas 填满整个窗口
        canvas = tk.Canvas(root, bg=BG_DARK, highlightthickness=0)
        canvas.pack(fill='both', expand=True)

        # 右键菜单
        menu = tk.Menu(root, tearoff=0)
        menu.add_command(label='退出', command=self._safe_exit)
        root.bind('<Button-3>', lambda e: menu.post(e.x_root, e.y_root))

        self._root = root
        self._canvas = canvas
        self._menu = menu

    def _apply_no_activate(self):
        """注入 WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW，确保不抢焦点。

        对于 overrideredirect(True) 窗口，winfo_id() 直接返回顶层 HWND，
        无需 GetParent（后者可能返回内部包装窗口导致样式不生效）。
        """
        if not self._root or not self._root.winfo_exists():
            return
        try:
            hwnd = self._root.winfo_id()
            if not hwnd:
                return
            # 注册 argtypes/restype 防止 64 位句柄截断
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long
            # 用带 use_last_error 的句柄获取可靠错误码（默认 windll 不支持 get_last_error）
            _u32 = ctypes.WinDLL("user32", use_last_error=True)
            _u32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            _u32.SetWindowLongW.restype = ctypes.c_long
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_ex = ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            result = _u32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex)
            # SetWindowLongW 成功时返回旧样式值（0 也是合法旧值），
            # 只有返回 0 且 GetLastError 非 0 才是真失败
            err = ctypes.get_last_error()
            if result == 0 and err != 0:
                import logging
                logging.getLogger(__name__).warning(
                    f"设置 WS_EX_NOACTIVATE 失败（hwnd={hwnd}, GLE={err}）"
                )
        except (AttributeError, OSError) as e:
            import logging
            logging.getLogger(__name__).warning(
                f"_apply_no_activate 异常: {e}"
            )

    # ═══════════════════════════════════════════════════════════════
    # 公开 API（线程安全：自动路由到 Tk 主线程）
    # ═══════════════════════════════════════════════════════════════

    def show(self, state, text=''):
        """显示悬浮窗（可从任意线程安全调用）。"""
        self._root.after(0, self._show_impl, state, text)

    def hide(self):
        """隐藏悬浮窗（可从任意线程安全调用）。"""
        self._root.after(0, self._hide_impl)

    def set_level(self, rms):
        """外部传入音频 RMS 值（0~1 归一化范围），驱动波形跳动。

        RECORDING 状态下每次调用只记录；动画循环约 30fps 消费它。
        非 RECORDING 状态下调用无效果。
        可从任意线程安全调用（float 赋值在 CPython GIL 下是原子的）。
        """
        self._rms = max(0.0, min(1.0, rms))

    # ═══════════════════════════════════════════════════════════════
    # 内部实现（必须在 Tk 主线程调用）
    # ═══════════════════════════════════════════════════════════════

    def _show_impl(self, state, text):
        """show() 的实际实现——必须在 Tk 主线程调用。"""
        self._ensure_window()
        self._stop_anim()
        self._active = True
        self._state = state
        self._text = text
        self._smooth_rms = 0.0   # 每次 show 重置平滑值

        cfg = STATE_CONFIG[state]
        w, h = cfg['w'], cfg['h']

        # 1. 先映射窗口：withdraw 状态下 geometry() 不生效，
        #    不先 deiconify 会读到窗口旧尺寸（如首次 378x265），
        #    导致定位与绘制全错（"第二次录音错位"根因）
        self._root.geometry(f'{w}x{h}')
        self._root.deiconify()
        self._root.update_idletasks()

        # 2. 窗口已映射，读取实际尺寸（稳健防抖）
        actual_w = self._root.winfo_width()
        actual_h = self._root.winfo_height()
        if actual_w > 1:    # 用实际尺寸覆盖目标尺寸
            w = actual_w
        if actual_h > 1:
            h = actual_h
        self._canvas.config(width=w, height=h)

        # 3. 居中靠下定位（在绘制前，确保后续绘制基于最终坐标）
        self._center_bottom()

        # 4. 绘制内容
        self._draw(w, h, state, text)

    def _hide_impl(self):
        """hide() 的实际实现——必须在 Tk 主线程调用。"""
        self._stop_anim()
        self._active = False
        if self._root:
            self._root.withdraw()

    # ═══════════════════════════════════════════════════════════════
    # 定位
    # ═══════════════════════════════════════════════════════════════

    def _center_bottom(self):
        """将窗口置于屏幕底部居中，距底边 80px。"""
        self._root.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w = self._root.winfo_width()
        h = self._root.winfo_height()
        x = (sw - w) // 2
        y = sh - h - 80
        self._root.geometry(f'+{x}+{y}')

    # ═══════════════════════════════════════════════════════════════
    # 绘制（单 Canvas，每次全量重绘，根除错位）
    # ═══════════════════════════════════════════════════════════════

    def _draw(self, w, h, state, text):
        """基于实际窗口尺寸 w×h 全量重绘 Canvas。"""
        c = self._canvas
        c.delete('all')

        # 背景胶囊（圆角 16px 深色底）
        _rounded_rect(c, 0, 0, w, h, radius=16, fill=BG_DARK, outline='')

        cfg = STATE_CONFIG[state]

        if state == 'RECORDING':
            # 录音中：纯波形，无文字，30fps 动画
            self._anim_job = self._root.after(33, self._tick_recording, w, h)
        elif state in ('TRANSCRIBING', 'REFINING'):
            # 转写/润色：文字 + 右侧呼吸点动画
            self._draw_text_center(c, w, h, cfg['text'], cfg['color'], font_size=11)
            self._anim_job = self._root.after(50, self._tick_dot, w, h, cfg['color'])
        elif state == 'INJECTING':
            # 注入中：纯文字，无动画
            self._draw_text_center(c, w, h, cfg['text'], cfg['color'], font_size=11)
        elif state in ('PREVIEW', 'ERROR'):
            # 预览/错误：外部文字，截断约 40 字
            display = text[:40] + ('…' if len(text) > 40 else '')
            self._draw_text_center(c, w, h, display, cfg['color'],
                                   font_size=10, wraplength=w - 40)

    def _draw_text_center(self, canvas, w, h, text, color,
                          font_size=11, wraplength=None):
        """在 Canvas 中央绘制文字。"""
        if not text:
            return
        canvas.create_text(
            w // 2, h // 2,
            text=text,
            fill=color,
            font=(FONT_FAMILY, font_size),
            width=wraplength,
            anchor='center',
        )

    def _draw_wave_bars(self, w, h, rms):
        """在 Canvas 上绘制 5 根竖条音频波。

        Args:
            w, h: 窗口宽高
            rms: 平滑后的 RMS（0~1），驱动基准高度
        """
        c = self._canvas
        color = STATE_CONFIG['RECORDING']['color']

        # 基于 RMS 计算基准高度
        base_h = WAVE_MIN_HEIGHT + (WAVE_MAX_HEIGHT - WAVE_MIN_HEIGHT) * rms

        # 竖条组居中
        total_w = WAVE_BAR_COUNT * WAVE_BAR_WIDTH + (WAVE_BAR_COUNT - 1) * WAVE_BAR_GAP
        start_x = (w - total_w) // 2
        bar_center_y = h // 2

        for i in range(WAVE_BAR_COUNT):
            # 每根加随机抖动，模拟真实音频频谱
            if rms > 0.05:
                jitter = random.uniform(-0.5, 0.5) * base_h
            else:
                jitter = random.uniform(0, 1.5)  # 静默时微量随机呼吸
            bar_h = max(WAVE_MIN_HEIGHT, base_h + jitter)
            bar_h = min(WAVE_MAX_HEIGHT, bar_h)

            x1 = start_x + i * (WAVE_BAR_WIDTH + WAVE_BAR_GAP)
            x2 = x1 + WAVE_BAR_WIDTH
            y1 = bar_center_y - bar_h // 2
            y2 = bar_center_y + bar_h // 2

            # 竖条（小圆角 2px）
            _rounded_rect(c, x1, y1, x2, y2, radius=2, fill=color, outline='')

    # ═══════════════════════════════════════════════════════════════
    # 动画帧
    # ═══════════════════════════════════════════════════════════════

    def _tick_recording(self, w, h):
        """录音波形动画帧（~30 fps）。"""
        if not self._active or self._state != 'RECORDING':
            return

        # 低通滤波平滑 RMS
        self._smooth_rms += (self._rms - self._smooth_rms) * 0.3

        # 无数据时微弱呼吸效果
        if self._smooth_rms < 0.02:
            self._smooth_rms = 0.03 + 0.03 * math.sin(self._phase)
            self._phase += 0.12

        # 全量重绘：背景 + 波形
        c = self._canvas
        c.delete('all')
        _rounded_rect(c, 0, 0, w, h, radius=16, fill=BG_DARK, outline='')
        self._draw_wave_bars(w, h, self._smooth_rms)

        self._anim_job = self._root.after(33, self._tick_recording, w, h)

    def _tick_dot(self, w, h, color):
        """非录音状态呼吸点动画（~20 fps）。"""
        if not self._active:
            return

        self._phase += 0.08
        a = 0.3 + 0.4 * (1 + math.sin(self._phase))  # 亮度在 0.3~1.0 间震荡

        c = self._canvas
        c.delete('all')

        # 背景
        _rounded_rect(c, 0, 0, w, h, radius=16, fill=BG_DARK, outline='')

        # 文字
        cfg = STATE_CONFIG.get(self._state)
        if cfg and cfg['text']:
            self._draw_text_center(c, w, h, cfg['text'], cfg['color'], font_size=11)

        # 右侧呼吸点
        dot_r = 3 + 2 * a
        dot_x = w - 26
        dot_y = h // 2
        hex_c = color.lstrip('#')
        cr, cg, cb = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
        fr = int(0x1E + (cr - 0x1E) * a)
        fg = int(0x1E + (cg - 0x1E) * a)
        fb = int(0x1E + (cb - 0x1E) * a)
        dot_fill = f'#{fr:02x}{fg:02x}{fb:02x}'
        c.create_oval(dot_x - dot_r, dot_y - dot_r,
                      dot_x + dot_r, dot_y + dot_r,
                      fill=dot_fill, outline='')

        self._anim_job = self._root.after(50, self._tick_dot, w, h, color)

    def _stop_anim(self):
        """停止动画定时器。"""
        if self._anim_job and self._root:
            self._root.after_cancel(self._anim_job)
        self._anim_job = None

    # ═══════════════════════════════════════════════════════════════
    # 退出
    # ═══════════════════════════════════════════════════════════════

    def _safe_exit(self):
        """安全退出：停止动画 → 销毁窗口 → 清空引用（通过 after 路由到 Tk 主线程）。"""
        def _do_exit():
            self._stop_anim()
            self._active = False
            if self._root:
                self._root.destroy()
                self._root = None
                self._canvas = None
        if self._root:  # 窗口可能已被销毁/从未创建，先判空再调度
            self._root.after(0, _do_exit)

    _exit = _safe_exit  # 兼容旧接口

    def run(self):
        """阻塞式 Tk 主循环（仅预览用）。"""
        if self._root:
            self._root.mainloop()


# ═══════════════════════════════════════════════════════════════════
# 预览 / 演示（if __name__ == '__main__'）
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    overlay = Overlay()

    def demo():
        """模拟完整工作流：录音 → 各状态 → 再次录音（验证无错位）。"""
        # ── 阶段 1：录音，随机 RMS 驱动波形约 5 秒 ──
        overlay.show('RECORDING')
        start = time.time()
        while time.time() - start < 5:
            rms = random.uniform(0.1, 0.9)  # 模拟说话
            overlay.set_level(rms)
            time.sleep(0.08)
        overlay.set_level(0.0)  # 安静
        time.sleep(0.8)

        # ── 阶段 2：依次展示其他状态 ──
        demo_states = [
            ('TRANSCRIBING', ''),
            ('REFINING', ''),
            ('INJECTING', ''),
            ('PREVIEW', '你好世界，这是语音识别结果的预览文本'),
            ('ERROR', '识别失败：网络连接超时请重试'),
        ]
        for s, t in demo_states:
            overlay.show(s, t)
            time.sleep(2.5)

        # ── 阶段 3：再次录音，验证连续切换无错位 ──
        overlay.show('RECORDING')
        start = time.time()
        while time.time() - start < 4:
            rms = random.uniform(0.1, 0.95)
            overlay.set_level(rms)
            time.sleep(0.08)
        overlay.set_level(0.0)
        time.sleep(0.5)

        overlay.hide()
        overlay._safe_exit()

    threading.Thread(target=demo, daemon=True).start()
    overlay.run()

# -*- coding: utf-8 -*-
"""Qt 版悬浮胶囊原型：置顶、不抢焦点、三态动画。

对外接口与现有 voice_ime/ui.py 的 Overlay 保持一致：
    show(state, text="") / hide() / set_level(rms) / set_speaking(bool) / set_levels(list)
这样后续可以直接替换 Tk 实现，App 不需要改调用方式。
"""
import ctypes
import math

from PySide6.QtCore import QPoint, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from .theme import (
    BG_DARK,
    FONT_FAMILY,
    STATE_CONFIG,
    WAVE_BAR_COUNT,
    WAVE_BAR_GAP,
    WAVE_BAR_WIDTH,
    WAVE_MAX_HEIGHT,
    WAVE_MIN_HEIGHT,
)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


class QtOverlay(QWidget):
    """无边框胶囊。用 Win32 扩展样式确保显示时不激活、不抢输入焦点。"""

    def __init__(self, max_chars=300, parent=None):
        super().__init__(parent)
        self._max_chars = max(int(max_chars), 10)
        self._state = "RECORDING"
        self._text = ""
        self._rms = 0.0
        self._smooth_rms = 0.0
        self._levels = None
        self._smooth_bands = None
        self._peak_bands = None
        self._speaking = False
        self._phase = 0.0

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    # ---------- 与 Tk Overlay 同名的公开接口 ----------
    def show(self, state="RECORDING", text=""):
        cfg = STATE_CONFIG.get(state, STATE_CONFIG["ERROR"])
        self._state = state
        self._text = text
        self._rms = 0.0
        self._smooth_rms = 0.0
        self._levels = None
        self._smooth_bands = None
        self._peak_bands = None
        self._speaking = False
        self.setFixedSize(cfg["w"], cfg["h"])
        self._move_bottom_center()
        QWidget.show(self)
        self._raise_no_activate()
        self._timer.start()

    def hide(self):
        self._timer.stop()
        super().hide()

    def set_level(self, rms):
        self._rms = max(0.0, min(1.0, float(rms)))

    def set_speaking(self, speaking):
        self._speaking = bool(speaking)

    def set_levels(self, levels):
        self._levels = list(levels) if levels else None

    # ---------- Win32：禁止激活 ----------
    def showEvent(self, event):
        super().showEvent(event)
        # 窗口真正创建后再改扩展样式；延迟一拍，避免 Qt 在 show 时重置样式
        QTimer.singleShot(0, self._raise_no_activate)

    def _raise_no_activate(self):
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            user32.SetWindowLongW.restype = ctypes.c_long
            ex = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
            user32.SetWindowLongW(
                ctypes.c_void_p(hwnd), GWL_EXSTYLE,
                ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
            )
        except Exception:
            pass

    def ex_style(self):
        """诊断用：返回当前 HWND 的扩展样式。"""
        hwnd = int(self.winId())
        return ctypes.windll.user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)

    # ---------- 位置与绘制 ----------
    def _move_bottom_center(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.bottom() - self.height() - 80
        self.move(QPoint(x, y))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())

        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        painter.fillPath(path, QColor(BG_DARK))

        cfg = STATE_CONFIG.get(self._state, STATE_CONFIG["ERROR"])
        if self._state == "RECORDING":
            self._draw_wave(painter)
        elif self._state in ("TRANSCRIBING", "REFINING"):
            self._draw_text(painter, cfg["text"], cfg["color"])
            self._draw_dot(painter, cfg["color"])
        elif self._state == "INJECTING":
            self._draw_text(painter, cfg["text"], cfg["color"])
        elif self._state in ("PREVIEW", "ERROR"):
            text = self._text[: self._max_chars]
            if len(self._text) > self._max_chars:
                text += "…"
            self._draw_text(painter, text, cfg["color"], font_size=10)

    def _draw_text(self, painter, text, color, font_size=11):
        if not text:
            return
        painter.setPen(QColor(color))
        font = QFont(FONT_FAMILY, font_size)
        painter.setFont(font)
        rect = QRectF(12, 0, self.width() - 24, self.height())
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

    def _draw_dot(self, painter, color):
        a = min(1.0, 0.35 + 0.45 * (math.sin(self._phase) + 1) / 2)
        c = QColor(color)
        c.setAlphaF(a)
        r = 3 + 2 * a
        cx, cy = self.width() - 22, self.height() // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(c)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    def _draw_wave(self, painter):
        n = WAVE_BAR_COUNT
        if self._speaking and self._levels is not None and len(self._levels) >= n:
            gain = min(1.0, math.sqrt(max(self._smooth_rms, 0.0)) * 1.2)
            raw = [min(1.0, self._levels[i] * gain) for i in range(n)]
        elif self._speaking:
            disp = min(1.0, math.sqrt(max(self._smooth_rms, 0.0)) * 1.2)
            raw = [disp] * n
        else:
            raw = None

        if raw is None:
            bands = [0.2 + 0.15 * math.sin(math.pi * (i + 0.5) / n) for i in range(n)]
            peaks = bands
        else:
            self._smooth_bands = (
                list(raw) if self._smooth_bands is None
                else [s + (lv - s) * 0.6 for s, lv in zip(self._smooth_bands, raw)]
            )
            if self._peak_bands is None:
                self._peak_bands = list(self._smooth_bands)
            else:
                self._peak_bands = [
                    max(s, p * 0.88) for s, p in zip(self._smooth_bands, self._peak_bands)
                ]
            peaks = self._peak_bands

        total_w = n * WAVE_BAR_WIDTH + (n - 1) * WAVE_BAR_GAP
        start_x = (self.width() - total_w) // 2
        cy = self.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(STATE_CONFIG["RECORDING"]["color"]))
        for i in range(n):
            env = 0.7 + 0.3 * math.sin(math.pi * (i + 0.5) / n)
            wobble = 0.06 * math.sin(self._phase * (1 + i * 0.15) + i * 0.9)
            lv = max(0.0, min(1.0, peaks[i] * env + wobble))
            h = WAVE_MIN_HEIGHT + (WAVE_MAX_HEIGHT - WAVE_MIN_HEIGHT) * lv
            x = start_x + i * (WAVE_BAR_WIDTH + WAVE_BAR_GAP)
            painter.drawRoundedRect(QRectF(x, cy - h / 2, WAVE_BAR_WIDTH, h), 2, 2)

    def _tick(self):
        self._phase += 0.18 if self._state == "RECORDING" else 0.08
        if self._speaking:
            self._smooth_rms += (self._rms - self._smooth_rms) * 0.6
        else:
            self._smooth_rms = 0.0
        self.update()

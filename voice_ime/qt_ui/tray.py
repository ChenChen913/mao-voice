# -*- coding: utf-8 -*-
"""Qt 托盘原型：状态文本 + 开始/打开/退出菜单。"""
from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .theme import ACCENT
from version import __version__

STATUS_LABELS = {
    "IDLE": "空闲", "RECORDING": "录音中", "PROCESSING": "处理中",
    "TRANSCRIBING": "转写中", "REFINING": "润色中", "PREVIEW": "预览",
    "INJECTING": "注入中", "ERROR": "错误",
}


def make_icon(size=64):
    """深色圆底 + 蓝色声波竖条，与 README 里的托盘图标一致。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1E1E1E"))
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.setBrush(QColor(ACCENT))
    bars = [(14, 22, 4, 20), (24, 14, 4, 36), (34, 10, 4, 44),
            (44, 14, 4, 36), (54, 22, 4, 20)]
    scale = size / 64
    for x, y, w, h in bars:
        painter.drawRoundedRect(
            int(x * scale), int(y * scale), max(2, int(w * scale)), int(h * scale), 2, 2
        )
    painter.end()
    return QIcon(pix)


class QtTray(QObject):
    """与现有 pystray 版 TrayIcon 同名方法：start / set_status / stop。"""

    def __init__(self, on_toggle=None, on_open=None, on_quit=None, on_pause=None):
        super().__init__()
        self._on_toggle = on_toggle
        self._on_open = on_open
        self._on_quit = on_quit
        self._on_pause = on_pause
        self._icon = None
        self._status = "IDLE"

    def start(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        self._icon = QSystemTrayIcon(make_icon(), None)
        self._icon.setToolTip("AI 语音输入法 v{}".format(__version__))

        menu = QMenu()
        act_toggle = QAction("开始/停止录音", menu)
        act_toggle.triggered.connect(lambda: self._call(self._on_toggle))
        act_open = QAction("打开控制台", menu)
        act_open.triggered.connect(lambda: self._call(self._on_open))
        act_pause = QAction("暂停热键", menu)
        act_pause.setCheckable(True)
        act_pause.triggered.connect(lambda checked: self._call(self._on_pause, checked))
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(lambda: self._call(self._on_quit))
        menu.addAction(act_toggle)
        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_pause)
        menu.addSeparator()
        menu.addAction(act_quit)

        self._icon.setContextMenu(menu)
        self._icon.show()
        self._set_tooltip()
        return True

    def _call(self, fn, *args):
        if fn:
            fn(*args)

    def _set_tooltip(self):
        if self._icon:
            self._icon.setToolTip(
                "AI 语音输入法 · " + STATUS_LABELS.get(self._status, self._status)
            )

    def set_status(self, state):
        self._status = state
        self._set_tooltip()

    def stop(self):
        if self._icon:
            self._icon.hide()
            self._icon = None

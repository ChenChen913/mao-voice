# -*- coding: utf-8 -*-
"""把 Qt 的 QTimer 包装成现有 App 需要的 root.after / root.quit 接口。

App 只用 root 做两件事：定时轮询（after）和退出（quit）。
这样引擎侧的状态机与线程模型可以原样复用，不必改 main.py。
"""
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication


class QtRoot(QObject):
    def after(self, ms, fn):
        QTimer.singleShot(max(0, int(ms)), fn)

    def quit(self):
        instance = QApplication.instance()
        if instance is not None:
            instance.quit()

# -*- coding: utf-8 -*-
"""Qt 客户端模块导入冒烟：不创建 QApplication，CI 无桌面环境也能跑。"""
import pytest

pytest.importorskip("PySide6")


def test_qt_client_modules_import():
    import qt_ui.client_app  # noqa: F401
    import qt_ui.main_window  # noqa: F401
    import qt_ui.overlay  # noqa: F401
    import qt_ui.root  # noqa: F401
    import qt_ui.tray  # noqa: F401

# -*- coding: utf-8 -*-
"""生成浅色主题截图（手动运行，不进 CI）。

用法：python tests/client_light_smoke.py
"""
import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(BASE))

# 必须在导入 qt_ui 之前设置：theme.py 在导入时读取该环境变量
os.environ["MAO_THEME"] = "light"

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from client_smoke import demo_modes_config, save_shot, seed_demo_history  # noqa: E402
from config import ensure_defaults, load_config  # noqa: E402
import qt_ui.main_window as mw  # noqa: E402
from qt_ui.main_window import MainWindow  # noqa: E402


def main():
    ensure_defaults()
    cfg = load_config()
    app = QApplication(sys.argv)
    demo = seed_demo_history()
    original = mw.HISTORY_PATH
    mw.HISTORY_PATH = str(demo)

    window = MainWindow()
    window.show_page("首页")
    QTest.qWait(200)
    save_shot(window, "client-home-light.png")

    window.show_page("设置")
    QTest.qWait(200)
    save_shot(window, "client-settings-light.png")

    window.show_page("模式")
    window.modes_page.load_modes(demo_modes_config(cfg))
    QTest.qWait(200)
    save_shot(window, "client-modes-light.png")

    mw.HISTORY_PATH = original
    shutil.rmtree(demo.parent, ignore_errors=True)
    app.quit()
    print("[通过] 浅色主题截图已生成")
    return 0


if __name__ == "__main__":
    sys.exit(main())

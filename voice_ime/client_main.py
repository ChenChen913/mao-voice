# -*- coding: utf-8 -*-
"""Qt 客户端入口：启动主窗口、悬浮胶囊、托盘与现有引擎。

运行：python client_main.py（或双击 启动客户端.bat）
和 Tk 版（main.py）共用 config.json / 词库.txt / 引擎模块，二者不要同时运行。
"""
import logging
import sys
import threading

from PySide6.QtCore import QSharedMemory
from PySide6.QtWidgets import QApplication

from asr import missing_local_model
from config import clamp_number, ensure_defaults, load_config
from hotkey import HotkeyListener, parse_key
from qt_ui.client_app import ClientApp
from qt_ui.main_window import MainWindow
from qt_ui.overlay import QtOverlay
from qt_ui.root import QtRoot
from qt_ui.tray import QtTray, make_icon
from version import __version__


def _setup_hotkeys(app_logic, cfg):
    """与 main.main 相同的热键策略：主热键 + 设置 + 强度切换，非法/冲突回退。"""
    listeners = []
    hotkey_name = cfg["hotkey"]
    if parse_key(hotkey_name) is None:
        print("[警告] 录音热键 {} 无效，已回退默认 alt_r".format(hotkey_name))
        hotkey_name = "alt_r"
        cfg["hotkey"] = hotkey_name
    hotkey = HotkeyListener(hotkey_name, app_logic.on_toggle)
    hotkey.start()
    listeners.append(hotkey)

    settings_key = cfg.get("settings_hotkey", "f8")
    if settings_key:
        if parse_key(settings_key) is None:
            print("[警告] 设置热键 {} 无效，已回退默认 f8".format(settings_key))
            settings_key = "f8"
        if settings_key != hotkey_name:
            h = HotkeyListener(settings_key, app_logic.open_settings)
            h.start()
            listeners.append(h)
            print("[设置] 按一下 {} 打开客户端设置".format(settings_key))
        else:
            print("[警告] 设置热键 {} 与录音热键冲突，未启动".format(settings_key))

    cycle_key = cfg.get("refine_cycle_hotkey", "f9")
    if cycle_key:
        if parse_key(cycle_key) is None:
            print("[警告] 润色切换热键 {} 无效，已回退默认 f9".format(cycle_key))
            cycle_key = "f9"
        if cycle_key != hotkey_name and cycle_key != settings_key:
            h = HotkeyListener(cycle_key, app_logic.on_cycle_refine)
            h.start()
            listeners.append(h)
            print("[设置] 按一下 {} 循环切换润色强度".format(cycle_key))
        else:
            print("[警告] 润色切换热键 {} 与录音/设置热键冲突，未启动".format(cycle_key))
    return listeners


def main():
    ensure_defaults()
    cfg = load_config()
    model = cfg.get("asr", {}).get("model", "")
    if missing_local_model(model):
        print("[警告] 模型未下载：{} 不存在，请先运行 python download_model.py".format(model))

    guard = QSharedMemory("mao-voice-client-single-instance")
    if not guard.create(1):
        print("[提示] mao-voice 客户端已在运行，本次启动退出")
        return 0

    qapp = QApplication(sys.argv)
    qapp.setApplicationName("mao-voice")
    qapp.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.setWindowIcon(make_icon())
    window.show()

    overlay = QtOverlay(
        max_chars=int(clamp_number(cfg.get("ui", {}).get("max_chars", 300), 300, lo=10))
    )
    root = QtRoot()
    app_logic = ClientApp(cfg, overlay, root, window)
    window.home.record_clicked.connect(app_logic.on_toggle)
    window.quit_requested.connect(app_logic.exit_app)

    if hasattr(app_logic.asr, "warmup"):
        threading.Thread(target=app_logic.asr.warmup, daemon=True).start()

    listeners = _setup_hotkeys(app_logic, cfg)

    def _on_settings_saved(payload):
        ok, msg = app_logic.apply_settings(payload)
        if ok:
            for h in listeners:
                h.stop()
            listeners[:] = _setup_hotkeys(app_logic, app_logic.cfg)
            msg = "已保存并应用，热键已重载"
        window.settings_page.show_result(ok, msg)

    window.settings_saved.connect(_on_settings_saved)

    def _open_window():
        window.show_page("首页")

    def _toggle_pause(paused):
        for h in listeners:
            h.stop() if paused else h.start()
        print("[设置] 热键已暂停" if paused else "[设置] 热键已恢复")

    app_logic.tray = QtTray(
        on_toggle=app_logic.on_toggle,
        on_open=_open_window,
        on_quit=app_logic.exit_app,
        on_pause=_toggle_pause,
    )
    if not app_logic.tray.start():
        print("[警告] 系统托盘不可用，客户端仍可使用主窗口")

    print("[就绪] mao-voice 客户端 v{} · 按一下 {} 开始录音。".format(__version__, cfg["hotkey"]))
    root.after(60, app_logic.poll_ui)
    root.after(300, app_logic._poll_recording)
    root.after(100, app_logic._poll_level)

    try:
        code = qapp.exec()
    finally:
        try:
            with app_logic._lock:
                if app_logic.state == "RECORDING" and app_logic.recorder is not None:
                    app_logic.recorder.stop()
        except Exception:
            logging.exception("退出时停止录音失败")
        for h in listeners:
            h.stop()
        if app_logic.tray is not None:
            app_logic.tray.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())

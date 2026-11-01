# -*- coding: utf-8 -*-
"""Qt 客户端 + 现有引擎的真机冒烟（手动运行，不进 CI）。

用真实麦克风录 1 秒，ASR/纠错/注入替换为确定性假实现，验证：
  1. 主窗口按钮能驱动 App 状态机；
  2. 悬浮胶囊在录音时出现、结束后隐藏；
  3. 胶囊显示期间前台窗口不变；
  4. 管线把最终文本交给注入函数。

用法：python tests/client_smoke.py
"""
import ctypes
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE.parent))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QPainter, QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402
from config import ensure_defaults, load_config  # noqa: E402
from qt_ui.client_app import ClientApp  # noqa: E402
from qt_ui.main_window import MainWindow  # noqa: E402
from qt_ui.overlay import QtOverlay  # noqa: E402
from qt_ui.root import QtRoot  # noqa: E402
from qt_ui.wizard import FirstRunWizard  # noqa: E402

OUT = BASE.parent / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)


class FakeVad:
    def silence_seconds(self):
        return 0


class FakeRecorder:
    """录音替身：不依赖麦克风，返回固定时长音频。"""

    def __init__(self, on_draft=None, on_level=None, device=None):
        self.duration = 1.2
        self.active = False
        self.vad = FakeVad()
        self.speaking_now = True
        self.bands_now = None

    def start(self):
        self.active = True

    def stop(self):
        self.active = False
        import numpy as np
        return np.zeros(19200, dtype=np.float32)


def save_shot(widget, name, scale=2):
    """按 2 倍像素渲染截图，README 缩放后文字依然清晰。"""
    pix = QPixmap(widget.size() * scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.scale(scale, scale)
    widget.render(painter, QPoint(0, 0))
    painter.end()
    pix.save(str(OUT / name))


def fg_hwnd():
    return int(ctypes.windll.user32.GetForegroundWindow())


def main_run():
    ensure_defaults()
    cfg = load_config()
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()
    overlay = QtOverlay()
    root = QtRoot()
    original_recorder = main.Recorder
    main.Recorder = FakeRecorder  # 用固定音频替身，避免依赖本机麦克风状态
    app = ClientApp(cfg, overlay, root, window)

    app.refiner = type("FakeRefiner", (), {
        "enabled": True,
        "refine": lambda self, raw, level=None, words_block="": raw + "。",
    })()
    app.asr.transcribe = lambda audio: "客户端冒烟测试"

    root.after(60, app.poll_ui)
    root.after(300, app._poll_recording)
    root.after(100, app._poll_level)

    injected = []
    original_inject = main.safe_inject.inject
    main.safe_inject.inject = lambda text, **kw: (
        injected.append(text) or (True, "注入成功（冒烟替身）")
    )

    QTest.qWait(300)
    before = fg_hwnd()
    app.on_toggle()
    QTest.qWait(500)
    during = fg_hwnd()
    print("recording_state={} recorder_active={}".format(
        app.state, bool(app.recorder and app.recorder.active)))
    recording_visible = overlay.isVisible()
    app.recorder.bands_now = [
        0.18, 0.32, 0.55, 0.78, 0.62, 0.95, 0.70, 0.48,
        0.88, 0.60, 0.36, 0.52, 0.28, 0.16, 0.10,
    ]
    app._last_rms = 0.9
    overlay.set_level(0.9)
    QTest.qWait(300)
    save_shot(overlay, "client-overlay-recording.png")
    app.on_toggle()

    deadline = time.time() + 5
    while app.state != "IDLE" and time.time() < deadline:
        QTest.qWait(100)

    # 截图前临时把首页状态切换为「就绪」，避免把本机未装模型的提示截进演示图
    window.home._model_ok = True
    window.set_status("IDLE")
    QTest.qWait(150)
    save_shot(window, "client-home.png")

    # 设置页：截图时把本机模型路径换成通用示例，避免把私有目录写进 README 截图。
    # 为了让「目录有效」状态真实出现，临时创建一份占位模型目录，截图后删除。
    fake_model = BASE / "models" / "faster-whisper-large-v3-turbo"
    created_fake = not fake_model.exists()
    if created_fake:
        fake_model.mkdir(parents=True, exist_ok=True)
        for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"):
            (fake_model / name).write_bytes(b"placeholder" * 40000)
    window.show_page("设置")
    window.settings_page.model.setText("models/faster-whisper-large-v3-turbo")
    QTest.qWait(200)
    save_shot(window, "client-settings.png")
    window.settings_page._set_section(2)
    QTest.qWait(200)
    save_shot(window, "client-settings-model.png")
    window.settings_page._set_section(0)
    payloads = []
    window.settings_saved.connect(payloads.append)
    window.settings_page.level.setCurrentIndex(1)  # light
    window.settings_page.save_btn.click()

    # 历史 / 词库页截图，便于检查空状态与表格布局
    window.show_page("历史")
    QTest.qWait(200)
    save_shot(window, "client-history.png")
    window.show_page("词库")
    QTest.qWait(200)
    save_shot(window, "client-dictionary.png")

    wizard = FirstRunWizard(cfg)
    wizard.show()
    QTest.qWait(150)
    save_shot(wizard, "client-wizard.png")
    wizard.close()

    settings_ok = bool(payloads) and payloads[0].get("refine", {}).get("level") == "light"

    hidden_after = not overlay.isVisible()
    print("state={} injected={!r}".format(app.state, injected))
    print("focus_before={} focus_during_overlay={} unchanged={}".format(
        before, during, before == during))
    print("overlay_visible_recording={} hidden_after={}".format(
        recording_visible, hidden_after))
    print("settings_payload={!r}".format(payloads[-1] if payloads else None))

    problems = []
    if app.state != "IDLE":
        problems.append("管线未回到 IDLE")
    if injected != ["客户端冒烟测试。"]:
        problems.append("注入文本不符合预期")
    if not recording_visible:
        problems.append("录音时胶囊未显示")
    if not hidden_after:
        problems.append("处理结束后胶囊未隐藏")
    if before != during:
        problems.append("胶囊显示时抢走了前台焦点")
    if not settings_ok:
        problems.append("设置页未产出正确的保存载荷")

    main.safe_inject.inject = original_inject
    main.Recorder = original_recorder
    if created_fake:
        shutil.rmtree(fake_model, ignore_errors=True)
        try:
            fake_model.parent.rmdir()
        except OSError:
            pass
    overlay.hide()
    qapp.quit()
    if problems:
        for p in problems:
            print("[失败] " + p)
        return 1
    print("[通过] Qt 客户端冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main_run())

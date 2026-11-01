# -*- coding: utf-8 -*-
"""首次启动向导：欢迎/隐私 → 麦克风试录 → 模型目录 → 热键与 Key。

设计目标：第一次运行不打开控制台也能完成最小配置；所有步骤都可跳过，
跳过时沿用默认配置，之后可在设置页补。
"""
import copy
import os

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from config import CONFIG_PATH
from hotkey import HOTKEY_LABELS
from model_store import resolve_model_path, scan_model_dirs, validate_model_dir
from recorder import list_input_devices
from .main_window import HOTKEYS
from .theme import (
    ERROR, FONT_MONO, FONT_FAMILY, ON_PRIMARY, OUTLINE, OUTLINE_VARIANT,
    PRIMARY, PRIMARY_HOVER, RADIUS, RADIUS_SM, SUCCESS, SURFACE,
    SURFACE_CONTAINER, SURFACE_HIGH, SURFACE_HIGHEST, SURFACE_LOW,
    SURFACE_LOWEST, TEXT, TEXT_VARIANT,
)

STEPS = ["欢迎", "麦克风", "识别模型", "热键与 Key"]


class FirstRunWizard(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = copy.deepcopy(cfg)
        self._step = 0
        self._stream = None
        self._peak = 0.0
        self._test_elapsed = 0.0
        self._test_timer = QTimer(self)
        self._test_timer.setInterval(50)
        self._test_timer.timeout.connect(self._tick_test)

        self.setObjectName("Root")
        self.setWindowTitle("mao-voice · 首次设置")
        self.setModal(True)
        self.setMinimumSize(720, 520)
        self.setStyleSheet(_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget()
        head.setObjectName("WizardHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(28, 20, 28, 16)
        hl.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(_rounded_logo(44))
        hl.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel("欢迎使用 mao-voice")
        self.title.setObjectName("H1")
        self.step_label = QLabel("第 1 步 / 共 4 步")
        self.step_label.setObjectName("Mono")
        titles.addWidget(self.title)
        titles.addWidget(self.step_label)
        hl.addLayout(titles)
        hl.addStretch(1)
        root.addWidget(head)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_welcome())
        self.stack.addWidget(self._page_mic())
        self.stack.addWidget(self._page_model())
        self.stack.addWidget(self._page_finish())
        root.addWidget(self.stack, 1)

        bottom = QFrame()
        bottom.setObjectName("Banner")
        bottom.setFixedHeight(64)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(20, 0, 20, 0)
        self.skip = QPushButton("跳过向导")
        self.skip.setObjectName("Ghost")
        self.skip.clicked.connect(self.reject)
        self.hint = QLabel("所有设置之后都能在「设置」里修改")
        self.hint.setObjectName("Mono")
        self.back = QPushButton("上一步")
        self.back.setObjectName("Ghost")
        self.back.clicked.connect(self._prev)
        self.back.setEnabled(False)
        self.next = QPushButton("下一步")
        self.next.setObjectName("Primary")
        self.next.clicked.connect(self._next)
        bl.addWidget(self.skip)
        bl.addWidget(self.hint)
        bl.addStretch(1)
        bl.addWidget(self.back)
        bl.addWidget(self.next)
        root.addWidget(bottom)

        self._populate(cfg)

    # ---------- 页面 ----------
    def _page_welcome(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)

        intro = QLabel(
            "按一下热键说话，文本会自动写入当前光标处；识别在本机运行。"
        )
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        lay.addWidget(intro)

        card = QFrame()
        card.setObjectName("Inner")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(10)
        title = QLabel("隐私与数据")
        title.setObjectName("H2")
        cl.addWidget(title)
        for text in (
            "音频只在内存中处理，默认不留存、不上传。",
            "语音识别使用你本机选择的 faster-whisper 模型。",
            "开启大模型纠错时，识别文本会发往你配置的端点。",
            "历史记录与学习规则默认关闭，均为明文落盘。",
        ):
            item = QLabel("•  " + text)
            item.setWordWrap(True)
            cl.addWidget(item)
        lay.addWidget(card)

        tip = QLabel("下一步会检测麦克风；没有设备也可以先跳过，进入系统后再配置。")
        tip.setObjectName("Mono")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        lay.addStretch(1)
        return page

    def _page_mic(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)

        desc = QLabel(
            "选择一个录音设备，并试录 2 秒。只要进度条出现跳动，就说明麦克风可用。"
        )
        desc.setWordWrap(True)
        desc.setObjectName("Muted")
        lay.addWidget(desc)

        self.device = QComboBox()
        lay.addWidget(_field("录音设备", self.device))

        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        self.test_btn = QPushButton("试录 2 秒")
        self.test_btn.setObjectName("Primary")
        self.test_btn.clicked.connect(self._start_test)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.progress, 1)
        lay.addLayout(test_row)

        self.mic_result = QLabel("尚未测试")
        self.mic_result.setObjectName("Mono")
        self.mic_result.setWordWrap(True)
        lay.addWidget(self.mic_result)
        lay.addStretch(1)
        return page

    def _page_model(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)

        desc = QLabel(
            "客户端需要一份 faster-whisper / CTranslate2 模型目录。"
            "如果本机已经有模型，直接选择目录即可，不需要复制。"
        )
        desc.setWordWrap(True)
        desc.setObjectName("Muted")
        lay.addWidget(desc)

        self.model = QLineEdit()
        self.model.setPlaceholderText(r"例如 D:\hf-models\faster-whisper-large-v3-turbo")
        self.model.textChanged.connect(self._update_model_status)
        models = QVBoxLayout()
        models.setSpacing(10)
        models.addWidget(self.model)
        row = QHBoxLayout()
        row.setSpacing(8)
        browse = QPushButton("浏览目录…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse_model)
        scan = QPushButton("扫描本机模型")
        scan.setObjectName("Ghost")
        scan.clicked.connect(self._scan_models)
        row.addWidget(browse)
        row.addWidget(scan)
        row.addStretch(1)
        models.addLayout(row)
        lay.addWidget(_field("模型目录", models))

        self.model_status = QLabel()
        self.model_status.setObjectName("Mono")
        self.model_status.setWordWrap(True)
        lay.addWidget(self.model_status)

        download = QLabel(
            "还没有模型？在 voice_ime 目录运行：python download_model.py "
            "（默认下载 medium 到 models/）。"
        )
        download.setObjectName("Muted")
        download.setWordWrap(True)
        lay.addWidget(download)
        lay.addStretch(1)
        return page

    def _page_finish(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)

        desc = QLabel("最后确认热键。API Key 可以留空，之后在设置里补充。")
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        self.hotkey = _hotkey_combo()
        self.settings_hotkey = _hotkey_combo(allow_empty=True)
        self.cycle_hotkey = _hotkey_combo(allow_empty=True)
        lay.addWidget(_field("录音热键", self.hotkey))
        lay.addWidget(_field("打开设置热键", self.settings_hotkey))
        lay.addWidget(_field("切换纠错强度热键", self.cycle_hotkey))
        for combo in (self.hotkey, self.settings_hotkey, self.cycle_hotkey):
            combo.currentIndexChanged.connect(self._update_hotkey_state)
        self.hotkey_state = QLabel()
        self.hotkey_state.setObjectName("Mono")
        lay.addWidget(self.hotkey_state)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("可留空；只写入本机 config.json")
        lay.addWidget(_field("DeepSeek API Key（可选）", self.api_key))

        self.autostart = QCheckBox("开机自动启动 mao-voice")
        lay.addWidget(self.autostart)
        lay.addStretch(1)
        return page

    # ---------- 数据填充 ----------
    def _populate(self, cfg):
        devices = list_input_devices()
        self.device.addItem("系统默认设备", "")
        for index, name in devices:
            self.device.addItem("{}  {}".format(index, name), index)
        saved_device = (cfg.get("recorder") or {}).get("device") or ""
        index = self.device.findData(saved_device)
        if index < 0 and isinstance(saved_device, str) and saved_device.isdigit():
            index = self.device.findData(int(saved_device))
        self.device.setCurrentIndex(max(0, index))
        if not devices:
            self.test_btn.setEnabled(False)
            self.mic_result.setText("未检测到输入设备；可先跳过，进入系统后再配置。")

        saved_model = (cfg.get("asr") or {}).get("model", "")
        resolved_model = resolve_model_path(saved_model, os.path.dirname(CONFIG_PATH))
        is_path = bool(
            saved_model
            and (os.path.isabs(saved_model) or "/" in saved_model
                 or "\\" in saved_model or saved_model.startswith("."))
        )
        if is_path and not validate_model_dir(resolved_model)["ok"]:
            saved_model = ""
        self.model.setText(saved_model)
        self._update_model_status()
        self._set_combo(self.hotkey, cfg.get("hotkey", "alt_r"))
        self._set_combo(self.settings_hotkey, cfg.get("settings_hotkey", "f8"))
        self._set_combo(self.cycle_hotkey, cfg.get("refine_cycle_hotkey", "f9"))
        self.api_key.setText((cfg.get("refine") or {}).get("api_key", ""))
        self.autostart.setChecked(bool((cfg.get("ui") or {}).get("autostart", False)))
        self._update_hotkey_state()

    @staticmethod
    def _set_combo(combo, value):
        idx = combo.findData(value)
        combo.setCurrentIndex(max(0, idx))

    # ---------- 麦克风测试 ----------
    def _start_test(self):
        self._stop_test()
        index = self.device.currentData()
        try:
            import sounddevice as sd
            stream = sd.InputStream(
                samplerate=16000, channels=1, blocksize=320,
                device=index if index != "" else None,
                callback=self._on_audio,
            )
            stream.start()
        except Exception as e:
            self.mic_result.setStyleSheet("color: %s;" % ERROR)
            self.mic_result.setText("无法打开麦克风：{}".format(e))
            return
        self._stream = stream
        self._peak = 0.0
        self._test_elapsed = 0.0
        self.progress.setValue(0)
        self.test_btn.setEnabled(False)
        self.mic_result.setStyleSheet("color: %s;" % TEXT_VARIANT)
        self.mic_result.setText("正在录音，请正常说话…")
        self._test_timer.start()

    def _on_audio(self, indata, frames, time_info, status):
        try:
            import numpy as np
            peak = float(np.max(np.abs(indata)))
        except Exception:
            return
        if peak > self._peak:
            self._peak = peak

    def _tick_test(self):
        self._test_elapsed += 0.05
        self.progress.setValue(min(100, int(self._test_elapsed / 2.0 * 100)))
        if self._test_elapsed >= 2.0:
            self._stop_test()
            if self._peak > 0.02:
                self.mic_result.setStyleSheet("color: %s;" % SUCCESS)
                self.mic_result.setText("检测到声音，峰值 {:.2f}，麦克风可用".format(self._peak))
            else:
                self.mic_result.setStyleSheet("color: %s;" % ERROR)
                self.mic_result.setText("没有检测到明显声音，请检查设备或系统录音权限")

    def _stop_test(self):
        self._test_timer.stop()
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self.test_btn.setEnabled(True)

    # ---------- 模型 ----------
    def _update_model_status(self):
        path = self.model.text().strip()
        if not path:
            self.model_status.setStyleSheet("color: %s;" % OUTLINE)
            self.model_status.setText("尚未选择模型目录（可先跳过）")
            return
        is_path = os.path.isabs(path) or "/" in path or "\\" in path or path.startswith(".")
        if not is_path:
            self.model_status.setStyleSheet("color: %s;" % OUTLINE)
            self.model_status.setText("将按模型名加载：{}".format(path))
            return
        result = validate_model_dir(
            resolve_model_path(path, os.path.dirname(CONFIG_PATH))
        )
        if result["ok"]:
            self.model_status.setStyleSheet("color: %s;" % SUCCESS)
            self.model_status.setText("模型可用 · {}".format(result["size_text"]))
        else:
            self.model_status.setStyleSheet("color: %s;" % ERROR)
            self.model_status.setText("不可用：{}".format(result["message"]))

    def _browse_model(self):
        start = self.model.text().strip()
        if not os.path.isdir(start):
            start = os.path.dirname(CONFIG_PATH)
        path = QFileDialog.getExistingDirectory(self, "选择模型目录", start)
        if path:
            self.model.setText(path)

    def _scan_models(self):
        root = QFileDialog.getExistingDirectory(
            self, "选择要扫描的根目录", os.path.dirname(CONFIG_PATH)
        )
        if not root:
            return
        found = scan_model_dirs(root)
        if not found:
            self.model_status.setStyleSheet("color: %s;" % ERROR)
            self.model_status.setText("没有找到包含 model.bin 的目录")
            return
        self.model.setText(found[0])
        if len(found) > 1:
            self.model_status.setText(
                "找到 {} 个模型，已选择第一个；可在设置页切换".format(len(found))
            )

    # ---------- 热键 ----------
    def _hotkey_conflict(self):
        seen = {}
        for label, combo in (
            ("录音", self.hotkey),
            ("打开设置", self.settings_hotkey),
            ("切换纠错", self.cycle_hotkey),
        ):
            key = combo.currentData()
            if not key:
                continue
            if key in seen:
                return "{} 同时绑定到「{}」和「{}」".format(
                    HOTKEY_LABELS.get(key, key), seen[key], label
                )
            seen[key] = label
        return ""

    def _update_hotkey_state(self):
        conflict = self._hotkey_conflict()
        if conflict:
            self.hotkey_state.setStyleSheet("color: %s;" % ERROR)
            self.hotkey_state.setText("热键冲突：" + conflict)
        else:
            self.hotkey_state.setStyleSheet("color: %s;" % SUCCESS)
            self.hotkey_state.setText("热键配置可用")

    # ---------- 步骤 ----------
    def _next(self):
        if self._step == 2:
            path = self.model.text().strip()
            is_path = bool(
                path and (os.path.isabs(path) or "/" in path or "\\" in path
                          or path.startswith("."))
            )
            resolved = resolve_model_path(path, os.path.dirname(CONFIG_PATH))
            if is_path and not validate_model_dir(resolved)["ok"]:
                self.model_status.setStyleSheet("color: %s;" % ERROR)
                self.model_status.setText(
                    "模型目录不可用：{}".format(validate_model_dir(resolved)["message"])
                )
                return
        if self._step == 3:
            if self._hotkey_conflict():
                return
            if self.model.text().strip() == "":
                answer = QMessageBox.question(
                    self, "还没选择模型",
                    "现在还没有选择模型，客户端启动后会显示「模型未就绪」。继续吗？",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.accept()
            return
        self._go(self._step + 1)

    def _prev(self):
        self._go(self._step - 1)

    def _go(self, step):
        self._stop_test()
        self._step = max(0, min(len(STEPS) - 1, step))
        self.stack.setCurrentIndex(self._step)
        self.title.setText([
            "欢迎使用 mao-voice",
            "检测麦克风",
            "选择识别模型",
            "热键与 API Key",
        ][self._step])
        self.step_label.setText("第 {} 步 / 共 {} 步".format(self._step + 1, len(STEPS)))
        self.back.setEnabled(self._step > 0)
        self.next.setText("完成" if self._step == len(STEPS) - 1 else "下一步")
        self.skip.setVisible(self._step < len(STEPS) - 1)

    def closeEvent(self, event):
        self._stop_test()
        super().closeEvent(event)

    def result_config(self):
        """返回合并后的完整配置，供 client_main 保存。"""
        cfg = copy.deepcopy(self._cfg)
        cfg["hotkey"] = self.hotkey.currentData()
        cfg["settings_hotkey"] = self.settings_hotkey.currentData()
        cfg["refine_cycle_hotkey"] = self.cycle_hotkey.currentData()
        cfg.setdefault("asr", {})["model"] = self.model.text().strip()
        cfg.setdefault("recorder", {})["device"] = self.device.currentData() or ""
        cfg.setdefault("ui", {})["autostart"] = self.autostart.isChecked()
        key = self.api_key.text().strip()
        if key:
            cfg.setdefault("refine", {})["api_key"] = key
        return cfg


def _field(label_text, control):
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    label = QLabel(label_text)
    label.setObjectName("Muted")
    lay.addWidget(label)
    if isinstance(control, QWidget):
        lay.addWidget(control)
    else:
        lay.addLayout(control)
    return box


def _hotkey_combo(allow_empty=False):
    combo = QComboBox()
    if allow_empty:
        combo.addItem("禁用", "")
    for key in HOTKEYS:
        combo.addItem(HOTKEY_LABELS.get(key, key), key)
    return combo


def _rounded_logo(size):
    from .theme import asset_path
    path = asset_path("logo.png")
    if not os.path.exists(path):
        return QPixmap()
    pix = QPixmap(path)
    inset = int(pix.width() * 0.045)
    src = pix.copy(inset, inset, pix.width() - inset * 2, pix.height() - inset * 2)
    src = src.scaled(QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setClipPath(_rounded_path(size))
    painter.drawPixmap(0, 0, src)
    painter.end()
    return out


def _rounded_path(size):
    from PySide6.QtGui import QPainterPath
    from PySide6.QtCore import QRectF
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    return path


_QSS = """
QWidget#Root { background: %(bg)s; color: %(text)s; font-family: "%(font)s"; font-size: 16px; }
QWidget#WizardHead { background: %(lowest)s; border-bottom: 1px solid %(outline_variant)s; }
QFrame#Banner, QFrame#Inner { background: %(low)s; border: 1px solid %(outline_variant)s; border-radius: %(radius)s; }
QLabel#H1 { font-size: 22px; font-weight: 600; }
QLabel#H2 { font-size: 17px; font-weight: 600; }
QLabel#Mono { font-family: "%(mono)s"; font-size: 13px; color: %(outline)s; }
QLabel#Muted { color: %(muted)s; font-size: 14px; }
QLineEdit, QComboBox { background: %(container)s; color: %(text)s; border: 1px solid %(outline_variant)s;
    border-radius: %(radius_sm)s; padding: 7px 11px; min-height: 30px; font-size: 14px; }
QLineEdit:focus, QComboBox:focus { border-color: %(primary)s; }
QComboBox QAbstractItemView { background: %(low)s; color: %(text)s; selection-background-color: %(high)s; }
QPushButton#Primary { background: %(primary)s; color: %(on_primary)s; border: none; border-radius: %(radius_sm)s;
    padding: 8px 18px; font-size: 14px; font-weight: 600; }
QPushButton#Primary:hover { background: %(primary_hover)s; }
QPushButton#Ghost { background: %(container)s; color: %(muted)s; border: 1px solid %(outline_variant)s;
    border-radius: %(radius_sm)s; padding: 7px 14px; font-size: 13px; }
QPushButton#Ghost:hover { background: %(high)s; color: %(text)s; }
QPushButton#Ghost:disabled { color: %(outline_variant)s; }
QCheckBox { color: %(text)s; spacing: 10px; font-size: 14px; }
QProgressBar { border: 1px solid %(outline_variant)s; border-radius: 4px; background: %(container)s; max-height: 14px; }
QProgressBar::chunk { background: %(primary)s; border-radius: 3px; }
""" % {
    "bg": SURFACE, "lowest": SURFACE_LOWEST, "low": SURFACE_LOW,
    "container": SURFACE_CONTAINER, "high": SURFACE_HIGH, "highest": SURFACE_HIGHEST,
    "outline": OUTLINE, "outline_variant": OUTLINE_VARIANT, "text": TEXT,
    "muted": TEXT_VARIANT, "primary": PRIMARY, "on_primary": ON_PRIMARY,
    "primary_hover": PRIMARY_HOVER, "radius": RADIUS, "radius_sm": RADIUS_SM,
    "mono": FONT_MONO, "font": FONT_FAMILY,
}

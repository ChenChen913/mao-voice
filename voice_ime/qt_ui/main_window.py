# -*- coding: utf-8 -*-
"""Qt 主窗口原型：首页 / 历史 / 词库 / 设置 四页骨架，读取真实配置与词库。"""
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from .theme import (
    ACCENT, BORDER, MUTED, STATE_CONFIG, SURFACE, TEXT, WINDOW_BG,
)
from version import __version__

ROOT = Path(__file__).resolve().parents[2]
VOICE_IME = ROOT / "voice_ime"
CONFIG_PATH = VOICE_IME / "config.json"
EXAMPLE_PATH = VOICE_IME / "config.example.json"
WORDS_PATH = VOICE_IME / "词库.txt"
HISTORY_PATH = VOICE_IME / "history.json"

HOTKEYS = ["alt_r", "alt_l", "ctrl_r", "ctrl_l", "shift_r", "shift_l",
           "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10",
           "f11", "f12", "caps_lock", "space", "enter", "esc"]
LEVELS = [("conservative", "保守纠错"), ("light", "轻度规整"), ("polish", "完整规整")]


def model_ready(cfg):
    """配置里的模型路径是否存在（模型名如 small 视为可自动下载）。"""
    model = (cfg.get("asr", {}).get("model") or "").strip()
    if not model:
        return False
    if "/" not in model and "\\" not in model and not model.startswith("."):
        return True
    return Path(model).exists()


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_cfg():
    cfg = load_json(CONFIG_PATH)
    return cfg or load_json(EXAMPLE_PATH)


def load_words():
    terms, mappings = [], []
    try:
        with open(WORDS_PATH, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() and v.strip():
                        mappings.append((k.strip(), v.strip()))
                else:
                    terms.append(line)
    except OSError:
        pass
    return terms, mappings


def load_history():
    data = load_json_list(HISTORY_PATH)
    return [x for x in data if isinstance(x, dict) and x.get("final")]


def load_json_list(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


QSS = """
QWidget#Root { background: %(bg)s; }
QWidget#TitleBar { background: #16191D; border-bottom: 1px solid %(border)s; }
QLabel { color: %(text)s; background: transparent; }
QLabel#Muted { color: %(muted)s; }
QLabel#H1 { font-size: 20px; font-weight: 600; }
QLabel#H2 { font-size: 15px; font-weight: 600; }
QPushButton#Nav {
    text-align: left; padding: 10px 14px; border-radius: 8px;
    color: %(muted)s; background: transparent; border: none;
}
QPushButton#Nav:hover { background: #1B1E23; color: %(text)s; }
QPushButton#Nav[active="true"] { background: #1F2933; color: %(text)s; }
QPushButton#Record {
    background: %(accent)s; color: white; border: none; border-radius: 12px;
    font-size: 15px; font-weight: 600; padding: 18px 28px;
}
QPushButton#Record:hover { background: #5AA0E3; }
QPushButton#Primary {
    background: %(accent)s; color: white; border: none; border-radius: 8px;
    font-size: 13px; font-weight: 600; padding: 8px 18px;
}
QPushButton#Primary:hover { background: #5AA0E3; }
QPushButton#Ghost {
    background: #1B1E23; color: %(text)s; border: 1px solid %(border)s;
    border-radius: 8px; padding: 6px 12px;
}
QPushButton#Ghost:hover { background: #232830; }
QPushButton#WinBtn {
    background: transparent; color: %(muted)s; border: none;
    border-radius: 6px; padding: 0; font-size: 14px;
}
QPushButton#WinBtn:hover { background: #232830; color: %(text)s; }
QFrame#Card { background: %(surface)s; border: 1px solid %(border)s; border-radius: 12px; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 10px 12px; border-radius: 8px; color: %(text)s; }
QListWidget::item:selected { background: #1F2933; }
QTableWidget { background: %(surface)s; border: 1px solid %(border)s; border-radius: 8px; gridline-color: %(border)s; }
QHeaderView::section { background: #1B1E23; color: %(muted)s; border: none; padding: 6px 10px; }
QLineEdit, QComboBox { background: #1B1E23; color: %(text)s; border: 1px solid %(border)s;
    border-radius: 6px; padding: 6px 10px; }
QTextEdit { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s;
    border-radius: 8px; padding: 8px; }
QCheckBox { color: %(text)s; spacing: 8px; }
""" % {"bg": WINDOW_BG, "border": BORDER, "text": TEXT, "muted": MUTED,
       "surface": SURFACE, "accent": ACCENT}


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__()
        self._window = window
        self._drag = None
        self.setObjectName("TitleBar")
        self.setFixedHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 10, 0)
        title = QLabel("mao-voice")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        lay.addWidget(title)
        tag = QLabel("客户端预览")
        tag.setObjectName("Muted")
        tag.setStyleSheet("font-size: 12px;")
        lay.addWidget(tag)
        lay.addStretch(1)
        btn_min = QPushButton("—")
        btn_min.setObjectName("WinBtn")
        btn_min.setFixedSize(32, 28)
        btn_min.clicked.connect(self._window.showMinimized)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("WinBtn")
        btn_close.setFixedSize(32, 28)
        btn_close.clicked.connect(self._window.close)
        lay.addWidget(btn_min)
        lay.addWidget(btn_close)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None


class HomePage(QWidget):
    record_clicked = Signal()

    def __init__(self):
        super().__init__()
        cfg = load_cfg()
        self._model_ok = model_ready(cfg)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(18)

        header = QHBoxLayout()
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: %s; font-size: 14px;" % "#27AE60")
        self.status = QLabel("就绪")
        self.status.setObjectName("H2")
        self.hint = QLabel("按右 Alt 开始说话")
        self.hint.setObjectName("Muted")
        header.addWidget(self.dot)
        header.addWidget(self.status)
        header.addSpacing(10)
        header.addWidget(self.hint)
        header.addStretch(1)
        lay.addLayout(header)

        hero = QFrame()
        hero.setObjectName("Card")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(28, 26, 28, 26)
        hero_lay.setSpacing(14)
        self.hero_title = QLabel("今天想说什么？")
        self.hero_title.setObjectName("H1")
        self.hero_sub = QLabel(
            "识别在本机完成，只有开启纠错时文本才会发往你配置的服务"
            if self._model_ok else
            "还没有下载模型：先运行 python download_model.py，再开始说话"
        )
        self.hero_sub.setObjectName("Muted")
        self.record_btn = QPushButton("按一下开始说话")
        self.record_btn.setObjectName("Record")
        self.record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_btn.clicked.connect(self.record_clicked)
        hero_lay.addWidget(self.hero_title)
        hero_lay.addWidget(self.hero_sub)
        hero_lay.addSpacing(6)
        hero_lay.addWidget(self.record_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(hero)

        recent_card = QFrame()
        recent_card.setObjectName("Card")
        rec_lay = QVBoxLayout(recent_card)
        rec_lay.setContentsMargins(20, 16, 20, 16)
        rec_lay.setSpacing(8)
        rec_title = QLabel("最近输入")
        rec_title.setObjectName("H2")
        rec_lay.addWidget(rec_title)
        self.recent_list = QListWidget()
        self.recent_list.setFixedHeight(150)
        rec_lay.addWidget(self.recent_list)
        lay.addWidget(recent_card, 1)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        hist = load_history()
        words = sum(len(x.get("final", "")) for x in hist)
        self.stat_words = self._stat_card(stats, "今日输入", "{} 字".format(words))
        self.stat_time = self._stat_card(
            stats, "约省时间", "{} 分钟".format(max(0, words // 40))
        )
        self.stat_model = self._stat_card(
            stats, "识别模型", Path(cfg.get("asr", {}).get("model", "medium")).name
        )
        lay.addLayout(stats)

        self._refresh_recent(hist)

    @staticmethod
    def _stat_card(layout, title, value):
        card = QFrame()
        card.setObjectName("Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 12, 16, 12)
        t = QLabel(title)
        t.setObjectName("Muted")
        v = QLabel(value)
        v.setStyleSheet("font-size: 16px; font-weight: 600;")
        box.addWidget(t)
        box.addWidget(v)
        layout.addWidget(card, 1)
        return v

    def _refresh_recent(self, hist):
        self.recent_list.clear()
        if not hist:
            item = QListWidgetItem("还没有输入记录。开启历史记录后，这里会显示最近说过的内容。")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(item)
            return
        for x in reversed(hist[-5:]):
            text = x.get("final", "").replace("\n", " ")
            preview = text[:46] + ("…" if len(text) > 46 else "")
            item = QListWidgetItem("{}   {}".format(x.get("ts", "")[11:16], preview))
            self.recent_list.addItem(item)

    def refresh_stats(self):
        hist = load_history()
        words = sum(len(x.get("final", "")) for x in hist)
        self.stat_words.setText("{} 字".format(words))
        self.stat_time.setText("{} 分钟".format(max(0, words // 40)))
        self._refresh_recent(hist)

    def update_config(self, cfg):
        self._model_ok = model_ready(cfg)
        self.stat_model.setText(Path(cfg.get("asr", {}).get("model", "medium")).name)
        self.set_status("IDLE")

    def set_status(self, state, text=""):
        if state == "IDLE" and not self._model_ok:
            self.dot.setStyleSheet("color: %s; font-size: 14px;" % "#F39C12")
            self.status.setText("模型未就绪")
            self.hint.setText("先运行 python download_model.py")
            self.record_btn.setText("按一下开始说话")
            return
        color = STATE_CONFIG.get(state, {"color": "#27AE60"})["color"]
        labels = {
            "IDLE": "就绪", "RECORDING": "录音中", "TRANSCRIBING": "转写中",
            "REFINING": "润色中", "INJECTING": "注入中", "ERROR": "出错了",
        }
        self.dot.setStyleSheet("color: %s; font-size: 14px;" % color)
        self.status.setText(labels.get(state, state))
        if state == "RECORDING":
            self.record_btn.setText("再按一下结束")
        elif state == "IDLE":
            self.record_btn.setText("按一下开始说话")
            self.hint.setText("按右 Alt 开始说话")
            self.hero_sub.setText("识别在本机完成，只有开启纠错时文本才会发往你配置的服务")


class HistoryPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        title = QLabel("历史")
        title.setObjectName("H1")
        lay.addWidget(title)
        body = QHBoxLayout()
        body.setSpacing(16)
        self.list = QListWidget()
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        body.addWidget(self.list, 4)
        body.addWidget(self.detail, 6)
        lay.addLayout(body, 1)

        self._items = []
        self.list.currentRowChanged.connect(self._show_detail)
        self.reload()

    def reload(self):
        self._items = load_history()
        self.list.blockSignals(True)
        self.list.clear()
        if not self._items:
            item = QListWidgetItem("暂无历史记录")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(item)
            self.detail.setPlainText("开启「输入历史」后，每次成功注入都会记录在这里。")
        else:
            for x in reversed(self._items):
                text = x.get("final", "").replace("\n", " ")
                self.list.addItem("{}   {}".format(x.get("ts", "")[5:16], text[:40]))
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        if self._items:
            self._show_detail(0)

    def _show_detail(self, row):
        if row < 0 or row >= len(self._items):
            return
        x = list(reversed(self._items))[row]
        self.detail.setPlainText(
            "时间：{}\n时长：{} 秒\n\n原始转写：\n{}\n\n润色结果：\n{}".format(
                x.get("ts", ""), x.get("duration_s", "?"),
                x.get("raw", ""), x.get("final", ""),
            )
        )


class DictionaryPage(QWidget):
    def __init__(self):
        super().__init__()
        terms, mappings = load_words()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        title = QLabel("词库")
        title.setObjectName("H1")
        hint = QLabel("热词会拼入识别提示词；替换规则只作用于纠错结果。原型阶段仅展示。")
        hint.setObjectName("Muted")
        lay.addWidget(title)
        lay.addWidget(hint)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["原词 / 词条", "指定写法", "类型"])
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        rows = [(t, "（热词）", "热词") for t in terms] + [
            (k, v, "替换规则") for k, v in mappings
        ]
        table.setRowCount(len(rows))
        for r, (a, b, kind) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(a))
            table.setItem(r, 1, QTableWidgetItem(b))
            table.setItem(r, 2, QTableWidgetItem(kind))
        table.resizeColumnsToContents()
        lay.addWidget(table, 1)


class SettingsPage(QWidget):
    saved = Signal(dict)

    PASTE_MODES = [
        ("auto", "自动（终端类窗口走 Unicode 直注）"),
        ("ctrl_v", "始终剪贴板 + Ctrl+V"),
        ("unicode", "始终 Unicode 直注"),
    ]

    def __init__(self):
        super().__init__()
        cfg = load_cfg()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        title = QLabel("设置")
        title.setObjectName("H1")
        banner = QLabel("保存后立即生效；录音热键会重载监听。API Key 只写入本机 config.json。")
        banner.setStyleSheet(
            "color: %s; background: #1B1E23; border: 1px solid %s;"
            "border-radius: 8px; padding: 8px 12px;" % (MUTED, BORDER)
        )
        lay.addWidget(title)
        lay.addWidget(banner)

        card = QFrame()
        card.setObjectName("Card")
        form = QFormLayout(card)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.hotkey = QComboBox()
        self.hotkey.addItems(HOTKEYS)
        self.hotkey.setCurrentText(cfg.get("hotkey", "alt_r"))
        form.addRow("录音热键", self.hotkey)

        self.model = QLineEdit(cfg.get("asr", {}).get("model", ""))
        self.model.setPlaceholderText("models/faster-whisper-medium 或 small")
        form.addRow("识别模型", self.model)

        self.level = QComboBox()
        for key, label in LEVELS:
            self.level.addItem(label, key)
        current = cfg.get("refine", {}).get("level", "conservative")
        self.level.setCurrentIndex(max(0, [k for k, _ in LEVELS].index(current)))
        form.addRow("纠错强度", self.level)

        self.base_url = QLineEdit(cfg.get("refine", {}).get("base_url", ""))
        self.base_url.setPlaceholderText("https://api.deepseek.com/v1")
        form.addRow("纠错服务", self.base_url)

        self.api_key = QLineEdit(cfg.get("refine", {}).get("api_key", ""))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("留空则使用 DEEPSEEK_API_KEY 环境变量")
        form.addRow("API Key", self.api_key)

        self.paste_mode = QComboBox()
        for key, label in self.PASTE_MODES:
            self.paste_mode.addItem(label, key)
        current_mode = cfg.get("inject", {}).get("paste_mode", "auto")
        mode_keys = [k for k, _ in self.PASTE_MODES]
        self.paste_mode.setCurrentIndex(
            mode_keys.index(current_mode) if current_mode in mode_keys else 0
        )
        form.addRow("注入方式", self.paste_mode)

        self.hist_cb = QCheckBox("记录输入历史（明文落盘）")
        self.hist_cb.setChecked(bool(cfg.get("history", {}).get("enabled", False)))
        form.addRow("历史", self.hist_cb)

        self.learn_cb = QCheckBox("自学习纠错规则（明文落盘）")
        self.learn_cb.setChecked(bool(cfg.get("learn", {}).get("enabled", False)))
        form.addRow("学习", self.learn_cb)

        lay.addWidget(card)

        footer = QHBoxLayout()
        self.save_btn = QPushButton("保存并应用")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setFixedHeight(38)
        self.save_btn.clicked.connect(self._save)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        footer.addWidget(self.save_btn)
        footer.addSpacing(12)
        footer.addWidget(self.status)
        footer.addStretch(1)
        lay.addLayout(footer)
        lay.addStretch(1)

    def _save(self):
        model = self.model.text().strip()
        if not model:
            self._warn("识别模型不能为空")
            return
        if self.hotkey.currentText() not in HOTKEYS:
            self._warn("热键不在支持列表内")
            return
        payload = {
            "hotkey": self.hotkey.currentText(),
            "asr": {"model": model},
            "refine": {
                "level": self.level.currentData(),
                "base_url": self.base_url.text().strip(),
                "api_key": self.api_key.text().strip(),
            },
            "inject": {"paste_mode": self.paste_mode.currentData()},
            "history": {"enabled": self.hist_cb.isChecked()},
            "learn": {"enabled": self.learn_cb.isChecked()},
        }
        self.saved.emit(payload)

    def show_result(self, ok, message):
        self.status.setStyleSheet("color: %s;" % ("#27AE60" if ok else "#E74C3C"))
        self.status.setText(message)

    def _warn(self, message):
        self.show_result(False, message)


class MainWindow(QWidget):
    settings_saved = Signal(dict)

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint)
        self.setObjectName("Root")
        self.setStyleSheet(QSS)
        self.resize(1000, 660)
        self.setMinimumSize(860, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(TitleBar(self))

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.home = HomePage()
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage()
        self.settings_page.saved.connect(self.settings_saved)
        self.pages = {
            "首页": self.home,
            "历史": self.history_page,
            "词库": DictionaryPage(),
            "设置": self.settings_page,
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self._set_page("首页")

    def _build_sidebar(self):
        side = QWidget()
        side.setFixedWidth(190)
        side.setStyleSheet("background: #0F1114; border-right: 1px solid %s;" % BORDER)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 16, 12, 16)
        lay.setSpacing(6)
        self.nav_buttons = {}
        for name in ("首页", "历史", "词库", "设置"):
            btn = QPushButton(name)
            btn.setObjectName("Nav")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, n=name: self._set_page(n))
            lay.addWidget(btn)
            self.nav_buttons[name] = btn
        lay.addStretch(1)
        version = QLabel("v{} · 客户端预览".format(__version__))
        version.setObjectName("Muted")
        version.setStyleSheet("font-size: 11px;")
        version.setWordWrap(True)
        lay.addWidget(version)
        return side

    def _set_page(self, name):
        self.stack.setCurrentWidget(self.pages[name])
        for n, btn in self.nav_buttons.items():
            if n == name:
                btn.setStyleSheet("background: #1F2933; color: #E8EAED;")
            else:
                btn.setStyleSheet("")

    def show_page(self, name):
        if name in self.pages:
            if name == "历史":
                self.history_page.reload()
            elif name == "首页":
                self.home.refresh_stats()
            self._set_page(name)
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh_data(self, cfg=None):
        """引擎状态变化后刷新首页统计与历史列表。"""
        if cfg is not None:
            self.home.update_config(cfg)
        else:
            self.home.refresh_stats()
        self.history_page.reload()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def set_status(self, state, text=""):
        self.home.set_status(state, text)

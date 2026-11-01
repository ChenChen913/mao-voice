# -*- coding: utf-8 -*-
"""Qt 主窗口：对齐 code.html 原型的深色仪表风（1000×660）。"""
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QMouseEvent, QPainter,
    QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QSizeGrip, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from version import __version__
from hotkey import HOTKEY_LABELS
from .theme import (
    ERROR, FONT_FAMILY, FONT_MONO, OUTLINE, OUTLINE_VARIANT, PRIMARY, RADIUS,
    RADIUS_SM, SECONDARY, SECONDARY_CONTAINER, STATE_CONFIG, SUCCESS, SURFACE,
    SURFACE_CONTAINER, SURFACE_HIGH, SURFACE_HIGHEST, SURFACE_LOW,
    SURFACE_LOWEST, TERTIARY, TEXT, TEXT_VARIANT, asset_path,
)

ROOT = Path(__file__).resolve().parents[2]
VOICE_IME = ROOT / "voice_ime"
CONFIG_PATH = VOICE_IME / "config.json"
EXAMPLE_PATH = VOICE_IME / "config.example.json"
WORDS_PATH = VOICE_IME / "词库.txt"
HISTORY_PATH = VOICE_IME / "history.json"
LEARNED_PATH = VOICE_IME / "learned_rules.json"

HOTKEYS = ["alt_r", "alt_l", "ctrl_r", "ctrl_l", "shift_r", "shift_l",
           "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10",
           "f11", "f12", "caps_lock", "space", "enter", "esc"]
LEVELS = [("conservative", "保守纠错"), ("light", "轻度规整"), ("polish", "完整规整")]
PASTE_MODES = [("auto", "自动（终端走 Unicode）"), ("ctrl_v", "始终 Ctrl+V"),
               ("unicode", "始终 Unicode 直注")]
LANGUAGES = [(None, "自动检测（中英混杂）"), ("zh", "固定中文"), ("en", "固定英文")]

LEVEL_LABELS = dict(LEVELS)
PASTE_LABELS = dict(PASTE_MODES)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def load_cfg():
    cfg = load_json(CONFIG_PATH, {})
    return cfg if cfg else load_json(EXAMPLE_PATH, {})


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


def load_learned():
    data = load_json(LEARNED_PATH, [])
    out = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("wrong") and item.get("right"):
                out.append((item["wrong"], item["right"], int(item.get("count", 0))))
    return out


def load_history():
    data = load_json(HISTORY_PATH, [])
    return [x for x in data if isinstance(x, dict) and x.get("final")]


def model_ready(cfg):
    model = (cfg.get("asr", {}).get("model") or "").strip()
    if not model:
        return False
    if "/" not in model and "\\" not in model and not model.startswith("."):
        return True
    return Path(model).exists()


def short_model_name(cfg):
    """把 faster-whisper-large-v3-turbo 缩成 large-v3-turbo，避免界面里被截断。"""
    name = Path((cfg.get("asr", {}).get("model") or "")).name
    return name.replace("faster-whisper-", "").replace("faster-whisper", "本地模型") or "本地模型"


def parse_ts(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def elide(text, width, font):
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, width)


# --------------------------------------------------------------------------
# 图标
# --------------------------------------------------------------------------

def make_glyph(kind, color, size=16):
    """用 QPainter 画极简线性图标，避免依赖外部图标字体。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(color), 1.2))
    s = size
    if kind == "mic":
        p.drawRoundedRect(int(s * 0.35), int(s * 0.08), int(s * 0.3), int(s * 0.42), 3, 3)
        p.drawArc(int(s * 0.27), int(s * 0.3), int(s * 0.46), int(s * 0.42), 180 * 16, 180 * 16)
        p.drawLine(int(s * 0.5), int(s * 0.72), int(s * 0.5), int(s * 0.86))
        p.drawLine(int(s * 0.32), int(s * 0.86), int(s * 0.68), int(s * 0.86))
    elif kind == "history":
        p.drawEllipse(int(s * 0.12), int(s * 0.12), int(s * 0.76), int(s * 0.76))
        p.drawLine(int(s * 0.5), int(s * 0.3), int(s * 0.5), int(s * 0.5))
        p.drawLine(int(s * 0.5), int(s * 0.5), int(s * 0.68), int(s * 0.62))
    elif kind == "dict":
        p.drawRoundedRect(int(s * 0.16), int(s * 0.1), int(s * 0.68), int(s * 0.8), 2, 2)
        for y in (0.3, 0.5, 0.7):
            p.drawLine(int(s * 0.26), int(s * y), int(s * 0.7), int(s * y))
    elif kind == "settings":
        for i, y in enumerate((0.25, 0.5, 0.75)):
            p.drawLine(int(s * 0.12), int(s * y), int(s * 0.88), int(s * y))
            cx = (0.3, 0.7, 0.45)[i]
            p.drawEllipse(int(s * cx) - 1, int(s * y) - 1, 4, 4)
    elif kind == "power":
        p.drawArc(int(s * 0.2), int(s * 0.24), int(s * 0.6), int(s * 0.6), 30 * 16, 300 * 16)
        p.drawLine(int(s * 0.5), int(s * 0.12), int(s * 0.5), int(s * 0.5))
    p.end()
    return QIcon(pix)


class LogoLabel(QLabel):
    def __init__(self, size=26):
        super().__init__()
        path = asset_path("logo.png")
        pix = QPixmap(path) if Path(path).exists() else QPixmap()
        if pix.isNull():
            self.setText("●")
            self.setStyleSheet("color: %s; font-size: 18px;" % PRIMARY)
        else:
            # 原图四角是白底：先裁掉白边，再按圆角裁切，避免深色顶栏上露出白角
            inset = int(pix.width() * 0.045)
            cropped = pix.copy(inset, inset, pix.width() - inset * 2, pix.height() - inset * 2)
            src = cropped.scaled(
                QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            rounded = QPixmap(size, size)
            rounded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
            painter.setClipPath(clip)
            painter.drawPixmap(0, 0, src)
            painter.end()
            self.setPixmap(rounded)


# --------------------------------------------------------------------------
# 通用控件
# --------------------------------------------------------------------------

QSS = """
QWidget#Root { background: %(bg)s; color: %(text)s; font-family: "%(font)s"; font-size: 16px; }
QWidget#TopBar { background: %(lowest)s; border-bottom: 1px solid %(outline_variant)s; }
QWidget#SideBar { background: %(low)s; border-right: 1px solid %(outline_variant)s; }
QWidget#StatusBar { background: %(lowest)s; border-top: 1px solid %(outline_variant)s; }
QLabel { background: transparent; color: %(text)s; }
QLabel#Mono { font-family: "%(mono)s"; font-size: 13px; color: %(outline)s; }
QLabel#Muted { color: %(muted)s; font-size: 14px; }
QLabel#Title { font-size: 19px; font-weight: 600; color: %(text)s; }
QLabel#H1 { font-size: 22px; font-weight: 600; color: %(text)s; }
QLabel#H2 { font-size: 17px; font-weight: 600; color: %(text)s; }
QFrame#Banner, QFrame#Card { background: %(low)s; border: 1px solid %(outline_variant)s; border-radius: %(radius)s; }
QFrame#Hero { background: %(lowest)s; border: 1px solid %(outline_variant)s; border-radius: %(radius)s; }
QFrame#Inner { background: %(container)s; border: 1px solid %(outline_variant)s; border-radius: %(radius_sm)s; }
QFrame#Row { background: %(container)s; border: 1px solid %(outline_variant)s; border-radius: %(radius_sm)s; }
QFrame#Row:hover { background: %(high)s; }
QPushButton#Nav {
    text-align: left; padding: 10px 12px 10px 10px; border: none;
    border-left: 2px solid transparent; border-radius: %(radius_sm)s;
    color: %(muted)s; background: transparent; font-size: 15px;
}
QPushButton#Nav:hover { background: %(container)s; color: %(text)s; }
QPushButton#Nav:checked {
    background: %(highest)s; color: %(text)s; border-left: 2px solid %(primary)s;
}
QPushButton#Primary {
    background: %(primary)s; color: #002e6a; border: none; border-radius: %(radius_sm)s;
    padding: 8px 18px; font-size: 14px; font-weight: 600;
}
QPushButton#Primary:hover { background: #d8e2ff; }
QPushButton#Ghost {
    background: %(container)s; color: %(muted)s; border: 1px solid %(outline_variant)s;
    border-radius: %(radius_sm)s; padding: 7px 14px; font-size: 13px;
}
QPushButton#Ghost:hover { background: %(high)s; color: %(text)s; }
QPushButton#WinBtn { background: transparent; color: %(outline)s; border: none; font-size: 16px; }
QPushButton#WinBtn:hover { background: %(high)s; color: %(text)s; }
QPushButton#Record {
    background: %(primary)s; color: #002e6a; border: none;
    border-radius: %(radius)s; padding: 14px 28px; font-size: 18px; font-weight: 600;
}
QPushButton#Record:hover { background: #c4d6ff; }
QPushButton#Chip {
    background: transparent; color: %(outline)s; border: 1px solid transparent;
    border-radius: %(radius_sm)s; padding: 4px 11px; font-size: 13px;
}
QPushButton#Chip:hover { color: %(text)s; background: %(container)s; }
QPushButton#Chip:checked { color: %(text)s; background: %(highest)s; border-color: %(outline_variant)s; }
QLineEdit, QComboBox, QDoubleSpinBox {
    background: %(container)s; color: %(text)s; border: 1px solid %(outline_variant)s;
    border-radius: %(radius_sm)s; padding: 7px 11px; min-height: 30px; font-size: 14px;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border-color: %(primary)s; }
QComboBox QAbstractItemView { background: %(low)s; color: %(text)s; selection-background-color: %(high)s; }
QCheckBox { color: %(text)s; spacing: 10px; font-size: 14px; }
QListWidget { background: transparent; border: none; outline: none; font-size: 14px; }
QListWidget::item { padding: 9px 10px; border-radius: %(radius_sm)s; color: %(text)s; }
QListWidget::item:hover { background: %(container)s; }
QListWidget::item:selected { background: %(highest)s; color: %(text)s; }
QTableWidget { background: %(lowest)s; border: 1px solid %(outline_variant)s; border-radius: %(radius)s; gridline-color: %(outline_variant)s; font-size: 14px; }
QHeaderView::section { background: %(low)s; color: %(outline)s; border: none; padding: 10px 12px; font-size: 13px; }
QTableWidget::item { padding: 6px 10px; }
QTextEdit, QPlainTextEdit { background: %(lowest)s; color: %(text)s; border: 1px solid %(outline_variant)s; border-radius: %(radius_sm)s; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: %(outline_variant)s; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
""" % {
    "bg": SURFACE, "lowest": SURFACE_LOWEST, "low": SURFACE_LOW,
    "container": SURFACE_CONTAINER, "high": SURFACE_HIGH, "highest": SURFACE_HIGHEST,
    "outline": OUTLINE, "outline_variant": OUTLINE_VARIANT, "text": TEXT,
    "muted": TEXT_VARIANT, "primary": PRIMARY, "radius": RADIUS,
    "radius_sm": RADIUS_SM, "font": FONT_FAMILY, "mono": FONT_MONO,
}


class NavButton(QPushButton):
    def __init__(self, text, kind):
        super().__init__(text)
        self.kind = kind
        self.setObjectName("Nav")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(make_glyph(kind, TEXT_VARIANT, 18))
        self.setIconSize(QSize(18, 18))

    def set_active(self, active):
        self.setChecked(active)
        self.setIcon(make_glyph(self.kind, PRIMARY if active else TEXT_VARIANT, 18))


class WaveformWidget(QWidget):
    """仪表盘上的实时波形示意；真实录音反馈仍由悬浮胶囊负责。"""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(104)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._phase += 0.12
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        p.fillRect(rect, QColor(SURFACE_CONTAINER))
        p.setPen(QPen(QColor(OUTLINE_VARIANT), 1))
        p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), RADIUS_SM, RADIUS_SM)

        p.setFont(QFont(FONT_MONO, 12))
        p.setPen(QColor(OUTLINE))
        p.drawText(rect.adjusted(14, 10, -14, 0), Qt.AlignmentFlag.AlignLeft, "实时波形")
        p.drawText(rect.adjusted(14, 10, -14, 0), Qt.AlignmentFlag.AlignRight, "本地识别")

        bars = 55
        gap = 6
        bar_w = 4
        total = bars * bar_w + (bars - 1) * gap
        start = (self.width() - total) // 2
        cy = self.height() / 2
        for i in range(bars):
            env = 0.18 + 0.32 * abs(math.sin(i * 0.7 + 0.4))
            wave = 0.5 + 0.5 * math.sin(self._phase + i * 0.55)
            h = 8 + (self.height() * 0.42) * env * (0.55 + 0.45 * wave)
            color = PRIMARY if env > 0.3 else SECONDARY_CONTAINER
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(
                int(start + i * (bar_w + gap)), int(cy - h / 2),
                bar_w, int(h), 1, 1,
            )
        p.setFont(QFont(FONT_MONO, 12))
        p.setPen(QColor(OUTLINE))
        p.drawText(rect.adjusted(14, 0, -14, -10), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, "说话时波形律动")
        p.drawText(rect.adjusted(14, 0, -14, -10), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, "音频不出本机")


class StatBox(QFrame):
    def __init__(self, title, value, unit="", color=TEXT):
        super().__init__()
        self.setObjectName("Inner")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("Mono")
        v = QLabel("{} {}".format(value, unit).strip())
        v.setStyleSheet("font-size: 22px; font-weight: 600; color: %s; font-family: '%s';" % (color, FONT_MONO))
        lay.addWidget(t)
        lay.addWidget(v)


# --------------------------------------------------------------------------
# 页面：首页
# --------------------------------------------------------------------------

class HomePage(QWidget):
    record_clicked = Signal()
    history_clicked = Signal()

    def __init__(self):
        super().__init__()
        cfg = load_cfg()
        self._cfg = cfg
        self._model_ok = model_ready(cfg)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 14)
        lay.setSpacing(14)

        # 顶部状态条
        banner = QFrame()
        banner.setObjectName("Banner")
        banner.setFixedHeight(58)
        b = QHBoxLayout(banner)
        b.setContentsMargins(16, 0, 16, 0)
        b.setSpacing(12)
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: %s; font-size: 14px;" % PRIMARY)
        self.status = QLabel("就绪 · 待命")
        self.status.setObjectName("H1")
        sep = QLabel("|")
        sep.setObjectName("Mono")
        self.model_label = QLabel()
        self.model_label.setObjectName("Muted")
        self.hotkey_hint = QLabel("全局唤醒   " + self._hotkey_label())
        self.hotkey_hint.setObjectName("Mono")
        self.hotkey_hint.setStyleSheet(
            "color: %s; font-family: '%s'; font-size: 13px;" % (PRIMARY, FONT_MONO)
        )
        b.addWidget(self.dot)
        b.addWidget(self.status)
        b.addWidget(sep)
        b.addWidget(self.model_label)
        b.addStretch(1)
        b.addWidget(self.hotkey_hint)
        lay.addWidget(banner)

        # 中央仪表区
        hero = QFrame()
        hero.setObjectName("Hero")
        h = QVBoxLayout(hero)
        h.setContentsMargins(20, 16, 20, 16)
        h.setSpacing(12)
        self.wave = WaveformWidget()
        h.addWidget(self.wave, 1)
        center = QHBoxLayout()
        center.addStretch(1)
        self.record_btn = QPushButton("开始说话")
        self.record_btn.setObjectName("Record")
        self.record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_btn.setIcon(make_glyph("mic", "#002e6a", 22))
        self.record_btn.setIconSize(QSize(22, 22))
        self.record_btn.clicked.connect(self.record_clicked)
        center.addWidget(self.record_btn)
        center.addStretch(1)
        h.addLayout(center)
        self.hint = QLabel("按一下开始，再按一次结束 · 文本自动写入当前光标处")
        self.hint.setObjectName("Mono")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self.hint)
        lay.addWidget(hero, 1)

        self._apply_record_style(False)

        # 底部：最近输入 + 统计
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        recent = QFrame()
        recent.setObjectName("Card")
        r = QVBoxLayout(recent)
        r.setContentsMargins(14, 12, 14, 12)
        r.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel("最近输入流水")
        t.setObjectName("H2")
        more = QPushButton("查看完整历史")
        more.setObjectName("Chip")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.clicked.connect(self.history_clicked)
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(more)
        r.addLayout(head)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(6)
        r.addLayout(self.recent_box)
        bottom.addWidget(recent, 8)

        stats = QFrame()
        stats.setObjectName("Card")
        s = QVBoxLayout(stats)
        s.setContentsMargins(14, 12, 14, 12)
        s.setSpacing(8)
        sh = QHBoxLayout()
        st = QLabel("今日统计")
        st.setObjectName("H2")
        auto = QLabel("自动刷新")
        auto.setObjectName("Mono")
        sh.addWidget(st)
        sh.addStretch(1)
        sh.addWidget(auto)
        s.addLayout(sh)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.stat_words = StatBox("累计转写", "0", "字")
        self.stat_time = StatBox("节省击键", "0", "分钟", SECONDARY)
        self.stat_today = StatBox("今日条数", "0", "条", SECONDARY)
        self.stat_level = StatBox("纠错档位", "保守", "", TEXT)
        grid.addWidget(self.stat_words, 0, 0)
        grid.addWidget(self.stat_time, 0, 1)
        grid.addWidget(self.stat_today, 1, 0)
        grid.addWidget(self.stat_level, 1, 1)
        s.addLayout(grid, 1)
        bottom.addWidget(stats, 5)
        lay.addLayout(bottom)

        self.refresh_stats()

    def _hotkey_label(self):
        key = self._cfg.get("hotkey", "alt_r")
        return HOTKEY_LABELS.get(key, key)

    def _apply_record_style(self, recording):
        """空闲是主色按钮；录音中切成暖色「结束并写入」，让状态一眼可辨。"""
        bg, fg, hover = (
            (TERTIARY, "#3a1a00", "#ffd0ad") if recording
            else (PRIMARY, "#002e6a", "#c4d6ff")
        )
        self.record_btn.setStyleSheet(
            "QPushButton#Record { background: %s; color: %s; border: none;"
            " border-radius: %s; padding: 14px 28px; font-size: 18px; font-weight: 600; }"
            "QPushButton#Record:hover { background: %s; }" % (bg, fg, RADIUS, hover)
        )
        self.record_btn.setIcon(make_glyph("mic", fg, 22))

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh_stats(self):
        cfg = load_cfg()
        self._cfg = cfg
        self._model_ok = model_ready(cfg)
        hist = load_history()
        words = sum(len(x.get("final", "")) for x in hist)
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = sum(1 for x in hist if str(x.get("ts", ""))[:10] == today)
        self.stat_words.setVisible(True)
        self._set_stat(self.stat_words, str(words), "字")
        self._set_stat(self.stat_time, str(max(0, words // 40)), "分钟")
        self._set_stat(self.stat_today, str(today_count), "条")
        self._set_stat(self.stat_level, LEVEL_LABELS.get(
            cfg.get("refine", {}).get("level", "conservative"), "保守"
        ), "")
        self.model_label.setText(self._model_text(cfg))
        self.hotkey_hint.setText("全局唤醒   " + self._hotkey_label())
        self._clear_layout(self.recent_box)
        if not hist:
            empty = QLabel("还没有输入记录。按住热键说一句，这里会出现最近 5 条。")
            empty.setObjectName("Muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.recent_box.addStretch(1)
            self.recent_box.addWidget(empty)
            self.recent_box.addStretch(1)
        else:
            for x in reversed(hist[-5:]):
                row = QFrame()
                row.setObjectName("Row")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(12, 8, 12, 8)
                rl.setSpacing(10)
                tm = QLabel(x.get("ts", "")[11:19])
                tm.setObjectName("Mono")
                tm.setFixedWidth(64)
                text = QLabel(elide(x.get("final", "").replace("\n", " "), 520, QFont(FONT_FAMILY, 14)))
                text.setStyleSheet("font-size: 14px;")
                ok = QLabel("已注入")
                ok.setStyleSheet("color: %s; font-size: 13px;" % SECONDARY)
                rl.addWidget(tm)
                rl.addWidget(text, 1)
                rl.addWidget(ok)
                self.recent_box.addWidget(row)
            self.recent_box.addStretch(1)

    def _set_stat(self, box, value, unit=""):
        label = box.findChildren(QLabel)[-1]
        label.setText("{} {}".format(value, unit).strip())

    def _model_text(self, cfg):
        if not self._model_ok:
            return "模型未就绪 · 去设置里指定模型目录"
        return "{} · 本地".format(short_model_name(cfg))

    def update_config(self, cfg):
        self._cfg = cfg
        self._model_ok = model_ready(cfg)
        self.refresh_stats()
        self.set_status("IDLE")

    def set_status(self, state, text=""):
        labels = {"IDLE": "就绪 · 待命", "RECORDING": "录音中 · 正在采集",
                  "TRANSCRIBING": "转写中", "REFINING": "纠错中",
                  "INJECTING": "写入中", "ERROR": "出错了"}
        color = STATE_CONFIG.get(state, {"color": PRIMARY})["color"]
        self.dot.setStyleSheet("color: %s; font-size: 14px;" % color)
        self.status.setText(labels.get(state, state))
        if state == "RECORDING":
            self.record_btn.setText("结束并写入")
        elif state == "IDLE":
            self.record_btn.setText("开始说话")
        self._apply_record_style(state == "RECORDING")
        if state == "IDLE" and not self._model_ok:
            self.status.setText("模型未就绪")
            self.hint.setText("先到设置里指定 faster-whisper 模型目录")
            self.dot.setStyleSheet("color: %s; font-size: 14px;" % TERTIARY)
        elif state == "IDLE":
            self.hint.setText("按一下开始，再按一次结束 · 文本自动写入当前光标处")


# --------------------------------------------------------------------------
# 页面：历史
# --------------------------------------------------------------------------

class HistoryPage(QWidget):
    def __init__(self):
        super().__init__()
        self._filter = "all"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        top = QFrame()
        top.setObjectName("Banner")
        top.setFixedHeight(52)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(20, 0, 20, 0)
        tip = QLabel("音频默认不留存 · 历史只保存纯文本")
        tip.setStyleSheet("color: %s; font-size: 14px;" % SECONDARY)
        refresh = QPushButton("刷新")
        refresh.setObjectName("Ghost")
        refresh.clicked.connect(self.reload)
        tl.addWidget(tip)
        tl.addStretch(1)
        tl.addWidget(refresh)
        lay.addWidget(top)

        body = QHBoxLayout()
        body.setContentsMargins(20, 14, 20, 18)
        body.setSpacing(12)
        left = QFrame()
        left.setObjectName("Card")
        left.setFixedWidth(400)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("检索转写文字…")
        self.search.textChanged.connect(self.reload)
        ll.addWidget(self.search)
        chips = QHBoxLayout()
        chips.setSpacing(4)
        self.chip_buttons = {}
        for key, label in (("today", "今天"), ("week", "本周"),
                           ("month", "本月"), ("all", "全部")):
            b = QPushButton(label)
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setChecked(key == "all")
            b.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            chips.addWidget(b)
            self.chip_buttons[key] = b
        chips.addStretch(1)
        ll.addLayout(chips)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show_detail)
        ll.addWidget(self.list, 1)
        self.count = QLabel("0 条")
        self.count.setObjectName("Mono")
        ll.addWidget(self.count)
        body.addWidget(left)

        right = QFrame()
        right.setObjectName("Card")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail = QWidget()
        self.detail_lay = QVBoxLayout(self.detail)
        self.detail_lay.setContentsMargins(18, 16, 18, 16)
        self.detail_lay.setSpacing(10)
        self.detail_scroll.setWidget(self.detail)
        rl.addWidget(self.detail_scroll)
        body.addWidget(right, 1)
        lay.addLayout(body, 1)

        self._items = []
        self.reload()

    def _set_filter(self, key):
        self._filter = key
        self.reload()

    def _in_range(self, ts):
        dt = parse_ts(ts)
        if dt is None or self._filter == "all":
            return True
        now = datetime.now()
        if self._filter == "today":
            return dt.date() == now.date()
        if self._filter == "week":
            return dt >= now - timedelta(days=7)
        return dt.year == now.year and dt.month == now.month

    def reload(self):
        text = self.search.text().strip().lower() if hasattr(self, "search") else ""
        hist = load_history()
        self._items = [
            x for x in hist
            if self._in_range(x.get("ts", ""))
            and (not text or text in (x.get("final", "") + x.get("raw", "")).lower())
        ]
        self.list.blockSignals(True)
        self.list.clear()
        for x in reversed(self._items):
            preview = x.get("final", "").replace("\n", " ")
            item = QListWidgetItem("{}  {}".format(x.get("ts", "")[11:19], elide(
                preview, 350, QFont(FONT_FAMILY, 14)))
            )
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.count.setText("{} 条".format(len(self._items)))
        if self._items:
            self.list.setCurrentRow(0)
            self._show_detail(0)
        else:
            self._show_empty()

    def _clear_detail(self):
        while self.detail_lay.count():
            item = self.detail_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_empty(self):
        self._clear_detail()
        box = QLabel("暂无转写记录\n\n去首页说一句，或按一下热键开始录音。")
        box.setObjectName("Muted")
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_lay.addStretch(1)
        self.detail_lay.addWidget(box)
        self.detail_lay.addStretch(1)

    def _card(self, title, text, accent=OUTLINE_VARIANT, mono=False):
        frame = QFrame()
        frame.setObjectName("Inner")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("Mono")
        fl.addWidget(t)
        body = QLabel(text or "（空）")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(
            "font-family: '%s'; font-size: 14px; color: %s;"
            % (FONT_MONO if mono else FONT_FAMILY, TEXT_VARIANT if accent == OUTLINE_VARIANT else TEXT)
        )
        fl.addWidget(body)
        return frame

    def _show_detail(self, row):
        if row < 0 or row >= len(self._items):
            return
        x = list(reversed(self._items))[row]
        self._clear_detail()
        head = QHBoxLayout()
        title = QLabel("转写详情")
        title.setObjectName("H1")
        copy = QPushButton("复制结果")
        copy.setObjectName("Primary")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(x.get("final", "")))
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(copy)
        hw = QWidget()
        hw.setLayout(head)
        self.detail_lay.addWidget(hw)
        self.detail_lay.addWidget(self._card("原始转写", x.get("raw", ""), mono=True))
        self.detail_lay.addWidget(self._card("纠错结果 · 最终写入", x.get("final", ""), PRIMARY, mono=True))
        grid = QGridLayout()
        grid.setSpacing(8)
        values = [("时长", "{} 秒".format(x.get("duration_s", "?"))),
                  ("字数", "{} 字".format(len(x.get("final", "")))),
                  ("时间", x.get("ts", "")[11:19]),
                  ("状态", "已注入")]
        for i, (k, v) in enumerate(values):
            grid.addWidget(StatBox(k, v), i // 2, i % 2)
        gw = QWidget()
        gw.setLayout(grid)
        self.detail_lay.addWidget(gw)
        privacy = QLabel("安全策略：音频默认不留存，历史仅保存纯文本。")
        privacy.setObjectName("Mono")
        self.detail_lay.addWidget(privacy)
        self.detail_lay.addStretch(1)



# --------------------------------------------------------------------------
# 页面：词库
# --------------------------------------------------------------------------

class DictionaryPage(QWidget):
    def __init__(self):
        super().__init__()
        self._tab = "hot"
        self._rows = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        head = QHBoxLayout()
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.tab_buttons = {}
        for key, label in (("hot", "专有热词"), ("rule", "替换规则"), ("learn", "学习记录")):
            b = QPushButton(label)
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setChecked(key == "hot")
            b.clicked.connect(lambda _=False, k=key: self._set_tab(k))
            tabs.addWidget(b)
            self.tab_buttons[key] = b
        head.addLayout(tabs)
        head.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索词条…")
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self._reload)
        export = QPushButton("导出")
        export.setObjectName("Ghost")
        export.clicked.connect(self._export)
        head.addWidget(self.search)
        head.addWidget(export)
        lay.addLayout(head)

        hint = QLabel("热词影响识别提示词，替换规则作用于纠错输出；学习规则来自历史纠错沉淀。")
        hint.setStyleSheet(
            "color: %s; background: %s; border: 1px solid %s;"
            "border-radius: 4px; padding: 10px 14px; font-size: 14px;"
            % (TEXT_VARIANT, SURFACE_LOW, OUTLINE_VARIANT)
        )
        lay.addWidget(hint)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["词条 / 原词", "指定写法", "类型", "来源", "命中"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        lay.addWidget(self.table, 1)

        self.footer = QLabel()
        self.footer.setObjectName("Mono")
        lay.addWidget(self.footer)
        self._reload()

    def _set_tab(self, key):
        self._tab = key
        self._reload()

    def _reload(self):
        text = self.search.text().strip().lower() if hasattr(self, "search") else ""
        terms, mappings = load_words()
        rows = []
        if self._tab == "hot":
            rows = [(t, "（热词）", "热词", "本机词库", "—") for t in terms]
        elif self._tab == "rule":
            rows = [(k, v, "替换规则", "本机词库", "—") for k, v in mappings]
        else:
            rows = [(k, v, "学习规则", "学习记录", str(c))
                    for k, v, c in load_learned()]
        rows = [r for r in rows if not text or text in (" ".join(r)).lower()]
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                if j == 1:
                    item.setForeground(QColor(PRIMARY))
                elif j >= 2:
                    item.setForeground(QColor(OUTLINE))
                self.table.setItem(i, j, item)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 120)
        self.footer.setText("当前 {} 条记录 · 词库文件：词库.txt".format(len(rows)))
        self._rows = rows

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出词库", "mao_vocabulary.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    [{"term": r[0], "writing": r[1], "type": r[2], "source": r[3]}
                     for r in self._rows],
                    f, ensure_ascii=False, indent=2,
                )
            self.footer.setText("已导出 {} 条记录到 {}".format(len(self._rows), Path(path).name))
        except OSError as e:
            self.footer.setText("导出失败：{}".format(e))


# --------------------------------------------------------------------------
# 页面：设置
# --------------------------------------------------------------------------

class SettingsPage(QWidget):
    saved = Signal(dict)

    SECTIONS = ["通用与热键", "识别模型", "AI 保守纠错", "文本注入", "隐私与数据", "关于"]

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        nav = QWidget()
        nav.setFixedWidth(200)
        nav.setStyleSheet("background: %s; border-right: 1px solid %s;" % (SURFACE_LOW, OUTLINE_VARIANT))
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(10, 12, 10, 12)
        nl.setSpacing(4)
        label = QLabel("配置分组")
        label.setObjectName("Mono")
        nl.addWidget(label)
        self.nav_buttons = []
        for i, name in enumerate(self.SECTIONS):
            b = QPushButton(name)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, idx=i: self._set_section(idx))
            nl.addWidget(b)
            self.nav_buttons.append(b)
        nl.addStretch(1)
        lay.addWidget(nav)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.stack = QStackedWidget()
        self._build_sections()
        rl.addWidget(self.stack, 1)

        bottom = QFrame()
        bottom.setObjectName("Banner")
        bottom.setFixedHeight(56)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(14, 0, 14, 0)
        self.result = QLabel("修改后点保存，热键会重载监听")
        self.result.setObjectName("Mono")
        reset = QPushButton("放弃修改")
        reset.setObjectName("Ghost")
        reset.clicked.connect(lambda: self.load_fields())
        save = QPushButton("保存设置")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        self.save_btn = save
        bl.addWidget(self.result)
        bl.addStretch(1)
        bl.addWidget(reset)
        bl.addWidget(save)
        rl.addWidget(bottom)
        lay.addWidget(right, 1)

        self.load_fields()
        self._set_section(0)

    def _scroll(self, widget):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(widget)
        return sc

    def _page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)
        return w, v

    def _section_head(self, layout, title, desc):
        t = QLabel(title)
        t.setObjectName("H1")
        d = QLabel(desc)
        d.setObjectName("Muted")
        d.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(d)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: %s;" % OUTLINE_VARIANT)
        layout.addWidget(line)

    def _card(self, layout, title, desc, control):
        card = QFrame()
        card.setObjectName("Inner")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(6)
        t = QLabel(title)
        t.setStyleSheet("font-size: 16px; font-weight: 600;")
        d = QLabel(desc)
        d.setObjectName("Muted")
        d.setWordWrap(True)
        cl.addWidget(t)
        cl.addWidget(d)
        cl.addWidget(control)
        layout.addWidget(card)

    def _combo(self, values, current=None):
        combo = QComboBox()
        for key, label in values:
            combo.addItem(label, key)
        if current is not None:
            idx = combo.findData(current)
            combo.setCurrentIndex(max(0, idx))
        return combo

    def _build_sections(self):
        # 0 通用与热键
        page, v = self._page()
        self._section_head(v, "通用设置与唤醒热键", "配置热键与客户端基础行为。修改热键后保存，监听会立即重载。")
        self.hotkey = self._combo([(k, HOTKEY_LABELS.get(k, k)) for k in HOTKEYS])
        self._card(v, "录音热键", "按一下开始、再按一下结束。右 Alt 在部分键盘布局等于 AltGr，冲突时改用右 Ctrl 或 F 键。", self.hotkey)
        self.settings_hotkey = self._combo(
            [("", "禁用")] + [(k, HOTKEY_LABELS.get(k, k)) for k in HOTKEYS]
        )
        self._card(v, "打开设置热键", "用于快速打开当前窗口。留空或禁用可关闭。", self.settings_hotkey)
        self.cycle_hotkey = self._combo(
            [("", "禁用")] + [(k, HOTKEY_LABELS.get(k, k)) for k in HOTKEYS]
        )
        self._card(v, "切换纠错强度热键", "在保守纠错 / 轻度规整 / 完整规整之间循环。", self.cycle_hotkey)
        v.addStretch(1)
        self.stack.addWidget(self._scroll(page))

        # 1 识别模型
        page, v = self._page()
        self._section_head(v, "识别模型（ASR）", "模型在本机运行，音频不出本机。支持任意 faster-whisper / CTranslate2 目录。")
        self.model = QLineEdit()
        self.model.setPlaceholderText(r"例如 D:\models\faster-whisper-large-v3-turbo")
        self._card(v, "模型目录", "目录需包含 model.bin（通常还有 config.json、tokenizer.json、vocabulary.json）。", self.model)
        self.language = self._combo(LANGUAGES)
        self._card(v, "识别语言", "自动检测适合中英混杂；固定中文可减少误检。", self.language)
        self.cloud_fallback = QCheckBox("本地连续失败时自动切换云端 ASR")
        self._card(v, "云端兜底", "仅在配置了云端端点与 Key 时生效；默认本地优先。", self.cloud_fallback)
        v.addStretch(1)
        self.stack.addWidget(self._scroll(page))

        # 2 纠错
        page, v = self._page()
        self._section_head(v, "AI 保守纠错", "只修明显识别错误，不扩写、不改写原意。留空 Key 则完全本地零网络。")
        self.refine_enabled = QCheckBox("启用大模型纠错")
        self._card(v, "开关", "关闭后直接输出原始转写。", self.refine_enabled)
        self.level = self._combo(LEVELS)
        self._card(v, "纠错强度", "保守纠错最小改动；轻度规整允许口语转书面；完整规整允许理顺语序。", self.level)
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("https://api.deepseek.com/v1")
        self._card(v, "服务地址", "任意 OpenAI 兼容端点，例如 DeepSeek。", self.base_url)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("留空则使用 DEEPSEEK_API_KEY 环境变量")
        self._card(v, "API Key", "只写入本机 config.json；按量计费，建议使用环境变量。", self.api_key)
        v.addStretch(1)
        self.stack.addWidget(self._scroll(page))

        # 3 注入
        page, v = self._page()
        self._section_head(v, "文本注入管线", "适配 IDE、浏览器、终端等不同前台窗口。终端类窗口走 Unicode 直注。")
        self.paste_mode = self._combo(PASTE_MODES)
        self._card(v, "注入方式", "自动模式会根据窗口类名切换；Ctrl+V 通用性最好，Unicode 不占剪贴板。", self.paste_mode)
        self.restore_delay = QDoubleSpinBox()
        self.restore_delay.setRange(0.05, 5.0)
        self.restore_delay.setSingleStep(0.05)
        self.restore_delay.setSuffix(" 秒")
        self._card(v, "剪贴板恢复延迟", "慢应用（Electron、远程桌面）可适当调大，避免粘贴未完成就恢复剪贴板。", self.restore_delay)
        self.same_focus = QCheckBox("注入前校验前台窗口未切换")
        self._card(v, "焦点校验", "录音结束后如果切到了别的窗口，取消注入并把文本留在剪贴板。", self.same_focus)
        v.addStretch(1)
        self.stack.addWidget(self._scroll(page))

        # 4 隐私
        page, v = self._page()
        self._section_head(v, "隐私与数据", "音频默认不留存；历史与学习规则均为明文落盘，默认关闭。")
        self.history_cb = QCheckBox("记录输入历史（纯文本）")
        self._card(v, "历史记录", "开启后每次成功注入都会写入 history.json，可在历史页查看。", self.history_cb)
        self.learn_cb = QCheckBox("自学习纠错规则")
        self._card(v, "学习规则", "从润色差异中沉淀「原词→修正」，写入 learned_rules.json。", self.learn_cb)
        note = QLabel("音频只在内存中处理；开启纠错时，识别文本会发往你配置的 LLM 端点。")
        note.setWordWrap(True)
        note.setStyleSheet("color: %s; font-size: 14px;" % TERTIARY)
        v.addWidget(note)
        v.addStretch(1)
        self.stack.addWidget(self._scroll(page))

        # 5 关于
        page, v = self._page()
        self._section_head(v, "关于 mao-voice", "Windows 本地语音输入客户端。")
        info = QFrame()
        info.setObjectName("Inner")
        il = QVBoxLayout(info)
        il.setContentsMargins(10, 8, 10, 8)
        for k, val in (("版本", "v{} · 客户端预览".format(__version__)),
                       ("UI", "PySide6 / Qt Widgets · 无边框"),
                       ("识别", "faster-whisper / CTranslate2"),
                       ("许可", "Apache-2.0")):
            row = QHBoxLayout()
            a = QLabel(k)
            a.setObjectName("Mono")
            b = QLabel(val)
            b.setStyleSheet("font-family: '%s'; font-size: 14px;" % FONT_MONO)
            row.addWidget(a)
            row.addStretch(1)
            row.addWidget(b)
            il.addLayout(row)
        v.addWidget(info)
        v.addStretch(1)
        self.stack.addWidget(self._scroll(page))

    def _set_section(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == idx)
            b.setStyleSheet(
                "text-align:left; padding:9px 12px; border:none; border-radius:4px;"
                + "font-size: 15px;"
                + ("background:%s; color:%s;" % (SURFACE_HIGHEST, TEXT)
                   if i == idx else "background:transparent; color:%s;" % TEXT_VARIANT)
            )

    def load_fields(self, cfg=None):
        cfg = cfg or load_cfg()
        self._set_combo(self.hotkey, cfg.get("hotkey", "alt_r"))
        self._set_combo(self.settings_hotkey, cfg.get("settings_hotkey", "f8"))
        self._set_combo(self.cycle_hotkey, cfg.get("refine_cycle_hotkey", "f9"))
        self.model.setText(cfg.get("asr", {}).get("model", ""))
        self._set_combo(self.language, cfg.get("asr", {}).get("language"))
        self.cloud_fallback.setChecked(bool(cfg.get("asr", {}).get("cloud_fallback", True)))
        self.refine_enabled.setChecked(bool(cfg.get("refine", {}).get("enabled", True)))
        self._set_combo(self.level, cfg.get("refine", {}).get("level", "conservative"))
        self.base_url.setText(cfg.get("refine", {}).get("base_url", ""))
        self.api_key.setText(cfg.get("refine", {}).get("api_key", ""))
        self._set_combo(self.paste_mode, cfg.get("inject", {}).get("paste_mode", "auto"))
        self.restore_delay.setValue(float(cfg.get("inject", {}).get("restore_delay_sec", 0.2)))
        self.same_focus.setChecked(bool(cfg.get("inject", {}).get("require_same_focus", True)))
        self.history_cb.setChecked(bool(cfg.get("history", {}).get("enabled", False)))
        self.learn_cb.setChecked(bool(cfg.get("learn", {}).get("enabled", False)))

    @staticmethod
    def _set_combo(combo, value):
        idx = combo.findData(value)
        combo.setCurrentIndex(max(0, idx))

    def _save(self):
        model = self.model.text().strip()
        if not model:
            self.show_result(False, "模型目录不能为空")
            return
        payload = {
            "hotkey": self.hotkey.currentData(),
            "settings_hotkey": self.settings_hotkey.currentData(),
            "refine_cycle_hotkey": self.cycle_hotkey.currentData(),
            "asr": {
                "model": model,
                "language": self.language.currentData(),
                "cloud_fallback": self.cloud_fallback.isChecked(),
            },
            "refine": {
                "enabled": self.refine_enabled.isChecked(),
                "level": self.level.currentData(),
                "base_url": self.base_url.text().strip(),
                "api_key": self.api_key.text().strip(),
            },
            "inject": {
                "paste_mode": self.paste_mode.currentData(),
                "restore_delay_sec": round(self.restore_delay.value(), 2),
                "require_same_focus": self.same_focus.isChecked(),
            },
            "history": {"enabled": self.history_cb.isChecked()},
            "learn": {"enabled": self.learn_cb.isChecked()},
        }
        self.saved.emit(payload)

    def show_result(self, ok, message):
        self.result.setStyleSheet("color: %s;" % (SUCCESS if ok else ERROR))
        self.result.setText(message)


# --------------------------------------------------------------------------
# 主窗口
# --------------------------------------------------------------------------

class TopBar(QWidget):
    def __init__(self, window):
        super().__init__()
        self._window = window
        self._drag = None
        self.setObjectName("TopBar")
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 8, 0)
        lay.setSpacing(10)
        lay.addWidget(LogoLabel(26))
        title = QLabel("mao-voice")
        title.setObjectName("Title")
        lay.addWidget(title)

        self.status_pill = QFrame()
        self.status_pill.setObjectName("StatusPill")
        self.status_pill.setStyleSheet(
            "QFrame#StatusPill { background: %s; border: 1px solid %s; border-radius: 6px; }"
            "QFrame#StatusPill QLabel { background: transparent; border: none; }"
            % (SURFACE_CONTAINER, OUTLINE_VARIANT)
        )
        pl = QHBoxLayout(self.status_pill)
        pl.setContentsMargins(9, 2, 9, 2)
        pl.setSpacing(6)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: %s; font-size: 12px;" % SECONDARY)
        self.status_text = QLabel("就绪")
        self.status_text.setStyleSheet(
            "font-family: '%s'; font-size: 13px; color: %s;" % (FONT_MONO, TEXT_VARIANT)
        )
        pl.addWidget(self.status_dot)
        pl.addWidget(self.status_text)
        lay.addWidget(self.status_pill)
        lay.addStretch(1)

        self.model_chip = QLabel()
        self.model_chip.setObjectName("Mono")
        self.model_chip.setStyleSheet(
            "font-size: 13px; font-family: '%s'; color: %s;" % (FONT_MONO, OUTLINE)
        )
        lay.addWidget(self.model_chip)

        for text, tip, slot in (
            ("—", "最小化", self._window.showMinimized),
            ("□", "最大化", self._toggle_max),
            ("✕", "隐藏到托盘", self._window.close),
        ):
            b = QPushButton(text)
            b.setObjectName("WinBtn")
            b.setToolTip(tip)
            b.setFixedSize(32, 28)
            b.clicked.connect(slot)
            lay.addWidget(b)

    def _toggle_max(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None

    def mouseDoubleClickEvent(self, event):
        self._toggle_max()


class MainWindow(QWidget):
    settings_saved = Signal(dict)
    quit_requested = Signal()

    PAGE_NAMES = ("首页", "历史", "词库", "设置")

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint)
        self.setObjectName("Root")
        self.setStyleSheet(QSS)
        self.resize(1140, 760)
        self.setMinimumSize(1000, 680)
        self.setWindowTitle("mao-voice")

        cfg = load_cfg()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top = TopBar(self)
        root.addWidget(self.top)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        self.home = HomePage()
        self.history_page = HistoryPage()
        self.dictionary_page = DictionaryPage()
        self.settings_page = SettingsPage()
        self.pages = {
            "首页": self.home,
            "历史": self.history_page,
            "词库": self.dictionary_page,
            "设置": self.settings_page,
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        root.addWidget(self._build_statusbar())

        self.home.history_clicked.connect(lambda: self.show_page("历史"))
        self.settings_page.saved.connect(self.settings_saved)
        self._apply_cfg(cfg)
        self._set_page("首页")

    def _build_sidebar(self):
        side = QWidget()
        side.setObjectName("SideBar")
        side.setFixedWidth(216)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(3)
        lab = QLabel("工作区")
        lab.setObjectName("Mono")
        lab.setStyleSheet("font-size: 13px; letter-spacing: 1px; padding: 0 6px;")
        lay.addWidget(lab)
        self.nav_buttons = {}
        for name, kind in (("首页", "mic"), ("历史", "history"),
                           ("词库", "dict"), ("设置", "settings")):
            b = NavButton(name, kind)
            b.clicked.connect(lambda _=False, n=name: self._set_page(n))
            lay.addWidget(b)
            self.nav_buttons[name] = b

        lay.addStretch(1)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: %s;" % OUTLINE_VARIANT)
        lay.addWidget(line)
        lab2 = QLabel("系统")
        lab2.setObjectName("Mono")
        lab2.setStyleSheet("font-size: 13px; letter-spacing: 1px; padding: 6px 6px 0;")
        lay.addWidget(lab2)
        status = QLabel("托盘常驻运行中")
        status.setObjectName("Mono")
        status.setStyleSheet("font-size: 13px; padding: 0 6px;")
        lay.addWidget(status)
        exit_btn = QPushButton("退出程序")
        exit_btn.setObjectName("Nav")
        exit_btn.setIcon(make_glyph("power", TEXT_VARIANT, 18))
        exit_btn.setIconSize(QSize(18, 18))
        exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exit_btn.clicked.connect(lambda: self.quit_requested.emit())
        lay.addWidget(exit_btn)
        ver = QLabel("v{} · 客户端预览".format(__version__))
        ver.setObjectName("Mono")
        ver.setStyleSheet("font-size: 13px; padding: 6px;")
        ver.setWordWrap(True)
        lay.addWidget(ver)
        return side

    def _build_statusbar(self):
        bar = QWidget()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(10)
        self.sb_dot = QLabel("●")
        self.sb_dot.setStyleSheet("color: %s; font-size: 13px;" % SECONDARY)
        self.sb_model = QLabel()
        self.sb_level = QLabel()
        self.sb_paste = QLabel()
        for w in (self.sb_model, self.sb_level, self.sb_paste):
            w.setObjectName("Mono")
            w.setStyleSheet("font-size: 13px;")
        lay.addWidget(self.sb_dot)
        lay.addWidget(self.sb_model)
        lay.addWidget(self._sb_sep())
        lay.addWidget(self.sb_level)
        lay.addWidget(self._sb_sep())
        lay.addWidget(self.sb_paste)
        lay.addStretch(1)
        privacy = QLabel("音频: 不留存")
        privacy.setObjectName("Mono")
        privacy.setStyleSheet("color: %s; font-size: 13px;" % SECONDARY)
        lay.addWidget(privacy)
        lay.addWidget(self._sb_sep())
        ver = QLabel("v{}".format(__version__))
        ver.setObjectName("Mono")
        ver.setStyleSheet("font-size: 13px;")
        lay.addWidget(ver)
        grip = QSizeGrip(bar)
        grip.setFixedSize(12, 12)
        lay.addWidget(grip)
        return bar

    @staticmethod
    def _sb_sep():
        s = QLabel("|")
        s.setObjectName("Mono")
        s.setStyleSheet("font-size: 13px;")
        return s

    def _apply_cfg(self, cfg):
        self.settings_page.load_fields(cfg)
        self._update_statusbar(cfg)
        self.home.update_config(cfg)

    def _update_statusbar(self, cfg):
        model = short_model_name(cfg)
        self.sb_model.setText("模型: " + model)
        self.sb_level.setText("纠错: " + LEVEL_LABELS.get(
            cfg.get("refine", {}).get("level", "conservative"), "保守"
        ))
        self.sb_paste.setText("注入: " + PASTE_LABELS.get(
            cfg.get("inject", {}).get("paste_mode", "auto"), "自动"
        ))
        self.top.model_chip.setText("本地模型 · " + model)

    def _set_page(self, name):
        self.stack.setCurrentWidget(self.pages[name])
        for n, b in self.nav_buttons.items():
            b.set_active(n == name)
        if name == "历史":
            self.history_page.reload()
        elif name == "首页":
            self.home.refresh_stats()

    def show_page(self, name):
        if name in self.pages:
            self._set_page(name)
        self.show()
        self.raise_()
        self.activateWindow()

    def set_status(self, state, text=""):
        labels = {
            "IDLE": ("就绪", SECONDARY),
            "RECORDING": ("录音中", PRIMARY),
            "TRANSCRIBING": ("转写中", TERTIARY),
            "REFINING": ("纠错中", SECONDARY),
            "INJECTING": ("写入中", PRIMARY),
            "ERROR": ("错误", ERROR),
        }
        label, color = labels.get(state, (state, PRIMARY))
        if state == "IDLE" and not model_ready(load_cfg()):
            label, color = "模型未就绪", TERTIARY
        self.top.status_text.setText(label)
        self.top.status_dot.setStyleSheet("color: %s; font-size: 13px;" % color)
        self.home.set_status(state, text)

    def refresh_data(self, cfg=None):
        if cfg is not None:
            self._apply_cfg(cfg)
        else:
            self.home.refresh_stats()
            self._update_statusbar(load_cfg())
        self.history_page.reload()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

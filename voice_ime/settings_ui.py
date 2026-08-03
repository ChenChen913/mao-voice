# -*- coding: utf-8 -*-
"""托盘图标 + 设置窗口（v5.13.5）。

- 托盘：pystray，菜单含 开始/停止录音、打开设置、退出；
- 设置窗口：ttk.Notebook 五页签（通用/模型/LLM/词库/历史），即改即存。

所有跨线程入口（托盘回调）都通过主线程队列转发，避免直接操作 Tk。
"""
import logging
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:  # 依赖缺失时托盘功能降级（设置窗口仍可用）
    pystray = None
    Image = None
    ImageDraw = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORDS_PATH = os.path.join(BASE_DIR, "词库.txt")

HOTKEY_CHOICES = ["alt_r", "alt_l", "ctrl_r", "ctrl_l", "shift_r", "shift_l",
                  "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9",
                  "f10", "f11", "f12", "caps_lock", "space", "enter", "esc"]
LEVEL_CHOICES = ["conservative", "light", "polish"]
LEVEL_LABELS = {"conservative": "保守纠错", "light": "轻度规整", "polish": "完整规整"}


def make_tray_image():
    """生成 64x64 托盘图标（深色圆底 + 蓝色声波竖条）。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=(30, 30, 30, 255))
    bars = [(14, 22, 18, 42), (24, 14, 28, 50), (34, 10, 38, 54),
            (44, 14, 48, 50), (54, 22, 58, 42)]
    for x1, y1, x2, y2 in bars:
        d.rounded_rectangle((x1, y1, x2, y2), radius=2, fill=(74, 144, 217, 255))
    return img


class TrayIcon:
    """pystray 托盘封装：状态文本更新与退出均做异常兜底。"""

    def __init__(self, app):
        self.app = app
        self._icon = None

    def start(self):
        if pystray is None:
            logging.warning("pystray 未安装，托盘功能不可用")
            return
        menu = pystray.Menu(
            pystray.MenuItem("开始/停止录音（右 Alt）", lambda: self.app.on_toggle()),
            pystray.MenuItem("打开设置", lambda: self.app.open_settings()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda: self.app.exit_app()),
        )
        self._icon = pystray.Icon("mao-voice", make_tray_image(), "AI 语音输入法", menu)
        try:
            self._icon.run_detached()
        except Exception:
            logging.exception("托盘启动失败（不影响主程序）")
            self._icon = None

    def set_status(self, state):
        if self._icon is None:
            return
        labels = {"IDLE": "空闲", "RECORDING": "录音中", "PROCESSING": "处理中",
                  "TRANSCRIBING": "转写中", "REFINING": "润色中", "PREVIEW": "预览",
                  "INJECTING": "注入中", "ERROR": "错误"}
        try:
            self._icon.title = "AI 语音输入法 · " + labels.get(state, state)
            self._icon.update_menu()
        except Exception:
            pass

    def stop(self):
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None


class SettingsWindow:
    """设置窗口：五页签，保存即写 config.json（原子写）。"""

    def __init__(self, app, parent=None):
        self.app = app
        self.cfg = app.cfg
        self.root = tk.Toplevel(parent)
        self.root.title("AI 语音输入法 · 设置")
        self.root.geometry("640x520")
        self.root.attributes("-topmost", True)
        self._build()

    def _build(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_general = ttk.Frame(nb)
        self.tab_model = ttk.Frame(nb)
        self.tab_llm = ttk.Frame(nb)
        self.tab_words = ttk.Frame(nb)
        self.tab_history = ttk.Frame(nb)
        nb.add(self.tab_general, text="通用")
        nb.add(self.tab_model, text="模型")
        nb.add(self.tab_llm, text="LLM")
        nb.add(self.tab_words, text="词库")
        nb.add(self.tab_history, text="历史")
        self._build_general()
        self._build_model()
        self._build_llm()
        self._build_words()
        self._build_history()
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text="保存设置", command=self.save).pack(side="left")
        ttk.Button(bar, text="关闭", command=self.root.destroy).pack(side="right")

    def _build_general(self):
        f = self.tab_general
        self.var_hotkey = self._combo(f, "录音热键", HOTKEY_CHOICES, self.cfg.get("hotkey", "alt_r"), 0)
        self.var_cycle = self._combo(f, "润色切换热键", HOTKEY_CHOICES, self.cfg.get("refine_cycle_hotkey", "f9"), 1)
        self.var_settings_hk = self._combo(f, "设置热键", HOTKEY_CHOICES, self.cfg.get("settings_hotkey", "f8"), 2)
        self.var_language = self._combo(f, "识别语言", ["auto", "zh"], "auto" if not self.cfg.get("asr", {}).get("language") else "zh", 3)
        self.var_auto_stop = self._spin(f, "静音自动停止（秒，0=关闭）", 0, 30, self.cfg.get("recorder", {}).get("auto_stop_silence_sec", 0), 4)
        self.var_preview = self._spin(f, "状态提示时长（秒）", 0.5, 10.0, self.cfg.get("ui", {}).get("preview_sec", 1.5), 5)
        self.var_device = self._device_combo(f, 6)

    def _build_model(self):
        f = self.tab_model
        self.var_engine = self._combo(f, "识别引擎", ["whisper", "cloud"], self.cfg.get("asr", {}).get("engine", "whisper"), 0)
        self.var_model = self._entry(f, "本地模型路径（相对 voice_ime/）", self.cfg.get("asr", {}).get("model", "small"), 1)
        self.var_cloud_url = self._entry(f, "云端 Base URL", self.cfg.get("asr", {}).get("cloud", {}).get("base_url", ""), 2)
        self.var_cloud_key = self._entry(f, "云端 API Key", self.cfg.get("asr", {}).get("cloud", {}).get("api_key", ""), 3)
        self.var_cloud_model = self._entry(f, "云端模型名", self.cfg.get("asr", {}).get("cloud", {}).get("model", "whisper-1"), 4)
        ttk.Button(f, text="一键下载模型（ModelScope）", command=self._download_model).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=6)
        self.download_label = ttk.Label(f, text="下载约 1.5GB（medium）/ 480MB（small），完成后自动更新配置")
        self.download_label.grid(row=6, column=0, columnspan=2, sticky="w", padx=8)

    def _build_llm(self):
        f = self.tab_llm
        refine = self.cfg.get("refine", {})
        self.var_refine_enabled = tk.BooleanVar(value=bool(refine.get("enabled", True)))
        ttk.Checkbutton(f, text="启用 LLM 保守纠错", variable=self.var_refine_enabled).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        self.var_llm_url = self._entry(f, "Base URL", refine.get("base_url", "https://api.deepseek.com/v1"), 1)
        self.var_llm_key = self._entry(f, "API Key（留空读取 DEEPSEEK_API_KEY）", refine.get("api_key", ""), 2)
        self.var_llm_model = self._entry(f, "模型", refine.get("model", "deepseek-chat"), 3)
        self.var_level = self._combo(f, "润色强度", LEVEL_CHOICES, refine.get("level", "conservative"), 4,
                                     display={k: f"{v}（{LEVEL_LABELS[k]}）" for k, v in zip(LEVEL_CHOICES, LEVEL_CHOICES)})
        self.var_timeout = self._spin(f, "超时（秒）", 5, 120, refine.get("timeout_sec", 30), 5)

    def _build_words(self):
        f = self.tab_words
        ttk.Label(f, text="每行一条：# 注释 / 词条 / 原词=指定写法").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.words_text = tk.Text(f, width=70, height=16)
        self.words_text.grid(row=1, column=0, padx=8, pady=4)
        try:
            self.words_text.insert("1.0", open(WORDS_PATH, "r", encoding="utf-8-sig").read())
        except OSError:
            pass
        ttk.Button(f, text="保存词库", command=self._save_words).grid(row=2, column=0, sticky="w", padx=8, pady=4)

    def _build_history(self):
        f = self.tab_history
        ttk.Button(f, text="刷新", command=self._refresh_history).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Button(f, text="清空历史", command=self._clear_history).grid(row=0, column=1, sticky="w", padx=8, pady=4)
        self.history_list = tk.Listbox(f, width=90, height=18)
        self.history_list.grid(row=1, column=0, columnspan=2, padx=8, pady=4)
        self._refresh_history()

    # ---------- 控件辅助 ----------
    def _combo(self, parent, label, choices, value, row, display=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        var = tk.StringVar(value=value)
        c = ttk.Combobox(parent, textvariable=var, values=choices, state="readonly", width=40)
        c.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        return var

    def _entry(self, parent, label, value, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        var = tk.StringVar(value=str(value))
        e = ttk.Entry(parent, textvariable=var, width=44)
        e.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        return var

    def _spin(self, parent, label, lo, hi, value, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        var = tk.DoubleVar(value=float(value))
        s = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=42)
        s.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        return var

    def _device_combo(self, parent, row):
        ttk.Label(parent, text="麦克风设备").grid(row=row, column=0, sticky="e", padx=8, pady=4)
        devices = [""]
        try:
            import sounddevice as sd
            devices += [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]
        except Exception:
            pass
        var = tk.StringVar(value=self.cfg.get("recorder", {}).get("device", ""))
        ttk.Combobox(parent, textvariable=var, values=devices, width=40).grid(
            row=row, column=1, sticky="w", padx=8, pady=4)
        return var

    # ---------- 动作 ----------
    def save(self):
        r = self.cfg.setdefault("recorder", {})
        asr = self.cfg.setdefault("asr", {})
        refine = self.cfg.setdefault("refine", {})
        ui = self.cfg.setdefault("ui", {})
        cloud = asr.setdefault("cloud", {})
        try:
            self.cfg["hotkey"] = self.var_hotkey.get()
            self.cfg["refine_cycle_hotkey"] = self.var_cycle.get()
            self.cfg["settings_hotkey"] = self.var_settings_hk.get()
            asr["language"] = None if self.var_language.get() == "auto" else "zh"
            r["auto_stop_silence_sec"] = int(float(self.var_auto_stop.get()))
            ui["preview_sec"] = float(self.var_preview.get())
            r["device"] = self.var_device.get()
            asr["engine"] = self.var_engine.get()
            asr["model"] = self.var_model.get().strip()
            cloud["base_url"] = self.var_cloud_url.get().strip()
            cloud["api_key"] = self.var_cloud_key.get().strip()
            cloud["model"] = self.var_cloud_model.get().strip() or "whisper-1"
            refine["enabled"] = bool(self.var_refine_enabled.get())
            refine["base_url"] = self.var_llm_url.get().strip()
            refine["api_key"] = self.var_llm_key.get().strip()
            refine["model"] = self.var_llm_model.get().strip() or "deepseek-chat"
            refine["level"] = self.var_level.get()
            refine["timeout_sec"] = int(float(self.var_timeout.get()))
            self.app.save_cfg()
            messagebox.showinfo("保存成功", "设置已保存（录音热键等需重启生效）", parent=self.root)
        except Exception as e:
            messagebox.showerror("保存失败", str(e), parent=self.root)

    def _save_words(self):
        try:
            with open(WORDS_PATH, "w", encoding="utf-8") as f:
                f.write(self.words_text.get("1.0", "end"))
            messagebox.showinfo("保存成功", "词库已保存（下次转写生效）", parent=self.root)
        except OSError as e:
            messagebox.showerror("保存失败", str(e), parent=self.root)

    def _refresh_history(self):
        self.history_list.delete(0, "end")
        store = getattr(self.app, "history", None)
        if store is None:
            return
        for item in reversed(store.items()):
            self.history_list.insert("end", "[{}] {}".format(item.get("ts", "?"), item.get("final", "")))

    def _clear_history(self):
        store = getattr(self.app, "history", None)
        if store is not None:
            store.clear()
        self._refresh_history()

    def _download_model(self):
        def work():
            try:
                import download_model
                download_model.main(["--model", "medium"])
                self.root.after(0, lambda: self.download_label.config(text="下载完成，模型路径已更新"))
            except SystemExit:
                pass
            except Exception as e:
                self.root.after(0, lambda: self.download_label.config(text="下载失败：" + str(e)))
        threading.Thread(target=work, daemon=True).start()
        self.download_label.config(text="下载中…请保持网络通畅（可随时关闭窗口）")

    def lift(self):
        self.root.deiconify()
        self.root.lift()

# -*- coding: utf-8 -*-
"""客户端版 App：复用 main.App 的引擎逻辑，补上设置保存与界面刷新。"""
import logging
import threading

import autostart
import main
import safe_inject
from config import save_config
from history import HistoryStore, clear_entries, remove_entry
from learn import LearnedRules


def _merge(cfg, updates):
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value


class ClientApp(main.App):
    def __init__(self, cfg, overlay, root, window):
        super().__init__(cfg, overlay, root)
        self.window = window
        self._last_client_state = None

    def _open_settings_impl(self):
        self.window.show_page("设置")

    def _update_tray(self, state):
        super()._update_tray(state)
        if state != self._last_client_state:
            self._last_client_state = state
            try:
                self.window.set_status(state)
                if state == "IDLE":
                    self.window.refresh_data()
            except Exception:
                logging.exception("客户端界面刷新失败")

    def apply_settings(self, payload):
        """保存设置并尽量立即生效；返回 (是否成功, 说明)。"""
        old_model = self.cfg.get("asr", {}).get("model")
        _merge(self.cfg, payload)
        try:
            save_config(self.cfg)
        except Exception as e:
            logging.exception("保存配置失败")
            return False, "保存失败：{}".format(e)

        new_model = self.cfg.get("asr", {}).get("model")
        if new_model != old_model:
            try:
                self.asr = main.make_asr(self.cfg)
            except Exception as e:
                logging.exception("重建识别引擎失败")
                return False, "配置已保存，但识别引擎重建失败：{}".format(e)
            self._warmup_engine()
        else:
            self._report_engine_state()

        hist_cfg = self.cfg.get("history", {})
        if hist_cfg.get("enabled", False):
            try:
                self.history = HistoryStore(
                    max_entries=hist_cfg.get("max_entries", 100)
                )
            except Exception:
                logging.exception("初始化历史记录失败")
                self.history = None
        else:
            self.history = None

        learn_cfg = self.cfg.get("learn", {})
        if learn_cfg.get("enabled", False):
            try:
                self.learn = LearnedRules(
                    min_count=learn_cfg.get("min_count", 2),
                    max_rules=learn_cfg.get("max_rules", 200),
                )
            except Exception:
                logging.exception("初始化学习规则失败")
                self.learn = None
        else:
            self.learn = None

        started, auto_message = True, ""
        if "autostart" in (payload.get("ui") or {}):
            started, auto_message = autostart.set_enabled(
                bool(self.cfg.get("ui", {}).get("autostart", False))
            )
        self.window.refresh_data(self.cfg)
        message = "已保存并应用"
        if not started:
            message += "；" + auto_message
        return True, message

    @staticmethod
    def _engine_device(engine):
        device = getattr(engine, "device", "cpu")
        reason = getattr(engine, "_gpu_fallback_reason", "")
        text = "已加载 · {}".format("GPU (CUDA)" if device == "cuda" else "CPU")
        if device != "cuda" and reason:
            text += "（{}）".format(reason)
        return text

    def _set_engine_state(self, text, ok=None):
        page = getattr(self.window, "settings_page", None)
        if page is not None:
            page.set_engine_state(text, ok)

    def _report_engine_state(self):
        """主线程读取当前引擎状态，刷新设置页的「加载状态」。"""
        engine = getattr(self.asr, "primary", self.asr)
        if hasattr(engine, "model") and engine.model is None:
            self._set_engine_state("尚未加载", None)
            return
        self._set_engine_state(self._engine_device(engine), True)

    def _warmup_engine(self):
        """后台加载模型；通过 Qt 信号回到主线程更新状态，避免跨线程操作界面。"""
        self._set_engine_state("正在加载模型…", None)

        def work():
            engine = getattr(self.asr, "primary", self.asr)
            try:
                if hasattr(self.asr, "warmup"):
                    self.asr.warmup()
            except Exception as e:
                logging.exception("模型预热失败")
                self._emit_engine_state("加载失败：{}".format(e), False)
                return
            if hasattr(engine, "model") and engine.model is None:
                self._emit_engine_state("加载失败（详见控制台日志）", False)
                return
            self._emit_engine_state(self._engine_device(engine), True)

        threading.Thread(target=work, daemon=True).start()

    def _emit_engine_state(self, text, ok):
        signal = getattr(self.window, "engine_state", None)
        if signal is not None:
            signal.emit(text, ok)

    def delete_history(self, entry):
        try:
            if self.history is not None:
                self.history.remove(entry)
            else:
                remove_entry(entry)
        except OSError:
            logging.exception("删除历史记录失败")
            return
        self.window.history_page.reload()
        self.window.home.refresh_stats()

    def clear_history(self):
        try:
            if self.history is not None:
                self.history.clear()
            else:
                clear_entries()
        except OSError:
            logging.exception("清空历史记录失败")
            return
        self.window.history_page.reload()
        self.window.home.refresh_stats()

    def reinject_text(self, text):
        """隐藏主窗口后把文本重新写入前台窗口；写入完再恢复窗口。"""
        if not text:
            return
        self.window.hide()
        self.root.after(260, lambda: self._reinject_now(text))

    def _reinject_now(self, text):
        inject_cfg = self.cfg.get("inject", {})
        try:
            ok, reason = safe_inject.inject(
                text,
                restore_delay_sec=inject_cfg.get("restore_delay_sec", 0.2),
                require_same_focus=False,
                paste_mode=inject_cfg.get("paste_mode", "auto"),
                terminal_classes=inject_cfg.get("terminal_classes"),
            )
        except Exception as e:
            logging.exception("重新注入失败")
            ok, reason = False, str(e)
        if ok:
            self.overlay.show("PREVIEW", "已重新写入")
        else:
            self.overlay.show("ERROR", "重新写入失败：{}".format(reason))
        self.root.after(1500, self._restore_after_reinject)

    def _restore_after_reinject(self):
        if self.state == "IDLE":
            self.overlay.hide()
        self.window.show_page("历史")

    def reload_dictionary(self):
        """词库改动后让识别引擎重新读取热词（下一次转写生效）。"""
        engines = [self.asr, getattr(self.asr, "primary", None)]
        for engine in engines:
            if engine is not None and hasattr(engine, "reload_glossary"):
                try:
                    engine.reload_glossary()
                except Exception:
                    logging.exception("刷新词库缓存失败")

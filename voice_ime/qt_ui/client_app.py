# -*- coding: utf-8 -*-
"""客户端版 App：复用 main.App 的引擎逻辑，补上设置保存与界面刷新。"""
import logging
import threading

import main
from config import save_config
from history import HistoryStore
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
                threading.Thread(target=self.asr.warmup, daemon=True).start()
            except Exception as e:
                logging.exception("重建识别引擎失败")
                return False, "配置已保存，但识别引擎重建失败：{}".format(e)

        hist_enabled = bool(self.cfg.get("history", {}).get("enabled", False))
        if hist_enabled and self.history is None:
            self.history = HistoryStore(
                max_entries=self.cfg.get("history", {}).get("max_entries", 100)
            )
        elif not hist_enabled:
            self.history = None

        learn_enabled = bool(self.cfg.get("learn", {}).get("enabled", False))
        if learn_enabled and self.learn is None:
            self.learn = LearnedRules(
                min_count=self.cfg.get("learn", {}).get("min_count", 2),
                max_rules=self.cfg.get("learn", {}).get("max_rules", 200),
            )
        elif not learn_enabled:
            self.learn = None

        self.window.refresh_data(self.cfg)
        return True, "已保存并应用"

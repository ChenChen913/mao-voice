# -*- coding: utf-8 -*-
"""客户端版 App：复用 main.App 的全部引擎逻辑，只把设置窗口接到 Qt 主窗口。"""
import main


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
            except Exception:
                pass

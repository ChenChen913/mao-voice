# -*- coding: utf-8 -*-
"""pytest 公共配置：把 voice_ime 根目录加入 sys.path，便于直接 import 被测模块。"""
import os
import sys

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

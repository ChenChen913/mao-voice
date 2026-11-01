# facts.md

> README 的唯一事实来源。A 部分由脚本/命令扫描生成后人工核对；B 部分取自仓库内用户文档，无法溯源的留 TODO。
> 更新时间：2026-11-01（v5.19 文档整理后重新核对）

## A. 可自动提取的事实

1. **项目类型**：Windows 桌面 AI 语音输入工具（个人效率工具 / 实验性项目）
2. **版本号**：`voice_ime/version.py` → `5.19.1`（启动日志、设置标题、托盘提示均取此处）
3. **主语言 / 运行时 / 最低版本**：Python；doctor.py 要求 >= 3.10，CI 在 3.12 / 3.13 测试（`.github/workflows/ci.yml` matrix）
4. **安装命令**：`pip install -r voice_ime/requirements.txt`（requirements.txt 存在，2026-11-01 实跑 doctor 通过）
5. **运行命令**：`python main.py`（voice_ime/main.py）或双击 `voice_ime/启动.bat`
6. **测试命令**：`python -m pytest voice_ime/tests -q` → 实跑结果 **127 passed in 2.13s**（2026-11-01，Python 3.13.3）
7. **静态检查**：`python -m ruff check voice_ime`（CI 同款，2026-11-01 实跑通过）
8. **构建命令**：`python packaging/build_exe.py`（可选 `--cpu-only`；CI 的 package.yml 固定 CPU 版）
9. **环境自检**：`python doctor.py`（7 项；源码首次运行前未建 config.json 时会有 2 项提示，属预期）
10. **真机端到端冒烟**：`python voice_ime/tests/e2e_live.py --no-asr` → 2026-11-01 实跑 **PASS**（注入成功、剪贴板恢复为哨兵）；完整模式需先下载模型
11. **目录结构**：
    - `voice_ime/` — 运行时代码，**16 个 .py 模块，4389 行**（2026-11-01 `Get-ChildItem voice_ime/*.py` + 行数统计）
    - `voice_ime/tests/` — 20 个测试相关 .py（127 项用例 + 手动脚本）
    - `packaging/` — PyInstaller 打包脚本与图标
    - `docs/` — 部署文档、PRD/SPEC/调研、更新记录、`docs/audits/` 审核报告、`docs/images/` 实机截图、`docs/plans/`
    - `.github/workflows/` — `ci.yml`（测试）、`package.yml`（tag 触发打包发布，CPU 版）
12. **主要依赖**（requirements.txt，9 个）：faster-whisper（>=1.0.0,<1.3）、ctranslate2（>=4.0,<5）、sounddevice、pynput、numpy、requests、onnxruntime、pystray、Pillow
13. **环境变量**：`DEEPSEEK_API_KEY`（纠错 Key 兜底）、`ASR_API_KEY`（云端 ASR Key 兜底，其次回退 DEEPSEEK_API_KEY）
14. **模型实测大小**（2026-09-28 记录，未变更）：medium = 1.5G，small = 464M
15. **许可证**：Apache-2.0（LICENSE 存在）
16. **文档清单**：README.md / README_EN.md；docs/ 下：部署文档、PRD、SPEC、调研与产品设计、更新记录、`audits/` 四份审核报告 + OCR 审查报告、facts.md
17. **演示素材**：`docs/images/overlay-recording.png`、`overlay-transcribing.png`、`overlay-injecting.png`（2026-11-01 由真实 Overlay 渲染并截取，非占位图）

## B. 需人工确认的事实（已核对）

- **一句话描述**：「按一下热键开始录音，再按一下结束：本地 Whisper 识别 + 大模型保守纠错，干净文本直接注入当前输入框的 Windows 工具。」
- **为什么做这个项目**：见 README「为什么做这个项目」；动机源自 PRD §1 与调研文档 §3 竞品分析
- **隐私边界**：音频不出本机；只有开启纠错时识别文本发往用户配置的 OpenAI 兼容端点（默认 DeepSeek）；不填 Key 零联网
- **与同类方案的差异**：详见 README「与同类工具的差别」；CapsWriter-Offline 的 star 数（7046）与「按住 CapsLock、FunASR 离线、热词 + LLM 润色」取自其 GitHub 仓库页（2026-11-01 查询）
- **已知限制**：见 README「已知限制」，含右侧 Alt 在部分布局等于 AltGr、云端 ASR 未真机联调、管理员窗口 UIPI 拦截、历史/学习明文落盘、长录音内存线性增长、打包版 GPU 未在 CI 验证
- **AI 参与声明**：README 原文——「由 AI 辅助开发（多 Agent 分模块实现，经多轮 AI 代码审查与三轮人工抽验）」

## 核对记录（2026-11-01）

- [x] pytest 实跑 127 passed；doctor 实跑（依赖/麦克风/GPU 通过，config.json 未建时按预期提示）
- [x] `ruff check`、`compileall` 实跑通过
- [x] `tests/e2e_live.py --no-asr` 实跑 PASS（真实注入 + 剪贴板恢复）
- [x] 模块数（16）、行数（4389）、测试数（127）均以命令输出为准
- [x] 演示截图为真实 Overlay 渲染结果的截屏，未做 UI 像素修改
- [x] 仓库内无明文密钥（`sk-` / `ghp_` 仅出现在测试假 key）
